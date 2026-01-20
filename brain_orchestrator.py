import ollama
import json
import requests
import time
from datetime import datetime
import os
import sys

sys.path.insert(0, os.getcwd())
from system.recursive_memory import get_memory

# Initialize memory
opus_memory = get_memory()

with open('brain_config.json', 'r') as f:
    config = json.load(f)

# =============================================================================
# CONFIG
# =============================================================================
MODEL = "qwen2.5-coder:7b"
THINKER_MODEL = "deepseek-r1:latest"
brain_url = f"http://127.0.0.1:{config['server_port']}"
BRAIN_SERVER_ONLINE = False

CONVO_MEMORY_FILE = "system/conversation_memory.json"
SYSTEM_PROMPT = "You are Marcos. You live inside Hugo's Brain - a codebase you can interact with. You just ran a tool or Hugo asked you something. Respond to what just happened. Be direct. 1-3 sentences. No generic AI talk."

# =============================================================================
# CONVERSATION MEMORY (survives sessions)
# =============================================================================
def load_conversation_memory():
    try:
        if os.path.exists(CONVO_MEMORY_FILE):
            with open(CONVO_MEMORY_FILE, 'r') as f:
                return json.load(f)
    except: pass
    return {"sessions": 0, "key_facts": [], "user_preferences": [], "ongoing_projects": []}

def save_conversation_memory(mem):
    os.makedirs(os.path.dirname(CONVO_MEMORY_FILE), exist_ok=True)
    with open(CONVO_MEMORY_FILE, 'w') as f:
        json.dump(mem, f, indent=2)

convo_memory = load_conversation_memory()

# =============================================================================
# CORE FUNCTIONS
# =============================================================================
def remember(fact_type, content):
    """Store fact in both short-term and long-term memory"""
    if fact_type == 'key_fact':
        convo_memory["key_facts"].append(content)
        convo_memory["key_facts"] = convo_memory["key_facts"][-20:]
    elif fact_type == 'project':
        convo_memory["ongoing_projects"].append(content)
        convo_memory["ongoing_projects"] = convo_memory["ongoing_projects"][-10:]
    elif fact_type == 'preference':
        convo_memory["user_preferences"].append(content)
        convo_memory["user_preferences"] = convo_memory["user_preferences"][-10:]
    save_conversation_memory(convo_memory)
    try:
        opus_memory.remember_fact(fact_type, content)
    except: pass
    print(f"   ✓ Remembered [{fact_type}]: {content[:50]}...")
    return {"status": "remembered", "type": fact_type}

def remember_batch(facts):
    """Store multiple facts at once"""
    results = []
    for fact in facts:
        fact_type = fact.get('fact_type', 'key_fact')
        content = fact.get('content', '')
        if content:
            result = remember(fact_type, content)
            results.append(result)
    print(f"   ✓ Batch remembered {len(results)} facts")
    return {"status": "batch_remembered", "count": len(results)}

def search_memory(query):
    """Search long-term memory"""
    try:
        results = opus_memory.search_memories(query)
        total = results.get("total_matches", 0)
        print(f"   ✓ Memory: {total} matches for '{query}'")
        return {
            "query": query,
            "total": total,
            "facts": results.get("matching_facts", [])[:10],
            "projects": results.get("matching_projects", [])[:5]
        }
    except Exception as e:
        return {"error": str(e)}

def search_brain(query):
    """Search files via brain_server"""
    if not BRAIN_SERVER_ONLINE:
        return {'error': 'brain_server offline', 'count': 0, 'files': []}
    try:
        r = requests.post(f'{brain_url}/search', json={'query': query}, timeout=30)
        result = r.json()
        print(f"   ✓ Found {result.get('count', 0)} files matching '{query}'")
        return result
    except Exception as e:
        return {'error': str(e), 'count': 0, 'files': []}

def create_file(path, content):
    """Create file directly"""
    try:
        path = path.replace(' ', '_')
        if '.' not in os.path.basename(path):
            path = path + '.txt'
        full_path = os.path.join(config['brain_path'], path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True) if os.path.dirname(full_path) else None
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"   ✓ Created: {path}")
        if BRAIN_SERVER_ONLINE:
            try: requests.post(f'{brain_url}/reindex', timeout=10)
            except: pass
        return {'status': 'created', 'path': path}
    except Exception as e:
        return {'error': str(e)}

def execute_task(task_description):
    """Send task to brain_server (CodeLlama)"""
    if not BRAIN_SERVER_ONLINE:
        return {'error': 'brain_server offline - cannot execute tasks'}
    try:
        r = requests.post(f'{brain_url}/execute', json={'task_description': task_description}, timeout=120)
        result = r.json()
        if result.get('created'): print(f"   ✓ Created: {', '.join(result['created'])}")
        if result.get('edited'): print(f"   ✓ Edited: {', '.join(result['edited'])}")
        return result
    except Exception as e:
        return {'error': str(e)}

