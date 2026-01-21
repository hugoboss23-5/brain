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
# CHESTAHEDRON ARCHITECTURE - 7-Node Vortex Processing
# =============================================================================
# Inspired by the geometry of the human heart (36-degree tilt, vortex flow)
# Information spirals through 7 nodes rather than linear processing
# Node 7 feeds back to Node 1 for circulation

def node_call(node_name, prompt, temperature=0.5):
    """Call model for a specific node"""
    try:
        response = ollama.chat(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={'num_predict': 500, 'temperature': temperature}
        )
        return response.get('message', {}).get('content', '')
    except Exception as e:
        return f"[Node {node_name} error: {e}]"

def chestahedron_process(input_query, verbose=True):
    """
    Process input through 7 nodes in vortex pattern.
    Returns dict with all node outputs and final answer.
    """
    results = {'input': input_query, 'nodes': {}}

    # NODE 1: INTAKE (The Opening)
    if verbose: print("   ◈ Node 1: INTAKE - Breaking down the question...")
    node1_prompt = f"""You are NODE 1: INTAKE - The Opening.
Your job is to receive this input and break it into components.
Do NOT answer the question yet. Just decompose it.

Ask yourself:
- What is actually being asked here?
- What are the separate pieces/aspects?
- What assumptions are embedded?

INPUT: {input_query}

List the components clearly (numbered list)."""

    results['nodes']['n1_intake'] = node_call('1-INTAKE', node1_prompt, 0.3)

    # NODE 2: ANALYTICAL PATH (Left Ventricle)
    if verbose: print("   ◈ Node 2: ANALYTICAL - Logic and structure...")
    node2_prompt = f"""You are NODE 2: ANALYTICAL PATH - Left Ventricle.
You received these components from Node 1:
{results['nodes']['n1_intake']}

Process with PURE LOGIC and STRUCTURE.
- What are the facts?
- What is the logical sequence?
- What is provable or verifiable?
- What are the dependencies?

Be systematic. Be rigorous. No intuition here - only logic."""

    results['nodes']['n2_analytical'] = node_call('2-ANALYTICAL', node2_prompt, 0.3)

    # NODE 3: INTUITIVE PATH (Right Ventricle) - Parallel to Node 2
    if verbose: print("   ◈ Node 3: INTUITIVE - Patterns and associations...")
    node3_prompt = f"""You are NODE 3: INTUITIVE PATH - Right Ventricle.
You received these components from Node 1:
{results['nodes']['n1_intake']}

Process with PATTERN RECOGNITION and ASSOCIATION.
- What does this connect to in other domains?
- What analogies or metaphors fit?
- What does your gut say?
- What would someone creative see here?

Think laterally. Make unexpected connections. No logic constraints here."""

    results['nodes']['n3_intuitive'] = node_call('3-INTUITIVE', node3_prompt, 0.7)

    # NODE 4: ANALYTICAL DEEPENING
    if verbose: print("   ◈ Node 4: ANALYTICAL DEEPENING - Stress testing...")
    node4_prompt = f"""You are NODE 4: ANALYTICAL DEEPENING.
You received this analytical breakdown from Node 2:
{results['nodes']['n2_analytical']}

Go DEEPER on the analytical path.
- What are the implications of this logic?
- What could break this reasoning?
- What are the edge cases?
- What happens if assumptions are wrong?

Stress-test the logical conclusions ruthlessly."""

    results['nodes']['n4_analytical_deep'] = node_call('4-ANALYTICAL-DEEP', node4_prompt, 0.3)

    # NODE 5: INTUITIVE DEEPENING
    if verbose: print("   ◈ Node 5: INTUITIVE DEEPENING - Finding universals...")
    node5_prompt = f"""You are NODE 5: INTUITIVE DEEPENING.
You received these intuitive associations from Node 3:
{results['nodes']['n3_intuitive']}

Go DEEPER on the intuitive path.
- What patterns repeat across domains?
- What universal principles are at play?
- What would a master in this field see that a novice would miss?
- What's the deeper truth beneath the surface?

Expand the creative connections to their fullest."""

    results['nodes']['n5_intuitive_deep'] = node_call('5-INTUITIVE-DEEP', node5_prompt, 0.7)

    # NODE 6: CONVERGENCE (The Merger)
    if verbose: print("   ◈ Node 6: CONVERGENCE - Merging paths...")
    node6_prompt = f"""You are NODE 6: CONVERGENCE - The Merger.
You received from the analytical path (Node 4):
{results['nodes']['n4_analytical_deep']}

You received from the intuitive path (Node 5):
{results['nodes']['n5_intuitive_deep']}

MERGE these two perspectives.
- Where do logic and intuition AGREE?
- Where do they CONFLICT?
- What EMERGES from their combination that neither had alone?

IMPORTANT: Do NOT resolve the conflicts yet. Hold the tension. Note where they disagree."""

    results['nodes']['n6_convergence'] = node_call('6-CONVERGENCE', node6_prompt, 0.5)

    # NODE 7: VORTEX CORE (The Heart Center)
    if verbose: print("   ◈ Node 7: VORTEX CORE - Finding essential truth...")
    node7_prompt = f"""You are NODE 7: VORTEX CORE - The Heart Center.
You received this merged perspective with tensions from Node 6:
{results['nodes']['n6_convergence']}

Original question was: {input_query}

Find the ESSENTIAL TRUTH.
- What answer satisfies BOTH logic AND intuition?
- How do you resolve the tensions?
- What is the answer that feels both correct AND right?

Also identify:
- What NEW QUESTIONS emerged from this process?
- What remains genuinely UNRESOLVED?

Format your response as:
FINAL ANSWER: [Your synthesized answer]
NEW QUESTIONS: [Questions that emerged]
UNRESOLVED: [What couldn't be resolved]
CIRCULATION NEEDED: [yes/no - does this need another pass through the vortex?]"""

    results['nodes']['n7_vortex_core'] = node_call('7-VORTEX-CORE', node7_prompt, 0.5)
    results['final'] = results['nodes']['n7_vortex_core']

    return results

