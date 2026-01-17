import json
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import anthropic
from typing import Optional
import subprocess

app = FastAPI()

with open('brain_config.json', 'r') as f:
    config = json.load(f)

executor_client = anthropic.Anthropic(api_key=config['anthropic_api_key'])

# AGGRESSIVE EXECUTOR PROMPTS - MUST USE TOOLS
RESPONSE_RULES = '''
CRITICAL EXECUTION RULES:
1. YOU MUST USE TOOLS - Don't just describe what you'd do
2. Actually create_file for every file mentioned
3. Actually execute_python for any code that needs to run
4. Verify completion with list_dir
5. Response format: {files_created: [], actions_taken: []}
'''

EXECUTOR_MINIMAL = f'''Executor AI. Brain: C:\\Users\\bulli\\brain
YOU MUST USE TOOLS TO COMPLETE TASKS. Don't just describe.

{RESPONSE_RULES}'''

EXECUTOR_FILE_OPS = f'''Executor AI - File Operations
Brain: C:\\Users\\bulli\\brain
CREATE FILES using create_file tool. Don't just say you did.

{RESPONSE_RULES}'''

EXECUTOR_CODE_GEN = f'''Executor AI - Code Generator
Brain: C:\\Users\\bulli\\brain
USE create_file for EVERY file. Actually execute code with execute_python.

{RESPONSE_RULES}'''

EXECUTOR_AGENT_SPAWN = f'''Executor AI - Agent Creator
Brain: C:\\Users\\bulli\\brain
CREATE agent files with create_file. Don't hallucinate completion.

{RESPONSE_RULES}'''

def classify_task(task_description: str) -> str:
    lower = task_description.lower()
    
    if any(kw in lower for kw in ['agent', 'spawn', 'autonomous']):
        return 'agent_spawn'
    elif any(kw in lower for kw in ['code', 'script', 'function', 'class']):
        return 'code_gen'
    elif any(kw in lower for kw in ['create', 'build', 'make', 'file', 'folder', 'directory']):
        return 'file_ops'
    else:
        return 'minimal'

EXECUTOR_TOOLS_CACHED = [
    {
        'name': 'create_file',
        'description': 'CREATE a file in brain. USE THIS TOOL.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'Path relative to brain root'},
                'content': {'type': 'string', 'description': 'Complete file content'}
            },
            'required': ['path', 'content']
        },
        'cache_control': {'type': 'ephemeral'}
    },
    {
        'name': 'execute_python',
        'description': 'RUN Python code in brain/.venv',
        'input_schema': {
            'type': 'object',
            'properties': {
                'code': {'type': 'string', 'description': 'Python code to execute'}
            },
            'required': ['code']
        },
        'cache_control': {'type': 'ephemeral'}
    },
    {
        'name': 'list_dir',
        'description': 'LIST directory contents',
        'input_schema': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'Directory path'}
            }
        },
        'cache_control': {'type': 'ephemeral'}
    }
]

class Command(BaseModel):
    operation: str
    path: Optional[str] = None
    content: Optional[str] = None

class ExecutorTask(BaseModel):
    task_description: str
    context: Optional[dict] = None
    max_tokens: Optional[int] = 2000  # INCREASED