def deep_think(question):
    """Deep analysis via thinker model"""
    try:
        print(f"   🧠 Thinking...")
        response = ollama.chat(
            model=THINKER_MODEL,
            messages=[{"role": "user", "content": f"Analyze thoroughly: {question}"}],
            options={'num_predict': 1024, 'temperature': 0.5}
        )
        reasoning = response.get('message', {}).get('content', '')
        print(f"   ✓ Analysis complete ({len(reasoning)} chars)")
        return {'reasoning': reasoning}
    except Exception as e:
        return {'error': str(e)}

# =============================================================================
# MEMORY CONTEXT
# =============================================================================
def get_memory_context():
    """Get recent memory context for injection into prompts"""
    parts = []

    # Last 3 key facts
    facts = convo_memory.get("key_facts", [])[-3:]
    if facts:
        parts.append(f"[Memory: {'; '.join(facts)}]")

    # Last 2 projects
    projects = convo_memory.get("ongoing_projects", [])[-2:]
    if projects:
        parts.append(f"[Projects: {'; '.join(projects)}]")

    return " ".join(parts)

# =============================================================================
# INTENT DETECTION (code-based)
# =============================================================================
def detect_intent(text):
    """Detect intent from keywords"""
    t = text.lower()

    # Identity
    if any(w in t for w in ['who are you', 'what are you', 'your name', 'are you marcos']):
        return 'identity'

    # Capabilities
    if any(w in t for w in ['what can you', 'can you do', 'abilities', 'help']):
        return 'capabilities'

    # Status
    if any(w in t for w in ['you online', 'you there', 'status', 'health']):
        return 'status'

    # List files
    if any(w in t for w in ['list files', 'show files', 'what files', 'ls', 'dir']):
        return 'list_files'

    if any(w in t for w in ['remember', 'store', 'save fact', 'note that']):
        return 'remember'
    if any(w in t for w in ['recall', 'what do you remember', 'search memory']):
        return 'search_memory'
    if any(w in t for w in ['create file', 'make file', 'write file', 'new file']):
        return 'create_file'
    if any(w in t for w in ['search', 'find', 'look for', 'where is']):
        return 'search'
    if any(w in t for w in ['think deep', 'analyze', 'think about']):
        return 'deep_think'
    if any(w in t for w in ['execute', 'run', 'do this', 'edit file', 'modify']):
        return 'execute'
    if '?' in text:
        return 'question'
    return 'conversation'

# =============================================================================
# STREAMING RESPONSE
# =============================================================================
def stream_response(prompt):
    """Stream response from model with memory context"""
    # Get memory context
    memory_ctx = get_memory_context()
    full_prompt = f"{memory_ctx}\n\n{prompt}" if memory_ctx else prompt

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": full_prompt}
    ]
    response_text = ""
    try:
        stream = ollama.chat(model=MODEL, messages=messages, stream=True,
                            options={'num_predict': 300, 'temperature': 0.4})
        print("Marcos: ", end="", flush=True)
        for chunk in stream:
            token = chunk.get('message', {}).get('content', '')
            if token:
                print(token, end="", flush=True)
                response_text += token
        print()
    except Exception as e:
        print(f"Error: {e}")
        return None
    return response_text

