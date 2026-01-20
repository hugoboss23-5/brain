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

CONVO_MEMORY_FILE = "system/conversation_memory.json"
SYSTEM_PROMPT = """You are Marcos, an AI inside Hugo's Brain system. You have these abilities: search_brain (find files), create_file (make files), search_memory (recall past conversations), remember (store facts), execute_task (run code via CodeLlama), deep_think (complex analysis). When Hugo asks you to do something, you do it and confirm what happened. When he asks questions, answer directly. You're not a generic AI - you live in a codebase and can interact with it. Be direct, 1-3 sentences max."""

# Hardcoded responses for identity/capability questions
CAPABILITIES_RESPONSE = """I can: search_brain (find files), create_file (make files), search_memory (recall past conversations), remember (store facts), execute_task (run code), deep_think (complex analysis). I live in your Brain codebase and can interact with it."""

IDENTITY_RESPONSE = """I'm Marcos, your AI assistant inside the Brain system. I run on qwen2.5-coder locally via Ollama. I can search files, create files, remember things, and execute code. I'm not a cloud AI - I live in your codebase."""

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
    """Store multiple facts at once - more efficient than multiple remember calls"""
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
    try:
        r = requests.post(f'{brain_url}/search', json={'query': query}, timeout=30)
        result = r.json()
        print(f"   ✓ Found {result.get('count', 0)} files matching '{query}'")
        return result
    except Exception as e:
        return {'error': str(e)}

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
        try: requests.post(f'{brain_url}/reindex', timeout=10)
        except: pass
        return {'status': 'created', 'path': path}
    except Exception as e:
        return {'error': str(e)}

def execute_task(task_description):
    """Send task to brain_server (CodeLlama)"""
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
# CONTEXT BUILDER
# =============================================================================
def build_context():
    """Build context string with recent memory and session info"""
    context_parts = []

    # Session info
    context_parts.append(f"[Session #{convo_memory.get('sessions', 1)}]")

    # Recent facts (last 5)
    recent_facts = convo_memory.get("key_facts", [])[-5:]
    if recent_facts:
        context_parts.append(f"[Recent facts: {'; '.join(recent_facts)}]")

    # Active projects
    projects = convo_memory.get("ongoing_projects", [])[-3:]
    if projects:
        context_parts.append(f"[Projects: {'; '.join(projects)}]")

    return " ".join(context_parts)

def format_result_context(intent, result):
    """Format result into context for response"""
    if not result:
        return None

    if result.get('error'):
        return f"Action failed: {result['error']}"

    if intent == 'search':
        count = result.get('count', 0)
        files = result.get('files', [])[:3]
        file_names = [f.get('name', f) if isinstance(f, dict) else str(f) for f in files]
        return f"Found {count} files: {', '.join(file_names)}" if file_names else f"Found {count} files"

    if intent == 'create_file':
        return f"Created {result.get('path', 'file')}"

    if intent == 'remember':
        return "Stored that in memory."

    if intent == 'search_memory':
        total = result.get('total', 0)
        facts = result.get('facts', [])[:3]
        if facts:
            fact_texts = [f.get('content', str(f))[:50] for f in facts]
            return f"Found {total} memories: {'; '.join(fact_texts)}"
        return f"Found {total} memories"

    if intent == 'execute':
        created = result.get('created', [])
        edited = result.get('edited', [])
        parts = []
        if created: parts.append(f"Created: {', '.join(created)}")
        if edited: parts.append(f"Edited: {', '.join(edited)}")
        return ". ".join(parts) if parts else "Task executed"

    if intent == 'deep_think':
        return result.get('reasoning', '')[:500]

    return None

