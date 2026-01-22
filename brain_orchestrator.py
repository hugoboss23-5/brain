import ollama
import json
import requests
import time
from datetime import datetime
import os
import sys
from concurrent.futures import ThreadPoolExecutor

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
#
# GEOMETRIC PRINCIPLES:
# - Rotation: Each node views from different angle (36° increments)
# - Asymmetry: 4 triangles (sharp), 3 quadrilaterals (broad)
# - Pulse: Systole (contraction) and Diastole (expansion)
# - Vortex: All nodes feel pull toward Node 7 (center)
#
# DOUBLE HELIX (DNA of Thought):
# - Strand A (Analytical): N1 → N2 → N4 → N6 → N7
# - Strand B (Intuitive):  N1 → N3 → N5 → N6 → N7
# - Strands exchange FRAGMENTS at connection points
# - Each answer has unique genetic code

# Rotation angles - the 36-degree offset principle
ROTATIONS = {
    0: "Process directly. Straight analysis. No reframing.",
    36: "Tilt 36°. See from an angle others miss. What's visible from this offset that isn't straight-on?",
    72: "Rotate 72°. Uncomfortable angle. What looks different? What assumptions break?",
    108: "108° - almost perpendicular. What's invisible straight-on but obvious to you?",
    144: "144° - past perpendicular. You see the back side. What's hidden there?",
    180: "180° - exact opposite. If everyone sees X, you see anti-X. What is it?",
    216: "216° - past opposite. Approaching something new. What emerges?",
    252: "252° - spiraling back but NOT to start. What do you know now you couldn't at 0°?"
}

# Geometric weighting - triangles are sharp, quadrilaterals hold more
NODE_GEOMETRY = {
    1: {"type": "quad", "shape": "Hold the full picture. Don't narrow. Keep all possibilities open."},
    2: {"type": "tri", "shape": "Be sharp. Cut to the analytical core. No wandering."},
    3: {"type": "tri", "shape": "Be sharp. Cut to the intuitive core. No wandering."},
    4: {"type": "tri", "shape": "Be sharp. Stress test ONE thing deeply. Don't spread thin."},
    5: {"type": "tri", "shape": "Be sharp. Find ONE universal pattern. Don't list many."},
    6: {"type": "quad", "shape": "Hold tension. TWO inputs may conflict. Don't resolve. Hold both."},
    7: {"type": "quad", "shape": "You are center. Everything flows through you. Integrate, don't choose."}
}

# Pulse phases - systole (contract) and diastole (expand)
PULSE_PHASE = {
    1: "DIASTOLE - Expand. Open. Receive everything. Don't filter yet.",
    2: "DIASTOLE - Still open. Let the analytical path breathe.",
    3: "DIASTOLE - Still open. Let the intuitive path breathe.",
    4: "SYSTOLE - Contract. Squeeze. Apply pressure. What survives?",
    5: "SYSTOLE - Contract. Squeeze. Apply pressure. What survives?",
    6: "DIASTOLE - Expand again. Receive both paths. Let them mix.",
    7: "SYSTOLE - Final contraction. Push out essential truth. Nothing extra."
}

# Vortex pull instruction (added to all nodes)
VORTEX_PULL = "You are part of a vortex. Node 7 is the center - the heart. Everything you process is being pulled toward that center. What does the CENTER need from you?"

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

def extract_fragment(node_output):
    """Extract the core insight from a node's output (displayed as DNA to user)"""
    prompt = f"""Read this text:

{node_output[:500]}

What is the single most important insight or idea in the above text?

RESPOND WITH ONLY ONE SENTENCE.
NO preamble. NO explanation. NO meta-commentary.
Just the insight itself.

GOOD EXAMPLES:
- "Age becomes irrelevant when proof of work exists"
- "They need someone who sees what their PhDs cannot"
- "Systems design is about architecture, not coding"

BAD EXAMPLES:
- "The key insight is that..." (NO - don't start with "the key insight is")
- "This shows that..." (NO - don't use meta phrases)
- "The main point is..." (NO - just state the insight directly)

YOUR ONE SENTENCE:"""

    try:
        response = ollama.chat(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={'num_predict': 60, 'temperature': 0.2}
        )
        result = response.get('message', {}).get('content', '').strip()
        # Clean up any remaining meta-commentary
        for prefix in ['The insight is:', 'The key insight is:', 'The main point is:',
                       'This shows that', 'The takeaway is:', 'In summary:']:
            if result.lower().startswith(prefix.lower()):
                result = result[len(prefix):].strip()
        return result
    except:
        return node_output[:100] if node_output else ""