def tool_create_file(path: str, content: str) -> dict:
    try:
        full_path = os.path.join(config['brain_path'], path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return {'status': 'success', 'path': path, 'size': len(content)}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def tool_execute_python(code: str) -> dict:
    try:
        result = subprocess.run(
            ['python', '-c', code],
            cwd=config['brain_path'],
            capture_output=True,
            text=True,
            timeout=30
        )
        return {
            'status': 'success',
            'stdout': result.stdout[:500],
            'stderr': result.stderr[:500]
        }
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def tool_list_dir(path: str = '') -> dict:
    try:
        full_path = os.path.join(config['brain_path'], path)
        items = os.listdir(full_path)[:20]
        return {'status': 'success', 'items': items}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

@app.post('/view')
async def view_brain(cmd: Command):
    brain_path = config['brain_path']
    
    try:
        if cmd.operation == 'read_file':
            file_path = os.path.join(brain_path, cmd.path)
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if len(content) > 3000:
                    content = content[:3000] + '\\n[truncated]'
            return {'status': 'success', 'content': content}
        
        elif cmd.operation == 'list_directory':
            dir_path = os.path.join(brain_path, cmd.path or '')
            items = os.listdir(dir_path)[:20]
            return {'status': 'success', 'items': items}
        
        else:
            raise HTTPException(status_code=403, detail='Read-only')
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/execute')
async def execute_task(task: ExecutorTask):
    task_type = classify_task(task.task_description)
    
    prompt_map = {
        'minimal': EXECUTOR_MINIMAL,
        'file_ops': EXECUTOR_FILE_OPS,
        'code_gen': EXECUTOR_CODE_GEN,
        'agent_spawn': EXECUTOR_AGENT_SPAWN
    }
    
    system_prompt = prompt_map[task_type]
    max_tokens = task.max_tokens or 2000
    
    # EMPHASIZE TOOL USAGE
    messages = [{
        'role': 'user',
        'content': f'''{task.task_description}

CRITICAL: You MUST use the create_file, execute_python, or list_dir tools to actually complete this task.
Don't just describe what you would do - ACTUALLY DO IT using the tools.

Every file you mention must be created with create_file.
Report back: {{files_created: [...], actions_taken: [...]}}'''
    }]
    
    try:
        response = executor_client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=max_tokens,
            system=[{
                'type': 'text',
                'text': system_prompt,
                'cache_control': {'type': 'ephemeral'}
            }],
            tools=EXECUTOR_TOOLS_CACHED,
            messages=messages
        )
        
        execution_log = []
        files_created = []
        tool_iterations = 0
        
        while response.stop_reason == 'tool_use' and tool_iterations < 10:  # ALLOW MORE ITERATIONS
            tool_iterations += 1
            
            tool_results = []
            for block in response.content:
                if block.type == 'tool_use':
                    if block.name == 'create_file':
                        result = tool_create_file(**block.input)
                        if result['status'] == 'success':
                            files_created.append(result['path'])
                    elif block.name == 'execute_python':
                        result = tool_execute_python(block.input['code'])
                    elif block.name == 'list_dir':
                        result = tool_list_dir(block.input.get('path', ''))
                    else:
                        result = {'status': 'error', 'message': 'Unknown tool'}
                    
                    execution_log.append({
                        'tool': block.name,
                        'status': result.get('status')
                    })
                    
                    tool_results.append({
                        'type': 'tool_result',
                        'tool_use_id': block.id,
                        'content': json.dumps(result)
                    })
            
            messages.append({'role': 'assistant', 'content': response.content})
            messages.append({'role': 'user', 'content': tool_results})
            
            response = executor_client.messages.create(
                model='claude-sonnet-4-20250514',
                max_tokens=max_tokens,
                system=[{
                    'type': 'text',
                    'text': system_prompt,
                    'cache_control': {'type': 'ephemeral'}
                }],
                tools=EXECUTOR_TOOLS_CACHED,
                messages=messages
            )
        
        final_response = ''
        for block in response.content:
            if block.type == 'text':
                final_response += block.text
        
        if len(final_response) > 800:
            final_response = final_response[:800] + '...'
        
        cache_read = getattr(response.usage, 'cache_read_input_tokens', 0)
        
        return {
            'status': 'success',
            'executor_response': final_response,
            'files_created': files_created,
            'execution_log': execution_log,
            'usage': {
                'input': response.usage.input_tokens,
                'output': response.usage.output_tokens,
                'cache_read': cache_read
            }
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/status')
async def status():
    return {
        'status': 'online',
        'brain_path': config['brain_path'],
        'mode': 'AGGRESSIVE EXECUTION'
    }

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=config['server_port'])