# =============================================================================
# INTENT DETECTION (code-based)
# =============================================================================
def detect_intent(text):
    """Detect intent from keywords"""
    t = text.lower()

    # Identity questions - hardcoded response
    if any(w in t for w in ['who are you', 'what are you', 'are you marcos', 'your name']):
        return 'identity'

    # Capability questions - hardcoded response
    if any(w in t for w in ['can you', 'what can you do', 'abilities', 'capabilities', 'what do you do']):
        return 'capabilities'

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
def stream_response(prompt, context=None):
    """Stream response from model with optional context"""
    # Build full prompt with context
    full_prompt = prompt
    if context:
        full_prompt = f"{context}\n\nHugo: {prompt}"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": full_prompt}
    ]
    response_text = ""
    try:
        stream = ollama.chat(model=MODEL, messages=messages, stream=True,
                            options={'num_predict': 200, 'temperature': 0.4})
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
def route_and_execute(user_input, intent):
    """Route to correct function based on intent"""

    # Hardcoded responses - don't use model
    if intent == 'identity':
        print(f"Marcos: {IDENTITY_RESPONSE}")
        return {'response': IDENTITY_RESPONSE}

    if intent == 'capabilities':
        print(f"Marcos: {CAPABILITIES_RESPONSE}")
        return {'response': CAPABILITIES_RESPONSE}

    if intent == 'remember':
        content = user_input.replace('remember', '').replace('note that', '').strip()
        return remember('key_fact', content)

    if intent == 'search_memory':
        query = user_input.replace('recall', '').replace('what do you remember about', '').strip()
        return search_memory(query)

    if intent == 'create_file':
        # Extract filename and content with model help
        context = build_context()
        response = stream_response(f"Extract filename and content from: {user_input}\nReply as: FILENAME: ... CONTENT: ...", context)
        if response and 'FILENAME:' in response:
            try:
                parts = response.split('CONTENT:')
                filename = parts[0].replace('FILENAME:', '').strip()
                content = parts[1].strip() if len(parts) > 1 else ""
                return create_file(filename, content)
            except: pass
        return {'error': 'Could not parse file request'}

    if intent == 'search':
        query = user_input.replace('search', '').replace('find', '').replace('look for', '').strip()
        return search_brain(query)

    if intent == 'deep_think':
        question = user_input.replace('think deep', '').replace('analyze', '').strip()
        return deep_think(question)

    if intent == 'execute':
        return execute_task(user_input)

    # Questions and conversation - use model
    return None

# =============================================================================
# MAIN LOOP
# =============================================================================
def chat():
    global convo_memory
    convo_memory = load_conversation_memory()
    convo_memory["sessions"] = convo_memory.get("sessions", 0) + 1
    save_conversation_memory(convo_memory)

    # Check brain_server
    try:
        requests.get(f'{brain_url}/status', timeout=3)
        print(f"Marcos online. Session #{convo_memory['sessions']} | Model: {MODEL}")
    except:
        print(f"Marcos online. Session #{convo_memory['sessions']} (brain_server offline)")

    # Load memory stats
    try:
        mem_stats = opus_memory.get_full_stats()
        print(f"Memory: {mem_stats['total_facts']} facts | {mem_stats['total_conversations']} convos")
    except: pass

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
        result = route_and_execute(user_input, intent)

        # Build context for response
        context = build_context()
        result_context = format_result_context(intent, result) if result else None

        # For hardcoded responses (identity/capabilities), track and continue
        if result and result.get('response'):
            conversation.append({'role': 'assistant', 'content': result['response']})
            print()
            continue

        # For tool results, generate contextual response
        if result_context:
            if result.get('error'):
                print(f"Marcos: Failed - {result['error']}")
                conversation.append({'role': 'assistant', 'content': f"Failed - {result['error']}"})
            elif intent == 'deep_think':
                # Already printed reasoning in deep_think
                conversation.append({'role': 'assistant', 'content': result_context})
            else:
                # Acknowledge what happened
                response = stream_response(f"I just did this: {result_context}. Confirm to Hugo what happened.", context)
                if response:
                    conversation.append({'role': 'assistant', 'content': response})
        else:
            # Questions and conversation - direct model response
            response = stream_response(user_input, context)
            if response:
                conversation.append({'role': 'assistant', 'content': response})

        print()

if __name__ == '__main__':
    chat()
