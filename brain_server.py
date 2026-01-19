import json
import os
import subprocess
import sys
import traceback
from datetime import datetime
from typing import Optional

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, os.getcwd())

from system.session_state import session_state
from system.eai_context import get_eai_system_prompt
from system.brain_index import BrainIndex

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

with open('brain_config.json', 'r') as f:
    config = json.load(f)

OLLAMA_URL = "http://localhost:11434/api/generate"

MODELS = {
    "hands": "codellama:7b",
    "thinker": "deepseek-r1:latest",
    "swarm": "tinyllama"
}

MEMORY_FILE = "system/brain_memory.json"
brain_index = BrainIndex(config['brain_path'])

def load_memory():
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {"created": datetime.now().isoformat(), "total_tasks": 0, "successful_tasks": 0, "failed_tasks": 0}

def save_memory(memory):
    os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
    memory["last_updated"] = datetime.now().isoformat()
    with open(MEMORY_FILE, 'w') as f:
        json.dump(memory, f, indent=2)

memory = load_memory()

def call_model(prompt: str, model: str, system: str = None, timeout: int = 120) -> dict:
    for attempt in range(3):
        try:
            payload = {'model': model, 'prompt': prompt, 'stream': False, 'options': {'temperature': 0.1, 'num_predict': 4000}}
            if system:
                payload['system'] = system
            response = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
            if response.status_code == 200:
                return {"status": "success", "response": response.json().get("response", "")}
            return {"status": "error", "message": f"Ollama returned {response.status_code}"}
        except requests.exceptions.Timeout:
            if attempt < 2:
                continue
            return {"status": "error", "message": "Timeout"}
        except Exception as e:
            if attempt < 2:
                continue
            return {"status": "error", "message": str(e)}
    return {"status": "error", "message": "Unknown error"}

def parse_json_response(response_text: str) -> list:
    if not response_text:
        return [{"error": "Empty response"}]
    cleaned = response_text.strip()
    if "```json" in cleaned:
        cleaned = cleaned.split("```json")[1].split("```")[0]
    elif "```" in cleaned:
        parts = cleaned.split("```")
        if len(parts) >= 2:
            cleaned = parts[1]
    cleaned = cleaned.strip()
    try:
        parsed = json.loads(cleaned)
        return [parsed] if isinstance(parsed, dict) else parsed
    except:
        pass
    if '[' in response_text:
        start, end = response_text.find('['), response_text.rfind(']') + 1
        if end > start:
            try:
                return json.loads(response_text[start:end])
            except:
                pass
    if '{' in response_text:
        start, end = response_text.find('{'), response_text.rfind('}') + 1
        if end > start:
            try:
                return [json.loads(response_text[start:end])]
            except:
                pass
    return [{"error": "Parse failed", "raw": response_text[:300]}]

class Command(BaseModel):
    operation: str
    path: Optional[str] = None

class ExecutorTask(BaseModel):
    task_description: str
    model: Optional[str] = None
    num_agents: Optional[int] = 50
    rounds: Optional[int] = 2

class SearchQuery(BaseModel):
    query: str

class ThinkRequest(BaseModel):
    question: str
    context: Optional[str] = None