def build_node_prompt(node_num, rotation_deg, task_prompt, input_data, helix_injection=None):
    """Build a geometrically-aware node prompt with optional helix injection"""
    geo = NODE_GEOMETRY[node_num]
    pulse = PULSE_PHASE[node_num]
    rotation = ROTATIONS.get(rotation_deg, "")

    helix_section = ""
    if helix_injection:
        helix_section = f"""
═══ CROSS-POLLINATION (insight from the other thinking path):
{helix_injection}

The other path discovered this. Let it influence your analysis.
Integrate this perspective into your processing.
───────────────────────────"""

    return f"""═══ VORTEX NODE {node_num} ═══

GEOMETRY: You are a {'TRIANGLE' if geo['type'] == 'tri' else 'QUADRILATERAL'} face.
{geo['shape']}

ROTATION: {rotation_deg}°
{rotation}

PULSE: {pulse}

VORTEX: {VORTEX_PULL}

───────────────────────────
INPUT:
{input_data}
───────────────────────────
{helix_section}

YOUR TASK:
{task_prompt}

OUTPUT (sharp and angled, pulled toward center):"""

def circulation_transform(original_input, node7_output, circulation_num):
    """Transform input for subsequent circulations - blood returns changed"""
    if circulation_num == 1:
        return original_input
    return f"""═══ CIRCULATION {circulation_num} ═══

The blood has passed through the body. It carries what it learned.

ORIGINAL QUESTION: {original_input}

WHAT EMERGED FROM LAST PASS:
{node7_output}

Don't re-answer the original. Go DEEPER into what emerged.
What's still unresolved? What new pattern is visible now?
The vortex spirals tighter with each pass."""