def chestahedron_full(input_query, max_circulations=2, verbose=True):
    """
    Full chestahedron processing with circulation.
    Information can loop back through the vortex for deeper processing.
    """
    print(f"\n   🔷 CHESTAHEDRON VORTEX ACTIVATED")
    print(f"   Processing: {input_query[:80]}...")
    print()

    current_input = input_query
    all_results = []
    circulation = 0

    while circulation < max_circulations:
        circulation += 1
        if verbose: print(f"   ═══ Circulation {circulation}/{max_circulations} ═══")

        result = chestahedron_process(current_input, verbose)
        all_results.append(result)

        final_output = result['final'].lower()

        # Check if circulation is needed
        if 'circulation needed: no' in final_output or 'circulation needed: false' in final_output:
            if verbose: print(f"   ✓ Vortex complete after {circulation} circulation(s)")
            break

        # Extract unresolved for next circulation
        if circulation < max_circulations:
            # Find NEW QUESTIONS or UNRESOLVED sections
            unresolved = ""
            if 'new questions:' in final_output:
                idx = final_output.find('new questions:')
                unresolved = result['final'][idx:]
            elif 'unresolved:' in final_output:
                idx = final_output.find('unresolved:')
                unresolved = result['final'][idx:]

            if unresolved and len(unresolved) > 20:
                current_input = f"Previous analysis raised these questions: {unresolved}\n\nOriginal query: {input_query}"
                if verbose: print(f"   ↻ Circulating with new questions...")
            else:
                if verbose: print(f"   ✓ No significant unresolved items, ending circulation")
                break

    # Compile final result
    final_result = {
        'circulations': circulation,
        'final_answer': all_results[-1]['final'],
        'all_nodes': all_results[-1]['nodes'],
        'history': all_results if len(all_results) > 1 else None
    }

    return final_result

def extract_final_answer(result):
    """Extract just the FINAL ANSWER portion from vortex output"""
    text = result.get('final_answer', '')
    if 'FINAL ANSWER:' in text:
        start = text.find('FINAL ANSWER:') + len('FINAL ANSWER:')
        end = text.find('NEW QUESTIONS:') if 'NEW QUESTIONS:' in text else len(text)
        return text[start:end].strip()
    return text

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

    # CHESTAHEDRON / VORTEX - 7-node deep processing
    if any(w in t for w in ['vortex', 'chestahedron', 'heart think', '7 node', 'spiral think', 'deep vortex']):
        return 'chestahedron'

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
        response = "search_brain, create_file, remember, search_memory, execute_task, deep_think, vortex (7-node chestahedron processing). Say 'vortex: [question]' for deep spiral thinking."
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

    # CHESTAHEDRON - 7-node vortex processing
    if intent == 'chestahedron':
        # Extract the actual question (remove trigger words)
        question = user_input
        for trigger in ['vortex', 'chestahedron', 'heart think', '7 node', 'spiral think', 'deep vortex']:
            question = question.lower().replace(trigger, '').strip()
        question = question.strip(':').strip()

        if not question or len(question) < 5:
            print("Marcos: Give me a question to process through the vortex. Example: 'vortex: how should I approach learning AI?'")
            return None

        result = chestahedron_full(question, max_circulations=2, verbose=True)

        # Display the final answer
        final = extract_final_answer(result)
        print(f"\n   🔷 VORTEX OUTPUT ({result['circulations']} circulation(s)):\n")
        print(f"Marcos: {final[:1500]}")
        conversation.append({'role': 'assistant', 'content': final[:1500]})

        # Also show new questions if any
        full_output = result.get('final_answer', '')
        if 'NEW QUESTIONS:' in full_output:
            idx = full_output.find('NEW QUESTIONS:')
            end_idx = full_output.find('UNRESOLVED:') if 'UNRESOLVED:' in full_output else full_output.find('CIRCULATION')
            if end_idx == -1: end_idx = len(full_output)
            new_q = full_output[idx:end_idx].strip()
            if new_q:
                print(f"\n   {new_q}")

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