def tool_create_file(path: str, content: str) -> dict:
    try:
        full_path = os.path.join(config['brain_path'], path)
        dir_name = os.path.dirname(full_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        session_state.index_file(path, os.path.splitext(path)[1], "Created by EAI")
        return {'status': 'created', 'path': path, 'size': len(content)}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def tool_edit_file(path: str, find: str, replace: str) -> dict:
    """Edit file by find/replace - no need to rewrite entire file"""
    try:
        full_path = os.path.join(config['brain_path'], path)
        if not os.path.exists(full_path):
            return {'status': 'error', 'message': f'File not found: {path}'}
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        if find not in content:
            return {'status': 'error', 'message': 'Search string not found'}
        new_content = content.replace(find, replace, 1)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return {'status': 'edited', 'path': path}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def tool_execute_python(code: str) -> dict:
    try:
        result = subprocess.run(['python', '-c', code], cwd=config['brain_path'], capture_output=True, text=True, timeout=30)
        return {'status': 'executed', 'stdout': result.stdout[:1000], 'stderr': result.stderr[:500]}
    except subprocess.TimeoutExpired:
        return {'status': 'error', 'message': 'Timeout (30s)'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def tool_list_dir(path: str = '') -> dict:
    try:
        full_path = os.path.join(config['brain_path'], path)
        items = []
        for item in os.listdir(full_path)[:50]:
            item_path = os.path.join(full_path, item)
            items.append({'name': item, 'type': 'dir' if os.path.isdir(item_path) else 'file'})
        session_state.cache_directory(path or '.', items)
        return {'status': 'listed', 'path': path or '.', 'items': items}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def execute_actions(actions: list) -> tuple:
    files_created, files_edited, execution_log = [], [], []
    for action in actions:
        if 'error' in action:
            execution_log.append({'error': action.get('error')})
            memory["failed_tasks"] += 1
            continue
        action_type = action.get('action', '')
        if action_type == 'create_file':
            result = tool_create_file(action.get('path', ''), action.get('content', ''))
            if result['status'] == 'created':
                files_created.append(action.get('path'))
                memory["successful_tasks"] += 1
            else:
                memory["failed_tasks"] += 1
            execution_log.append(result)
        elif action_type == 'edit_file':
            result = tool_edit_file(action.get('path', ''), action.get('find', ''), action.get('replace', ''))
            if result['status'] == 'edited':
                files_edited.append(action.get('path'))
                memory["successful_tasks"] += 1
            else:
                memory["failed_tasks"] += 1
            execution_log.append(result)
        elif action_type == 'execute_python':
            result = tool_execute_python(action.get('code', ''))
            execution_log.append(result)
            memory["successful_tasks" if result['status'] == 'executed' else "failed_tasks"] += 1
        elif action_type == 'list_dir':
            result = tool_list_dir(action.get('path', ''))
            execution_log.append(result)
    memory["total_tasks"] += len(actions)
    save_memory(memory)
    return files_created, files_edited, execution_log

@app.post('/view')
async def view_brain(cmd: Command):
    brain_path = config['brain_path']
    try:
        if cmd.operation == 'read_file':
            file_path = os.path.join(brain_path, cmd.path or '')
            if not os.path.exists(file_path):
                raise HTTPException(status_code=404, detail=f'Not found: {cmd.path}')
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            session_state.mark_file_viewed(cmd.path)
            return {'status': 'success', 'content': content[:8000], 'truncated': len(content) > 8000}
        elif cmd.operation == 'list_directory':
            cached = session_state.get_cached_directory(cmd.path or '.')
            if cached:
                return {'status': 'cached', 'items': cached}
            dir_path = os.path.join(brain_path, cmd.path or '')
            if not os.path.exists(dir_path):
                raise HTTPException(status_code=404, detail=f'Not found: {cmd.path}')
            items = []
            for item in os.listdir(dir_path)[:50]:
                item_path = os.path.join(dir_path, item)
                items.append({'name': item, 'type': 'dir' if os.path.isdir(item_path) else 'file'})
            session_state.cache_directory(cmd.path or '.', items)
            return {'status': 'success', 'items': items}
        raise HTTPException(status_code=403, detail='Invalid operation')
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/execute')
async def execute_task(task: ExecutorTask):
    try:
        print(f'[EAI] {task.task_description[:80]}')
        session_state.set_working_on(task.task_description[:100])
        model = task.model or MODELS["hands"]
        system_prompt = get_eai_system_prompt(task.task_description)
        result = call_model(f'{task.task_description}\n\nJSON only:', model, system_prompt, timeout=90)
        if result["status"] != "success":
            return {'status': 'error', 'message': result.get('message')}
        print(f'[EAI] Response: {result["response"][:150]}')
        actions = parse_json_response(result["response"])
        files_created, files_edited, execution_log = execute_actions(actions)
        print(f'[EAI] Done: {len(files_created)} created, {len(files_edited)} edited')
        return {
            'status': 'success',
            'created': files_created,
            'edited': files_edited,
            'log': execution_log,
            'model': model
        }
    except Exception as e:
        print(f'[EAI ERROR] {str(e)}')
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/think')
async def deep_think(req: ThinkRequest):
    try:
        print(f'[THINK] {req.question[:80]}')
        prompt = req.question
        if req.context:
            prompt = f"Context:\n{req.context}\n\nQuestion:\n{req.question}"
        result = call_model(prompt, MODELS["thinker"], None, timeout=180)
        if result["status"] != "success":
            return {'status': 'error', 'message': result.get('message')}
        return {'status': 'success', 'reasoning': result["response"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/search')
async def search_brain(query: SearchQuery):
    """Search entire brain without directory traversal"""
    results = brain_index.search(query.query)
    return {'status': 'success', 'results': results, 'count': len(results)}

@app.post('/reindex')
async def reindex_brain():
    """Reindex entire brain for search"""
    count = brain_index.reindex()
    return {'status': 'indexed', 'files': count}

@app.get('/context')
async def get_context():
    """Get full session context for Opus"""
    return {
        'working_on': session_state.state.get('working_on'),
        'recent_files': session_state.state.get('last_viewed', [])[-10:],
        'active_problems': session_state.state.get('active_problems', []),
        'directory_cache': list(session_state.state.get('directory_cache', {}).keys()),
        'hugo_preferences': session_state.state.get('hugo_preferences'),
        'project_context': session_state.state.get('project_context')
    }

@app.get('/status')
async def status():
    ollama_status = "unknown"
    models = []
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=2)
        if r.status_code == 200:
            ollama_status = "online"
            models = [m['name'] for m in r.json().get('models', [])]
    except:
        ollama_status = "offline"
    return {
        'status': 'online',
        'hierarchy': {'commander': 'Opus', 'hands': MODELS['hands'], 'thinker': MODELS['thinker'], 'swarm': MODELS['swarm']},
        'memory': {'tasks': memory['total_tasks'], 'success_rate': f"{(memory['successful_tasks'] / max(memory['total_tasks'], 1)) * 100:.0f}%"},
        'session': {'working_on': session_state.state.get('working_on'), 'cached_dirs': len(session_state.state.get('directory_cache', {}))},
        'ollama': ollama_status,
        'models': models,
        'endpoints': ['/execute', '/think', '/search', '/reindex', '/view', '/context', '/status']
    }

if __name__ == '__main__':
    import uvicorn
    # Auto-index on startup
    print('[BRAIN] Indexing files...')
    count = brain_index.reindex()
    print(f'[BRAIN] Indexed {count} files')
    print('='*60)
    print('🧠 BRAIN SERVER v2.0')
    print('='*60)
    print(f'👑 Commander: Opus')
    print(f'🤖 Hands: {MODELS["hands"]}')
    print(f'🧠 Thinker: {MODELS["thinker"]}')
    print(f'🐜 Swarm: {MODELS["swarm"]}')
    print(f'📁 Indexed: {count} files')
    print(f'🔍 Search: ENABLED')
    print(f'💾 Session State: ENABLED')
    print('='*60)
    uvicorn.run(app, host='127.0.0.1', port=config['server_port'])