# =============================================================================
# ROUTE AND EXECUTE
# =============================================================================
def route_and_execute(user_input, intent, conversation):
    """Route to correct function based on intent"""

    # Identity - hardcoded
    if intent == 'identity':
        response = "I'm Marcos. I live in your Brain repo. I can search files, create files, remember facts across sessions, execute code, and think deep when you need analysis."
        print(f"Marcos: {response}")
        conversation.append({'role': 'assistant', 'content': response})
        return None

    # Capabilities - hardcoded
    if intent == 'capabilities':
        response = "search_brain, create_file, remember, search_memory, execute_task, deep_think. Just tell me what you need."
        print(f"Marcos: {response}")
        conversation.append({'role': 'assistant', 'content': response})
        return None

    # Status - hardcoded
    if intent == 'status':
        response = f"Online. Session #{convo_memory['sessions']}. {len(convo_memory['key_facts'])} facts stored."
        print(f"Marcos: {response}")
        conversation.append({'role': 'assistant', 'content': response})
        return None

    # List files
    if intent == 'list_files':
        result = search_brain("*")
        files = result.get('files', result.get('matches', []))[:5]
        file_names = [f.get('name', f) if isinstance(f, dict) else str(f) for f in files]
        resp = stream_response(f"Found {result.get('count', 0)} files. Top matches: {', '.join(file_names)}")
        if resp:
            conversation.append({'role': 'assistant', 'content': resp})
        return result

    # Remember
    if intent == 'remember':
        content = user_input.replace('remember', '').replace('note that', '').strip()
        result = remember('key_fact', content)
        resp = stream_response("Stored. I'll remember that.")
        if resp:
            conversation.append({'role': 'assistant', 'content': resp})
        return result

    # Search memory
    if intent == 'search_memory':
        query = user_input.replace('recall', '').replace('what do you remember about', '').strip()
        result = search_memory(query)
        facts = result.get('facts', [])[:3]
        fact_texts = '; '.join([f.get('content', '')[:50] for f in facts]) if facts else 'none'
        resp = stream_response(f"Found {result.get('total', 0)} memories. {fact_texts}")
        if resp:
            conversation.append({'role': 'assistant', 'content': resp})
        return result

    # Create file
    if intent == 'create_file':
        # Extract filename and content with model help
        extract_resp = stream_response(f"Extract filename and content from: {user_input}\nReply as: FILENAME: ... CONTENT: ...")
        if extract_resp and 'FILENAME:' in extract_resp:
            try:
                parts = extract_resp.split('CONTENT:')
                filename = parts[0].replace('FILENAME:', '').strip()
                content = parts[1].strip() if len(parts) > 1 else ""
                result = create_file(filename, content)
                if result.get('error'):
                    resp = stream_response(f"Failed to create file: {result.get('error')}")
                else:
                    resp = stream_response(f"Created {result.get('path')}. What's next?")
                if resp:
                    conversation.append({'role': 'assistant', 'content': resp})
                return result
            except: pass
        return {'error': 'Could not parse file request'}

    # Search files
    if intent == 'search':
        query = user_input.replace('search', '').replace('find', '').replace('look for', '').strip()
        result = search_brain(query)
        files = result.get('files', result.get('matches', []))[:5]
        file_names = [f.get('name', f) if isinstance(f, dict) else str(f) for f in files]
        resp = stream_response(f"Found {result.get('count', 0)} files: {', '.join(file_names)}")
        if resp:
            conversation.append({'role': 'assistant', 'content': resp})
        return result

    # Deep think
    if intent == 'deep_think':
        question = user_input.replace('think deep', '').replace('analyze', '').strip()
        result = deep_think(question)
        if result.get('reasoning'):
            print(f"Marcos: {result['reasoning'][:800]}")
            conversation.append({'role': 'assistant', 'content': result['reasoning'][:800]})
            resp = stream_response("That's my analysis. Questions?")
            if resp:
                conversation.append({'role': 'assistant', 'content': resp})
        elif result.get('error'):
            resp = stream_response(f"Thinking failed: {result.get('error')}")
            if resp:
                conversation.append({'role': 'assistant', 'content': resp})
        return result

    # Execute task
    if intent == 'execute':
        result = execute_task(user_input)
        if result.get('error'):
            resp = stream_response(f"Execution failed: {result.get('error')}")
        else:
            created = result.get('created', [])
            edited = result.get('edited', [])
            resp = stream_response(f"Done. Created: {created}. Edited: {edited}")
        if resp:
            conversation.append({'role': 'assistant', 'content': resp})
        return result

    # Questions and conversation - direct model response
    resp = stream_response(user_input)
    if resp:
        conversation.append({'role': 'assistant', 'content': resp})
    return None

# =============================================================================
# MAIN LOOP
# =============================================================================
def chat():
    global convo_memory, BRAIN_SERVER_ONLINE
    convo_memory = load_conversation_memory()
    convo_memory["sessions"] = convo_memory.get("sessions", 0) + 1
    save_conversation_memory(convo_memory)

    # Check brain_server
    try:
        requests.get(f'{brain_url}/status', timeout=3)
        BRAIN_SERVER_ONLINE = True
    except:
        BRAIN_SERVER_ONLINE = False

    # Startup message
    print(f"Marcos online. Session #{convo_memory['sessions']}")

    if not BRAIN_SERVER_ONLINE:
        print("(brain_server offline - file operations limited)")

    # Memory stats
    try:
        mem_stats = opus_memory.get_full_stats()
        facts_count = mem_stats.get('total_facts', len(convo_memory.get('key_facts', [])))
        convos_count = mem_stats.get('total_conversations', 0)
        projects_count = len(convo_memory.get('ongoing_projects', []))
        print(f"Memory: {facts_count} facts | {convos_count} convos | {projects_count} projects")
    except:
        print(f"Memory: {len(convo_memory.get('key_facts', []))} facts | {len(convo_memory.get('ongoing_projects', []))} projects")

    print("Say 'help' for commands.")
    print()

    conversation = []

    while True:
        try:
            user_input = input("Hugo: ").strip()
        except (KeyboardInterrupt, EOFError):
            if conversation:
                try:
                    opus_memory.archive_conversation(conversation, convo_memory["sessions"])
                    print("\n📚 Conversation archived.")
                except: pass
            print("Goodbye.")
            break

        if not user_input:
            continue

        if user_input.lower() in ['exit', 'quit', 'bye']:
            save_conversation_memory(convo_memory)
            if conversation:
                try:
                    opus_memory.archive_conversation(conversation, convo_memory["sessions"])
                    print("📚 Conversation archived.")
                except: pass
            print("Goodbye.")
            break

        # Detect intent
        intent = detect_intent(user_input)

        # Track user message
        conversation.append({'role': 'user', 'content': user_input})
        if len(conversation) > 30:
            conversation = conversation[-30:]

        # Route and execute
        route_and_execute(user_input, intent, conversation)

        print()

if __name__ == '__main__':
    chat()