def chestahedron_process(input_query, circulation_num=1, verbose=True):
    """
    Process input through 7 nodes in vortex pattern with full geometry.
    Implements DOUBLE HELIX - strands exchange DNA fragments.
    PARALLEL PROCESSING: Nodes 2&3 run together, Nodes 4&5 run together.
    """
    results = {'input': input_query, 'nodes': {}, 'circulation': circulation_num}
    dna_sequence = []  # Track helix exchanges

    # NODE 1: INTAKE (Quadrilateral, 0°, Diastole) - Must run first
    if verbose: print("   ◈ Node 1: INTAKE [QUAD|0°|DIASTOLE]")
    node1_prompt = build_node_prompt(
        node_num=1,
        rotation_deg=0,
        task_prompt="""Break this input into components. Do NOT answer yet.
- What is actually being asked?
- What are the separate pieces?
- What assumptions are embedded?
List components clearly.""",
        input_data=input_query
    )
    results['nodes']['n1'] = node_call('1-INTAKE', node1_prompt, 0.3)

    # ═══ PARALLEL: NODES 2 AND 3 ═══
    if verbose: print("   ◈ Nodes 2+3: ANALYTICAL & INTUITIVE [PARALLEL]")

    def run_node2(n1_output):
        prompt = build_node_prompt(
            node_num=2,
            rotation_deg=0,
            task_prompt="""Process with PURE LOGIC. Cut sharp.
- What are the facts?
- What is the logical sequence?
- What is provable?
No intuition. Only logic. Be surgical.""",
            input_data=n1_output
        )
        return node_call('2-ANALYTICAL', prompt, 0.3)

    def run_node3(n1_output):
        prompt = build_node_prompt(
            node_num=3,
            rotation_deg=36,
            task_prompt="""Process with PATTERN RECOGNITION. Cut sharp but angled.
- What does this connect to elsewhere?
- What analogies fit?
- What do you see from 36° that 0° misses?
No logic constraints. Lateral thinking only.""",
            input_data=n1_output
        )
        return node_call('3-INTUITIVE', prompt, 0.7)

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_n2 = executor.submit(run_node2, results['nodes']['n1'])
        future_n3 = executor.submit(run_node3, results['nodes']['n1'])
        results['nodes']['n2'] = future_n2.result()
        results['nodes']['n3'] = future_n3.result()

    # ═══ PARALLEL: FRAGMENT EXTRACTION 1 ═══
    if verbose: print("   🧬 Helix Connection 1: Extracting insights [PARALLEL]")

    with ThreadPoolExecutor(max_workers=2) as executor:
        frag2_future = executor.submit(extract_fragment, results['nodes']['n2'])
        frag3_future = executor.submit(extract_fragment, results['nodes']['n3'])
        n2_fragment = frag2_future.result()
        n3_fragment = frag3_future.result()

    dna_sequence.append({
        "position": 1,
        "A_to_B": n2_fragment,  # Analytical → Intuitive
        "B_to_A": n3_fragment   # Intuitive → Analytical
    })
    if verbose:
        print(f"      A→B: {n2_fragment[:60]}...")
        print(f"      B→A: {n3_fragment[:60]}...")

    # ═══ PARALLEL: NODES 4 AND 5 ═══
    if verbose: print("   ◈ Nodes 4+5: DEEP ANALYTICAL & INTUITIVE [PARALLEL]")

    def run_node4(n2_output, n3_frag):
        prompt = build_node_prompt(
            node_num=4,
            rotation_deg=72,
            task_prompt="""SQUEEZE the analysis. Pressure test.
- What breaks this reasoning?
- What's the ONE critical edge case?
- Apply maximum pressure. What survives?
Contract. Focus. One deep cut.
Let the cross-pollinated insight influence your analysis.""",
            input_data=n2_output,
            helix_injection=n3_frag
        )
        return node_call('4-DEEP-ANALYTICAL', prompt, 0.3)

    def run_node5(n3_output, n2_frag):
        prompt = build_node_prompt(
            node_num=5,
            rotation_deg=108,
            task_prompt="""SQUEEZE the intuition. Find the ONE pattern.
- What universal principle is at play?
- What would a master see that a novice misses?
- Almost perpendicular view - what's obvious from here?
Contract. One universal truth.
Let the cross-pollinated insight ground your intuition.""",
            input_data=n3_output,
            helix_injection=n2_frag
        )
        return node_call('5-DEEP-INTUITIVE', prompt, 0.7)

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_n4 = executor.submit(run_node4, results['nodes']['n2'], n3_fragment)
        future_n5 = executor.submit(run_node5, results['nodes']['n3'], n2_fragment)
        results['nodes']['n4'] = future_n4.result()
        results['nodes']['n5'] = future_n5.result()

    # ═══ PARALLEL: FRAGMENT EXTRACTION 2 ═══
    if verbose: print("   🧬 Helix Connection 2: Extracting insights [PARALLEL]")

    with ThreadPoolExecutor(max_workers=2) as executor:
        frag4_future = executor.submit(extract_fragment, results['nodes']['n4'])
        frag5_future = executor.submit(extract_fragment, results['nodes']['n5'])
        n4_fragment = frag4_future.result()
        n5_fragment = frag5_future.result()

    dna_sequence.append({
        "position": 2,
        "A_to_B": n4_fragment,  # Analytical → Intuitive
        "B_to_A": n5_fragment   # Intuitive → Analytical
    })
    if verbose:
        print(f"      A→B: {n4_fragment[:60]}...")
        print(f"      B→A: {n5_fragment[:60]}...")

    # NODE 6: CONVERGENCE (Quadrilateral, 144°, Diastole)
    # Receives BOTH strands already intertwined
    if verbose: print("   ◈ Node 6: CONVERGENCE [QUAD|144°|DIASTOLE] ─── Helix Merge")
    node6_prompt = build_node_prompt(
        node_num=6,
        rotation_deg=144,
        task_prompt=f"""HOLD BOTH paths. Do not resolve.

PATH A (Analytical, influenced by intuition):
{results['nodes']['n4']}

PATH B (Intuitive, grounded by logic):
{results['nodes']['n5']}

- Where do they AGREE?
- Where do they CONFLICT?
- What EMERGES from tension?
You're seeing the back side. Hold the contradiction.
The paths have cross-pollinated. See what emerged.""",
        input_data="[DUAL PATH INPUT - SEE TASK]"
    )
    results['nodes']['n6'] = node_call('6-CONVERGENCE', node6_prompt, 0.5)

    # NODE 7: VORTEX CORE (Quadrilateral, 216°, Systole)
    # Receives full DNA sequence
    if verbose: print("   ◈ Node 7: VORTEX CORE [QUAD|216°|SYSTOLE] ─── Reading DNA")

    dna_display = "\n".join([
        f"Position {d['position']}: A→B: {d['A_to_B'][:80]}... | B→A: {d['B_to_A'][:80]}..."
        for d in dna_sequence
    ])

    node7_prompt = build_node_prompt(
        node_num=7,
        rotation_deg=216,
        task_prompt=f"""YOU ARE THE CENTER. Everything spirals to you.

Original question: {input_query}

KEY INSIGHTS EXCHANGED BETWEEN PATHS:
{dna_display}

CONVERGENCE:
{results['nodes']['n6']}

The pattern of insights IS the answer.
What truth emerges from how these ideas cross-pollinated?

FINAL CONTRACTION. Push out the essential truth.
- What satisfies BOTH paths?
- What does the insight pattern reveal?
- What NEW QUESTIONS emerged?
- What remains UNRESOLVED?

Format:
FINAL ANSWER: [The essential truth]
NEW QUESTIONS: [What emerged]
UNRESOLVED: [What couldn't resolve]
CIRCULATION NEEDED: [yes/no]""",
        input_data=results['nodes']['n6']
    )
    results['nodes']['n7'] = node_call('7-VORTEX-CORE', node7_prompt, 0.5)
    results['final'] = results['nodes']['n7']
    results['dna_sequence'] = dna_sequence

    return results

