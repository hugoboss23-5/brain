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
MODEL = "tinyllama:latest"
THINKER_MODEL = "deepseek-r1:latest"
brain_url = f"http://127.0.0.1:{config['server_port']}"

CONVO_MEMORY_FILE = "system/conversation_memory.json"
SYSTEM_PROMPT = "You are Marcos. Be direct. Answer in 1-2 sentences."

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
# CORE FUNCTIONS (kept from original)
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
# INTENT DETECTION (code-based, not model)
# =============================================================================
def detect_intent(text):
    """Detect intent from keywords"""
    t = text.lower()
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
def stream_response(prompt, check_answer=False, original_question=None):
    """Stream response from tinyllama"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ]
    response_text = ""
    try:
        stream = ollama.chat(model=MODEL, messages=messages, stream=True,
                            options={'num_predict': 150, 'temperature': 0.3})
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

    # CHECK step for questions
    if check_answer and original_question and response_text:
        if not check_response_quality(original_question, response_text):
            print("[retrying with more focus...]")
            return stream_response(f"Be more direct. Actually answer: {original_question}", False)

    return response_text

def check_response_quality(question, response):
    """Ask model if response actually answers the question"""
    if len(response.strip()) < 5:
        return False
    try:
        check = ollama.chat(
            model=MODEL,
            messages=[{"role": "user", "content": f'Does this answer "{question}"?\nResponse: "{response[:200]}"\nReply YES or NO only.'}],
            options={'num_predict': 10, 'temperature': 0.1}
        )
        answer = check.get('message', {}).get('content', '').upper()
        return 'YES' in answer
    except:
        return True

# =============================================================================
# ROUTE AND EXECUTE
# =============================================================================
def route_and_execute(user_input, intent):
    """Route to correct function based on intent"""

    if intent == 'remember':
        # Extract what to remember
        content = user_input.replace('remember', '').replace('note that', '').strip()
        return remember('key_fact', content)

    elif intent == 'search_memory':
        query = user_input.replace('recall', '').replace('what do you remember about', '').strip()
        return search_memory(query)

    elif intent == 'create_file':
        # Try to extract filename and content
        response = stream_response(f"Extract filename and content from: {user_input}\nReply as: FILENAME: ... CONTENT: ...")
        if response and 'FILENAME:' in response:
            try:
                parts = response.split('CONTENT:')
                filename = parts[0].replace('FILENAME:', '').strip()
                content = parts[1].strip() if len(parts) > 1 else ""
                return create_file(filename, content)
            except:
                pass
        return {'error': 'Could not parse file request'}

    elif intent == 'search':
        query = user_input.replace('search', '').replace('find', '').replace('look for', '').strip()
        return search_brain(query)

    elif intent == 'deep_think':
        question = user_input.replace('think deep', '').replace('analyze', '').strip()
        return deep_think(question)

    elif intent == 'execute':
        return execute_task(user_input)

    elif intent == 'question':
        stream_response(user_input, check_answer=True, original_question=user_input)
        return None

    else:  # conversation
        stream_response(user_input)
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
        print(f"Marcos online. Session #{convo_memory['sessions']}")
    except:
        print("Marcos online. (brain_server offline - some features limited)")

    # Load memory stats
    try:
        mem_stats = opus_memory.get_full_stats()
        print(f"Memory: {mem_stats['total_facts']} facts | {mem_stats['total_conversations']} convos")
    except:
        pass

    conversation = []

    while True:
        try:
            user_input = input("Hugo: ").strip()
        except (KeyboardInterrupt, EOFError):
            # Archive conversation
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

        # Track conversation
        conversation.append({'role': 'user', 'content': user_input})
        if len(conversation) > 30:
            conversation = conversation[-30:]

        # Route and execute
        result = route_and_execute(user_input, intent)

        # Show result if any
        if result and isinstance(result, dict):
            if result.get('error'):
                print(f"   ✗ {result['error']}")
            elif result.get('reasoning'):
                print(f"Marcos: {result['reasoning'][:500]}")
                conversation.append({'role': 'assistant', 'content': result['reasoning'][:500]})

        print()

if __name__ == '__main__':
    chat()