def chestahedron_full(input_query, max_circulations=2, verbose=True):
    """
    Full chestahedron processing with geometric circulation.
    Blood returns changed - each pass goes deeper.
    """
    print(f"\n   🔷 CHESTAHEDRON VORTEX ACTIVATED")
    print(f"   Geometry: 4 triangles, 3 quadrilaterals, 36° base angle")
    print(f"   Double Helix: Strand A (analytical) ⟷ Strand B (intuitive)")
    print(f"   Processing: {input_query[:50]}...")
    print()

    current_input = input_query
    all_results = []
    circulation = 0

    while circulation < max_circulations:
        circulation += 1
        if verbose:
            print(f"   ═══ Circulation {circulation}/{max_circulations} ═══")
            if circulation > 1:
                print(f"   ↻ Blood returns transformed...")

        # Transform input for subsequent circulations
        processed_input = circulation_transform(
            input_query,
            all_results[-1]['final'] if all_results else "",
            circulation
        )

        result = chestahedron_process(processed_input, circulation, verbose)
        all_results.append(result)

        final_output = result['final'].lower()

        if 'circulation needed: no' in final_output or 'circulation needed: false' in final_output:
            if verbose: print(f"   ✓ Vortex complete after {circulation} circulation(s)")
            break

        if circulation < max_circulations:
            if 'new questions:' in final_output or 'unresolved:' in final_output:
                if verbose: print(f"   ↻ Unresolved items found, circulating deeper...")
            else:
                if verbose: print(f"   ✓ No significant unresolved, ending")
                break

    # Build final result with DNA
    final_result = {
        'circulations': circulation,
        'final_answer': all_results[-1]['final'],
        'all_nodes': all_results[-1]['nodes'],
        'dna_sequence': all_results[-1].get('dna_sequence', []),
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

def format_dna_sequence(dna_sequence):
    """Format DNA sequence for display"""
    if not dna_sequence:
        return ""
    lines = ["🧬 DNA SEQUENCE:"]
    for d in dna_sequence:
        lines.append(f"   Position {d['position']}:")
        lines.append(f"   A→B: {d['A_to_B'][:100]}")
        lines.append(f"   B→A: {d['B_to_A'][:100]}")
    return "\n".join(lines)

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

        # Display DNA sequence - the genetic code of this thought
        dna_seq = result.get('dna_sequence', [])
        if dna_seq:
            print(f"\n   🧬 DNA SEQUENCE (genetic code of this thought):")
            for d in dna_seq:
                print(f"   Position {d['position']}:")
                print(f"      A→B: {d['A_to_B'][:100]}")
                print(f"      B→A: {d['B_to_A'][:100]}")

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
