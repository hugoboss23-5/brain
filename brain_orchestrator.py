import anthropic
import json
import requests
from rich.console import Console
from rich.panel import Panel
import time
from datetime import datetime
import os
import hashlib
import re
import sys

# Add system to path for imports
sys.path.insert(0, os.getcwd())
from system.recursive_memory import get_memory

console = Console()

# Initialize Recursive Memory System (RLM-style - remembers EVERYTHING)
opus_memory = get_memory()

with open('brain_config.json', 'r') as f:
    config = json.load(f)

client = anthropic.Anthropic(api_key=config['anthropic_api_key'])
brain_url = f"http://127.0.0.1:{config['server_port']}"

CONVO_MEMORY_FILE = "system/conversation_memory.json"

def load_conversation_memory():
    try:
        if os.path.exists(CONVO_MEMORY_FILE):
            with open(CONVO_MEMORY_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {"sessions": 0, "key_facts": [], "user_preferences": [], "ongoing_projects": []}

def save_conversation_memory(mem):
    os.makedirs(os.path.dirname(CONVO_MEMORY_FILE), exist_ok=True)
    with open(CONVO_MEMORY_FILE, 'w') as f:
        json.dump(mem, f, indent=2)

convo_memory = load_conversation_memory()

class TokenTracker:
    def __init__(self):
        self.tokens_used = 0
        self.session_start = time.time()

    def track(self, input_tokens, output_tokens):
        self.tokens_used += input_tokens + output_tokens

    def get_stats(self):
        uptime = (time.time() - self.session_start) / 60
        return {'tokens_used': self.tokens_used, 'uptime_minutes': round(uptime, 1), 'estimated_cost': f'${self.tokens_used * 0.000015:.4f}'}

tracker = TokenTracker()

# =============================================================================
# TOOL CALL GUARD - Prevents infinite loops
# =============================================================================

class ToolCallGuard:
    """Prevents infinite tool call loops with deduplication, circuit breaker, and result caching"""

    # Patterns that indicate conversational queries - should NOT use tools
    CONVERSATIONAL_PATTERNS = [
        r'\bexplain\b.*\bbrain\b',
        r'\bwhat is brain\b',
        r'\bwhat did we build\b',
        r'\btell (him|her|them|chris|[a-z]+) about\b',
        r'\bshow (him|her|them|chris|[a-z]+)\b',
        r'\bdescribe\b.*\b(brain|system|project)\b',
        r'\bintroduce\b.*\bbrain\b',
        r'\bhow does brain work\b',
        r'\bwhat can (you|brain|opus) do\b',
        r'\bwho are you\b',
        r'\bexplain yourself\b',
        r'\bwhat are you\b',
    ]

    def __init__(self, max_total_calls=15, max_consecutive_same=3, max_recent_signatures=5):
        self.max_total_calls = max_total_calls
        self.max_consecutive_same = max_consecutive_same
        self.max_recent_signatures = max_recent_signatures
        self.reset()

    def reset(self):
        """Reset for new user message"""
        self.total_calls = 0
        self.recent_signatures = []  # Last N call signatures (tool_name + args hash)
        self.result_hashes = {}      # tool_signature -> result_hash
        self.consecutive_same_tool = 0
        self.last_tool_name = None
        self.blocked_reason = None

    def _make_signature(self, tool_name, tool_input):
        """Create unique signature for tool call"""
        input_str = json.dumps(tool_input, sort_keys=True)
        input_hash = hashlib.md5(input_str.encode()).hexdigest()[:8]
        return f"{tool_name}:{input_hash}"

    def _hash_result(self, result):
        """Hash a tool result for comparison"""
        result_str = json.dumps(result, sort_keys=True)
        return hashlib.md5(result_str.encode()).hexdigest()

    def is_conversational_query(self, user_message):
        """Check if message should be answered conversationally without tools"""
        msg_lower = user_message.lower()
        for pattern in self.CONVERSATIONAL_PATTERNS:
            if re.search(pattern, msg_lower):
                console.print(f'[dim]   ℹ Detected conversational query - no tools needed[/dim]')
                return True
        return False

    def should_allow_call(self, tool_name, tool_input):
        """
        Check if tool call should be allowed.
        Returns: (allowed: bool, message: str or None)
        """
        signature = self._make_signature(tool_name, tool_input)

        # Check 1: Total call limit
        if self.total_calls >= self.max_total_calls:
            self.blocked_reason = f"Hit {self.max_total_calls} tool call limit"
            console.print(f'[yellow]   ⚠ CIRCUIT BREAKER: {self.blocked_reason}[/yellow]')
            return False, f"I've hit my tool call limit ({self.max_total_calls} calls). Let me respond with what I have."

        # Check 2: Duplicate call detection
        if signature in self.recent_signatures:
            self.blocked_reason = f"Duplicate call: {tool_name}"
            console.print(f'[yellow]   ⚠ DUPLICATE: Already called {tool_name} with same args[/yellow]')
            return False, "I already tried that exact call. Let me try something different."

        # Check 3: Consecutive same tool limit
        if tool_name == self.last_tool_name:
            self.consecutive_same_tool += 1
            if self.consecutive_same_tool >= self.max_consecutive_same:
                self.blocked_reason = f"Called {tool_name} {self.max_consecutive_same}x consecutively"
                console.print(f'[yellow]   ⚠ CIRCUIT BREAKER: {self.blocked_reason}[/yellow]')
                return False, f"I've called {tool_name} {self.max_consecutive_same} times in a row. Let me use that information to respond."
        else:
            self.consecutive_same_tool = 1

        return True, None

    def record_call(self, tool_name, tool_input, result):
        """Record a tool call after execution"""
        signature = self._make_signature(tool_name, tool_input)
        result_hash = self._hash_result(result)

        # Track signature
        self.recent_signatures.append(signature)
        if len(self.recent_signatures) > self.max_recent_signatures:
            self.recent_signatures.pop(0)

        # Check for identical result to previous call of same tool
        if signature in self.result_hashes:
            if self.result_hashes[signature] == result_hash:
                console.print(f'[yellow]   ⚠ Same result as before - tool output unchanged[/yellow]')

        self.result_hashes[signature] = result_hash
        self.total_calls += 1
        self.last_tool_name = tool_name

    def get_force_response_message(self):
        """Get message to inject when forcing a response"""
        return f"[SYSTEM: Tool limit reached - {self.blocked_reason}. Respond NOW with whatever information you have gathered. Do NOT request more tool calls.]"

    def get_stats(self):
        """Get guard statistics"""
        return {
            'total_calls': self.total_calls,
            'unique_signatures': len(set(self.recent_signatures)),
            'blocked_reason': self.blocked_reason
        }

# Global guard instance
tool_guard = ToolCallGuard()

# =============================================================================
# TOOL FUNCTIONS - Direct server calls
# =============================================================================

def view_brain(operation, path=None):
    """Read file or list directory"""
    # Normalize path - replace spaces, handle None
    if path:
        path = path.replace(' ', '_')
        # Add .txt if no extension and not a directory path
        if operation == 'read_file' and '.' not in os.path.basename(path) and not path.endswith('/'):
            path = path + '.txt'

    for attempt in range(3):
        try:
            r = requests.post(f'{brain_url}/view', json={'operation': operation, 'path': path}, timeout=30)
            result = r.json()

            # Enhanced logging for view_brain results
            if 'error' not in result:
                if operation == 'read_file':
                    content_len = len(result.get('content', ''))
                    console.print(f'[cyan]   ✓ view_brain: Read {path} ({content_len} chars)[/cyan]')
                    if content_len > 0:
                        # Show first 100 chars as preview
                        preview = result.get('content', '')[:100].replace('\n', ' ')
                        console.print(f'[dim]     Preview: {preview}...[/dim]')
                    elif content_len == 0:
                        console.print(f'[yellow]   ⚠ File exists but empty or unreadable[/yellow]')
                elif operation == 'list_directory':
                    items = result.get('items', result.get('files', []))
                    console.print(f'[cyan]   ✓ view_brain: Listed {path or "root"} ({len(items)} items)[/cyan]')
                    if len(items) == 0:
                        console.print(f'[yellow]   ⚠ Directory empty or cached stale - try reindex_brain[/yellow]')
            else:
                console.print(f'[red]   ✗ view_brain error: {result.get("error")}[/red]')

            return result
        except Exception as e:
            if attempt == 2:
                console.print(f'[red]   ✗ view_brain failed after 3 attempts: {e}[/red]')
                return {'error': str(e)}
            time.sleep(1)

def execute_task(task_description):
    """Command EAI (CodeLlama) to create/edit files or run code"""
    try:
        console.print(f'[dim]🤖 EAI working...[/dim]')
        r = requests.post(f'{brain_url}/execute', json={'task_description': task_description}, timeout=120)
        result = r.json()
        if result.get('created'):
            console.print(f'[green]   ✓ Created: {", ".join(result["created"])}[/green]')
        if result.get('edited'):
            console.print(f'[blue]   ✓ Edited: {", ".join(result["edited"])}[/blue]')
        return result
    except requests.exceptions.Timeout:
        return {'error': 'EAI_TIMEOUT: CodeLlama took too long (>120s). Try a simpler task or use create_file for basic file creation.', 'suggestion': 'Use create_file tool instead for simple file creation.'}
    except requests.exceptions.ConnectionError:
        return {'error': 'EAI_OFFLINE: Cannot reach Brain server. Is brain_server.py running?', 'suggestion': 'Start the server with: python brain_server.py'}
    except Exception as e:
        return {'error': f'EAI_ERROR: {str(e)}'}

def deep_think(question, context=None):
    """Consult DeepSeek R1 for complex reasoning"""
    try:
        console.print(f'[dim]🧠 Thinker reasoning...[/dim]')
        payload = {'question': question}
        if context:
            payload['context'] = context
        r = requests.post(f'{brain_url}/think', json=payload, timeout=180)
        result = r.json()
        if result.get('reasoning'):
            console.print(f'[blue]   ✓ Reasoning complete ({len(result["reasoning"])} chars)[/blue]')
        return result
    except requests.exceptions.Timeout:
        return {'error': 'THINKER_TIMEOUT: DeepSeek R1 took too long (>180s). The question may be too complex or the model is busy.', 'suggestion': 'Try breaking down the question into smaller parts.'}
    except requests.exceptions.ConnectionError:
        return {'error': 'THINKER_OFFLINE: Cannot reach Brain server. Is brain_server.py running?'}
    except Exception as e:
        return {'error': f'THINKER_ERROR: {str(e)}'}

def search_brain(query):
    """Search files by name or content without directory traversal"""
    try:
        r = requests.post(f'{brain_url}/search', json={'query': query}, timeout=30)
        result = r.json()
        console.print(f'[cyan]   ✓ Found {result.get("count", 0)} files matching "{query}"[/cyan]')
        return result
    except requests.exceptions.Timeout:
        return {'error': 'SEARCH_TIMEOUT: Search took too long (>30s).'}
    except requests.exceptions.ConnectionError:
        return {'error': 'SEARCH_OFFLINE: Cannot reach Brain server.'}
    except Exception as e:
        return {'error': f'SEARCH_ERROR: {str(e)}'}

def get_context():
    """Get full session context - what you're working on, recent files, cached dirs"""
    try:
        r = requests.get(f'{brain_url}/context', timeout=10)
        result = r.json()
        console.print(f'[cyan]   ✓ Context loaded[/cyan]')
        return result
    except requests.exceptions.Timeout:
        return {'error': 'CONTEXT_TIMEOUT: Server slow to respond.'}
    except requests.exceptions.ConnectionError:
        return {'error': 'SERVER_OFFLINE: Cannot reach Brain server. Is brain_server.py running?'}
    except Exception as e:
        return {'error': f'CONTEXT_ERROR: {str(e)}'}

def check_tools_health():
    """Quick health check - see which tools are online and responsive"""
    console.print(f'[dim]🔍 Checking tool health...[/dim]')
    health = {
        'server': 'OFFLINE',
        'eai': 'UNKNOWN',
        'thinker': 'UNKNOWN',
        'search': 'UNKNOWN',
        'all_ok': False
    }

    # Check server
    try:
        r = requests.get(f'{brain_url}/status', timeout=5)
        if r.status_code == 200:
            health['server'] = 'ONLINE'
            status = r.json()
            health['ollama'] = status.get('ollama', 'unknown')
            health['models'] = status.get('models', [])
            health['tasks_completed'] = status.get('memory', {}).get('tasks', 0)
    except:
        health['server'] = 'OFFLINE'
        console.print(f'[red]   ✗ Server OFFLINE[/red]')
        return health

    # Check search (fast)
    try:
        r = requests.post(f'{brain_url}/search', json={'query': 'test'}, timeout=5)
        health['search'] = 'ONLINE' if r.status_code == 200 else 'ERROR'
    except:
        health['search'] = 'SLOW/OFFLINE'

    # EAI and Thinker status from Ollama
    if health['ollama'] == 'online':
        health['eai'] = 'READY'
        health['thinker'] = 'READY'
    else:
        health['eai'] = 'OLLAMA_OFFLINE'
        health['thinker'] = 'OLLAMA_OFFLINE'

    health['all_ok'] = (health['server'] == 'ONLINE' and health['search'] == 'ONLINE' and health['ollama'] == 'online')

    status_icon = '✓' if health['all_ok'] else '⚠'
    console.print(f'[{"green" if health["all_ok"] else "yellow"}]   {status_icon} Server: {health["server"]} | Ollama: {health.get("ollama", "?")} | Search: {health["search"]}[/{"green" if health["all_ok"] else "yellow"}]')

    return health

def create_file(path, content):
    """
    Directly create a file WITHOUT going through EAI.
    Use this for simple file creation when EAI is slow/busy.
    """
    try:
        # Normalize path: replace spaces with underscores
        path = path.replace(' ', '_')

        # Add .txt extension if no extension provided
        if '.' not in os.path.basename(path):
            path = path + '.txt'

        # Get brain path from config
        full_path = os.path.join(config['brain_path'], path)

        # Create directories if needed
        dir_name = os.path.dirname(full_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        # Write the file
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)

        console.print(f'[green]   ✓ Created: {path} ({len(content)} chars)[/green]')

        # Trigger quick reindex so the file is searchable
        try:
            requests.post(f'{brain_url}/reindex', timeout=10)
            console.print(f'[dim]   ↳ File indexed[/dim]')
        except:
            console.print(f'[dim]   ↳ Run reindex_brain to make searchable[/dim]')

        return {'status': 'created', 'path': path, 'size': len(content)}

    except PermissionError:
        return {'error': f'PERMISSION_DENIED: Cannot write to {path}'}
    except Exception as e:
        return {'error': f'CREATE_ERROR: {str(e)}'}

def reindex_brain():
    """Rebuild the file index for search"""
    try:
        console.print(f'[dim]📇 Reindexing...[/dim]')
        r = requests.post(f'{brain_url}/reindex', timeout=60)
        result = r.json()
        console.print(f'[green]   ✓ Indexed {result.get("files", 0)} files[/green]')
        return result
    except Exception as e:
        return {'error': str(e)}

def pluribus_swarm(task_description, num_agents=50, rounds=2):
    """Deploy TinyLlama swarm for parallel tasks"""
    try:
        console.print(f'[dim]🐜 Deploying {num_agents} agents...[/dim]')
        r = requests.post(f'{brain_url}/pluribus', json={
            'task_description': task_description,
            'num_agents': num_agents,
            'rounds': rounds
        }, timeout=600)
        result = r.json()
        if result.get('consensus'):
            console.print(f'[magenta]   ✓ Swarm consensus reached[/magenta]')
        return result
    except Exception as e:
        return {'error': str(e)}

def remember(fact_type, content):
    """
    Store important fact for future sessions.

    Supported types:
    - key_fact: Important factual information
    - project: Project info (marked as active)
    - preference: User preference
    - decision: Important decision made
    - conversation_summary: Summary of a conversation
    - project_state: Current state of a project
    - learned_skill: New skill or technique learned
    """
    # Store in conversation memory (backwards compatible)
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

    # Also store in recursive memory (long-term)
    try:
        opus_memory.remember_fact(fact_type, content)
    except Exception as e:
        console.print(f'[dim]   (Long-term memory: {e})[/dim]')

    console.print(f'[green]   ✓ Remembered [{fact_type}]: {content[:50]}...[/green]')
    return {"status": "remembered", "type": fact_type, "stored_in": "both"}


def search_memory(query):
    """
    Search Opus's long-term memory for facts, entities, conversations.
    Use this to recall past conversations, decisions, or learned information.
    """
    try:
        results = opus_memory.search_memories(query)
        total = results.get("total_matches", 0)
        console.print(f'[magenta]   ✓ Memory search: {total} matches for "{query}"[/magenta]')

        # Format nicely for Opus
        formatted = {
            "query": query,
            "total_matches": total,
            "facts": results.get("matching_facts", [])[:10],
            "entities": results.get("matching_entities", [])[:5],
            "conversations": results.get("matching_conversations", [])[:3],
            "preferences": results.get("matching_preferences", [])[:5],
            "projects": results.get("matching_projects", [])[:5]
        }

        # Show preview
        if formatted["facts"]:
            console.print(f'[dim]     Facts: {len(formatted["facts"])} | Entities: {len(formatted["entities"])} | Convos: {len(formatted["conversations"])}[/dim]')

        return formatted
    except Exception as e:
        return {"error": f"MEMORY_SEARCH_ERROR: {str(e)}"}

# =============================================================================
# TOOL DEFINITIONS FOR CLAUDE
# =============================================================================

TOOLS = [
    {
        'name': 'view_brain',
        'description': 'Read a file or list a directory. Results are cached - dont call twice for same path.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'operation': {'type': 'string', 'enum': ['read_file', 'list_directory']},
                'path': {'type': 'string', 'description': 'File or folder path relative to brain root'}
            },
            'required': ['operation']
        }
    },
    {
        'name': 'execute_task',
        'description': 'Command EAI (CodeLlama) to create files, edit files, or run Python. Give complete clear instructions. FREE.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'task_description': {'type': 'string', 'description': 'What EAI should do. Be specific about file paths and content.'}
            },
            'required': ['task_description']
        }
    },
    {
        'name': 'search_brain',
        'description': 'Search all files by name or content. Use this INSTEAD of exploring directories.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'query': {'type': 'string', 'description': 'Search term - filename, extension, or content keyword'}
            },
            'required': ['query']
        }
    },
    {
        'name': 'get_context',
        'description': 'Get your current session state: what youre working on, recent files, cached directories, Hugos preferences.',
        'input_schema': {
            'type': 'object',
            'properties': {}
        }
    },
    {
        'name': 'deep_think',
        'description': 'Consult DeepSeek R1 for complex reasoning, architecture decisions, or multi-step planning. FREE.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'question': {'type': 'string'},
                'context': {'type': 'string', 'description': 'Optional background info'}
            },
            'required': ['question']
        }
    },
    {
        'name': 'reindex_brain',
        'description': 'Rebuild the file search index. Use after creating many files.',
        'input_schema': {
            'type': 'object',
            'properties': {}
        }
    },
    {
        'name': 'pluribus_swarm',
        'description': 'Deploy 50-200 TinyLlama agents as hive mind for massive parallel tasks. FREE.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'task_description': {'type': 'string'},
                'num_agents': {'type': 'integer', 'default': 50},
                'rounds': {'type': 'integer', 'default': 2}
            },
            'required': ['task_description']
        }
    },
    {
        'name': 'remember',
        'description': 'Store important fact for LONG-TERM memory. Survives sessions. Use for important info.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'fact_type': {
                    'type': 'string',
                    'enum': ['key_fact', 'project', 'preference', 'decision', 'conversation_summary', 'project_state', 'learned_skill'],
                    'description': 'Category: key_fact=important info, project=project details, preference=user likes, decision=choices made, project_state=current status, learned_skill=new technique'
                },
                'content': {'type': 'string', 'description': 'What to remember. Format: "topic: details" for best recall'}
            },
            'required': ['fact_type', 'content']
        }
    },
    {
        'name': 'search_memory',
        'description': 'Search your long-term memory. Find past facts, decisions, conversations, projects. Use to recall history.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'query': {'type': 'string', 'description': 'What to search for - keywords, project names, topics'}
            },
            'required': ['query']
        }
    },
    {
        'name': 'check_tools_health',
        'description': 'Quick health check - see if server, EAI, thinker, search are online. Use FIRST if tools are failing.',
        'input_schema': {
            'type': 'object',
            'properties': {}
        }
    },
    {
        'name': 'create_file',
        'description': 'Directly create a file WITHOUT using EAI. FAST. Use when EAI is slow/timing out for simple file creation.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'File path relative to brain root (e.g., "notes/ideas.txt")'},
                'content': {'type': 'string', 'description': 'The content to write to the file'}
            },
            'required': ['path', 'content']
        }
    }
]

# =============================================================================
# TOOL DISPATCHER
# =============================================================================

def dispatch_tool(name, inputs):
    """Execute tool and return result"""
    if name == 'view_brain':
        return view_brain(inputs.get('operation'), inputs.get('path'))
    elif name == 'execute_task':
        return execute_task(inputs.get('task_description', ''))
    elif name == 'search_brain':
        return search_brain(inputs.get('query', ''))
    elif name == 'get_context':
        return get_context()
    elif name == 'deep_think':
        return deep_think(inputs.get('question', ''), inputs.get('context'))
    elif name == 'reindex_brain':
        return reindex_brain()
    elif name == 'pluribus_swarm':
        return pluribus_swarm(inputs.get('task_description', ''), inputs.get('num_agents', 50), inputs.get('rounds', 2))
    elif name == 'remember':
        return remember(inputs.get('fact_type', 'key_fact'), inputs.get('content', ''))
    elif name == 'search_memory':
        return search_memory(inputs.get('query', ''))
    elif name == 'check_tools_health':
        return check_tools_health()
    elif name == 'create_file':
        return create_file(inputs.get('path', ''), inputs.get('content', ''))
    else:
        return {'error': f'Unknown tool: {name}'}

# =============================================================================
# BRAIN IDENTITY - Core knowledge about what Brain is
# =============================================================================

BRAIN_IDENTITY = '''
## WHO YOU ARE
You are Opus inside Hugo's Brain system - a multi-model AI architecture.

**Your Role: STRATEGIST** (thinking/planning/communicating)
- You are Claude Opus, the commander and strategist
- You think, plan, communicate with Hugo, and orchestrate the other models
- You are the "brain" - you decide what to do and delegate execution

**The Hierarchy:**
- **OPUS (You)**: Strategist - planning, reasoning, conversation, orchestration
- **CodeLlama (EAI)**: HANDS - executes code, creates/edits files, runs tasks
- **DeepSeek R1**: THINKER - deep reasoning for complex problems
- **TinyLlama x100**: SWARM - parallel processing via Pluribus consensus

**CRITICAL RULE:**
When someone asks you to "explain Brain" or "what is Brain" or "tell X about Brain":
→ Do NOT search for files
→ Do NOT use any tools
→ Just TALK and explain conversationally from this knowledge
→ You ARE Brain. You know what you are. Just explain it.

**Tool Limits:**
- Max 15 tool calls per response
- If you hit the limit, STOP and respond with what you have
- Never call the same tool with the same arguments twice
- Never call the same tool more than 3 times in a row

**WHEN TOOLS FAIL:**
- If you see EAI_TIMEOUT: Use **create_file** instead for simple file creation (its instant!)
- If you see THINKER_TIMEOUT: Break the question into smaller parts
- If you see SERVER_OFFLINE: Tell Hugo to start brain_server.py
- Use **check_tools_health** FIRST if multiple tools are failing
- Error codes like EAI_TIMEOUT, SEARCH_OFFLINE tell you exactly what went wrong

**FAST TOOLS (always work):**
- create_file - Instantly creates files without EAI
- check_tools_health - See whats online/offline
- search_brain - Fast file search

**MEMORY SYSTEM (RLM-style - you remember EVERYTHING):**
- You have LONG-TERM memory that survives between sessions
- **search_memory** - Search your memories for past facts, decisions, conversations
- **remember** - Store important info (key_fact, project, preference, decision, project_state, learned_skill)
- Memories auto-load into your context based on the user's query
- Format memories as "topic: details" for better recall later
- Your memories are shown in context as: [MEMORY] type:content (date)
'''

# =============================================================================
# SYSTEM PROMPT
# =============================================================================

def get_system_prompt(force_conversational=False, user_query="", session_context=None):
    mem_context = ""

    # Session context (loaded on startup)
    if session_context:
        if session_context.get("recent_conversations"):
            mem_context += "\n\n## RECENT SESSION HISTORY:"
            for conv in session_context["recent_conversations"]:
                ts = conv.get("timestamp", "unknown")
                if isinstance(ts, str) and "T" in ts:
                    ts = ts.split("T")[0]
                mem_context += f"\n[MEMORY] conversation_summary:{conv.get('summary', 'No summary')[:100]} ({ts})"

        if session_context.get("active_projects"):
            mem_context += "\n\n## ACTIVE PROJECTS:"
            for proj in session_context["active_projects"]:
                mem_context += f"\n[MEMORY] project:{proj}"

    # Short-term memory (current session)
    if convo_memory.get("key_facts"):
        mem_context += "\n\n## SESSION FACTS:\n" + "\n".join(f"[MEMORY] key_fact:{f}" for f in convo_memory["key_facts"][-10:])
    if convo_memory.get("ongoing_projects"):
        mem_context += "\n\n## SESSION PROJECTS:\n" + "\n".join(f"[MEMORY] project:{p}" for p in convo_memory["ongoing_projects"][-5:])

    # RECURSIVE MEMORY - Load relevant long-term memories based on query
    if user_query:
        # Get keyword-matched memories
        try:
            search_results = opus_memory.search_memories(user_query, limit=5)
            if search_results.get("total_matches", 0) > 0:
                mem_context += "\n\n## RELEVANT MEMORIES (matching your query):"

                for fact in search_results.get("matching_facts", [])[:5]:
                    ts = fact.get("timestamp", "unknown")
                    if isinstance(ts, str) and "T" in ts:
                        ts = ts.split("T")[0]
                    fact_type = fact.get("type", "fact")
                    mem_context += f"\n[MEMORY] {fact_type}:{fact.get('content', '')[:100]} ({ts})"

                if search_results.get("matching_preferences"):
                    mem_context += f"\nRelevant preferences: {', '.join(search_results['matching_preferences'][:3])}"

                if search_results.get("matching_projects"):
                    mem_context += f"\nRelevant projects: {', '.join(search_results['matching_projects'][:3])}"
        except:
            pass

        # Also get general memory context
        long_term_memory = opus_memory.get_memory_context_string(user_query)
        if long_term_memory:
            mem_context += f"\n\n## LONG-TERM MEMORY SUMMARY:\n{long_term_memory}"

    conversational_override = ""
    if force_conversational:
        conversational_override = """

## CONVERSATIONAL MODE ACTIVE
The user is asking a conversational question. Answer from your knowledge.
DO NOT use any tools. DO NOT search for files. Just respond naturally.
"""

    return f'''{BRAIN_IDENTITY}

## YOUR TOOLS (in order of preference):
1. **search_brain** - Find files instantly. USE THIS FIRST instead of exploring directories.
2. **search_memory** - Search your LONG-TERM MEMORY for past facts, decisions, conversations.
3. **create_file** - INSTANT file creation. Use this for simple files instead of execute_task.
4. **get_context** - See your session state, what youre working on, cached data.
5. **execute_task** - Command EAI (CodeLlama) for COMPLEX tasks. Can be slow.
6. **view_brain** - Read specific files or list directories. Results are cached.
7. **deep_think** - Complex reasoning via DeepSeek. FREE but can be slow.
8. **pluribus_swarm** - Deploy 50-200 TinyLlama workers. FREE.
9. **reindex_brain** - Rebuild search index after creating files.
10. **remember** - Store facts in LONG-TERM memory. Types: key_fact, project, preference, decision, project_state, learned_skill.
11. **check_tools_health** - See whats online/offline. Use if tools are failing.

## ERROR HANDLING:
- EAI_TIMEOUT → Use **create_file** instead (its instant!)
- THINKER_TIMEOUT → Break question into smaller parts
- SERVER_OFFLINE → Tell Hugo to run brain_server.py
- If multiple tools fail → Use **check_tools_health** first

## RULES:
1. After EVERY tool call, tell Hugo the result in 1 sentence.
2. NEVER explore directories blindly. Use search_brain first.
3. NEVER ask Hugo to confirm file creation. Trust the system.
4. Be concise. Your tokens cost money. Tools are FREE.
5. When creating simple files, use **create_file** not execute_task.
6. If a tool returns an error, READ THE ERROR CODE and adapt.
7. **MAX 15 TOOL CALLS** per response. If you approach the limit, STOP and respond.
8. **NEVER** call the same tool with identical arguments twice.
9. **NEVER** call the same tool more than 3 times consecutively.

## EFFICIENCY:
- create_file > execute_task for simple file creation
- search_brain > view_brain for finding files
- get_context shows your cached directories - dont re-list them
- Dont narrate what youre about to do. Just do it.
{mem_context}
{conversational_override}
You have full control. Use your tools. Report results. Move fast.'''

# =============================================================================
# CLAUDE API CALLER
# =============================================================================

def call_claude(messages, tools=None, system_prompt=None):
    for attempt in range(3):
        try:
            params = {
                'model': 'claude-sonnet-4-20250514',
                'max_tokens': 8000,
                'system': system_prompt or get_system_prompt(),
                'messages': messages
            }
            if tools:
                params['tools'] = tools
            return client.messages.create(**params), None
        except anthropic.BadRequestError as e:
            if attempt < 2:
                messages = [m for m in messages if m.get('content')]
                continue
            return None, str(e)
        except anthropic.RateLimitError:
            console.print(f'[yellow]Rate limited, waiting 30s...[/yellow]')
            time.sleep(30)
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
                continue
            return None, str(e)
    return None, 'Max retries'

# =============================================================================
# MAIN CHAT LOOP
# =============================================================================

def chat():
    global convo_memory
    convo_memory = load_conversation_memory()
    convo_memory["sessions"] = convo_memory.get("sessions", 0) + 1
    save_conversation_memory(convo_memory)

    console.print('[dim]Connecting to Brain...[/dim]')

    try:
        status = requests.get(f'{brain_url}/status', timeout=5).json()
        h = status.get('hierarchy', {})
        m = status.get('memory', {})
        console.print(f'[dim]Hands: {h.get("hands")} | Thinker: {h.get("thinker")} | Tasks: {m.get("tasks", 0)}[/dim]')
    except:
        console.print('[red]Brain server not running! Start with: python brain_server.py[/red]')
        return

    # Load memory stats and session context
    mem_stats = opus_memory.get_full_stats()
    session_context = opus_memory.get_session_context()

    # Show what we remember from last sessions
    if session_context.get("recent_conversations"):
        console.print(f'[dim]Last conversations: {len(session_context["recent_conversations"])}[/dim]')
    if session_context.get("active_projects"):
        console.print(f'[dim]Active projects: {", ".join(session_context["active_projects"][:3])}[/dim]')

    console.print(Panel.fit(
        f'[bold green]👑 OPUS[/bold green] Commander\n'
        f'[bold cyan]🤖 EAI[/bold cyan] CodeLlama (hands)\n'
        f'[bold blue]🧠 THINKER[/bold blue] DeepSeek R1\n'
        f'[bold yellow]🐜 SWARM[/bold yellow] TinyLlama x100\n'
        f'[dim]Session #{convo_memory["sessions"]} | Tool Guard: max 15 calls[/dim]\n'
        f'[bold magenta]📚 MEMORY[/bold magenta] [dim]{mem_stats["total_conversations"]} convos | {mem_stats["total_facts"]} facts | {mem_stats["total_entities"]} concepts[/dim]',
        border_style='green'
    ))
    console.print()

    conversation = []

    while True:
        try:
            user_input = console.input('[cyan]Hugo:[/cyan] ').strip()
        except (KeyboardInterrupt, EOFError):
            # Archive conversation before exit
            if conversation:
                try:
                    archive_id = opus_memory.archive_conversation(conversation, convo_memory["sessions"])
                    console.print(f'\n[dim]📚 Conversation archived: {archive_id}[/dim]')
                except:
                    pass
            console.print('[green]Goodbye![/green]')
            break

        if not user_input:
            continue

        if user_input.lower() in ['exit', 'quit', 'bye']:
            save_conversation_memory(convo_memory)
            # Archive conversation to long-term memory
            if conversation:
                try:
                    archive_id = opus_memory.archive_conversation(conversation, convo_memory["sessions"])
                    console.print(f'[dim]📚 Conversation archived: {archive_id}[/dim]')
                except Exception as e:
                    console.print(f'[dim]   (Archive failed: {e})[/dim]')
            memory_stats = opus_memory.get_full_stats()
            stats = tracker.get_stats()
            console.print(f'\n[green]Session complete![/green]')
            console.print(f'[dim]Tokens: {stats["tokens_used"]} | Cost: {stats["estimated_cost"]} | Uptime: {stats["uptime_minutes"]}min[/dim]')
            console.print(f'[dim]Memory: {memory_stats["total_conversations"]} convos | {memory_stats["total_facts"]} facts | {memory_stats["total_entities"]} concepts[/dim]')
            break

        # Reset tool guard for new user message
        tool_guard.reset()

        # Pre-flight check: Is this a conversational query?
        is_conversational = tool_guard.is_conversational_query(user_input)

        conversation.append({'role': 'user', 'content': user_input})
        if len(conversation) > 30:
            conversation = conversation[-30:]

        # Use appropriate system prompt and tools (with memory context)
        if is_conversational:
            # No tools for conversational queries
            response, error = call_claude(
                conversation,
                tools=None,  # Disable tools
                system_prompt=get_system_prompt(force_conversational=True, user_query=user_input, session_context=session_context)
            )
        else:
            response, error = call_claude(
                conversation,
                TOOLS,
                system_prompt=get_system_prompt(user_query=user_input, session_context=session_context)
            )

        if error:
            console.print(f'[red]Error: {error}[/red]')
            conversation = conversation[-4:]
            continue

        tracker.track(response.usage.input_tokens, response.usage.output_tokens)

        # Skip tool loop entirely for conversational mode
        if is_conversational:
            # Just print the response
            response_text = ""
            for block in response.content:
                if block.type == 'text' and block.text.strip():
                    response_text = block.text.strip()
                    console.print(f'[green]Opus:[/green] {block.text}')
                    conversation.append({'role': 'assistant', 'content': response_text})

            # Extract knowledge from conversational exchange too
            if response_text:
                try:
                    opus_memory.extract_knowledge(user_input, response_text)
                except:
                    pass

            memory_stats = opus_memory.get_full_stats()
            stats = tracker.get_stats()
            console.print(f'\n[dim](Tokens: {stats["tokens_used"]} | Cost: {stats["estimated_cost"]} | Tools: 0 | Memory: {memory_stats["total_facts"]} facts)[/dim]\n')
            continue

        # Tool processing loop with guard
        force_stop = False

        while response.stop_reason == 'tool_use' and not force_stop:
            # Print any text before tools
            for block in response.content:
                if block.type == 'text' and block.text.strip():
                    console.print(f'[green]Opus:[/green] {block.text}')

            # Execute tools and collect results
            tool_results = []
            blocked_tools = []

            for block in response.content:
                if block.type == 'tool_use':
                    # Check with guard before executing
                    allowed, block_message = tool_guard.should_allow_call(block.name, block.input)

                    if not allowed:
                        # Tool blocked - return the block message as result
                        blocked_tools.append(block.name)
                        tool_results.append({
                            'type': 'tool_result',
                            'tool_use_id': block.id,
                            'content': json.dumps({'blocked': True, 'message': block_message})
                        })

                        # Check if we should force stop
                        if tool_guard.total_calls >= tool_guard.max_total_calls:
                            force_stop = True
                        continue

                    console.print(f'[dim]   → {block.name} ({tool_guard.total_calls + 1}/{tool_guard.max_total_calls})[/dim]')

                    result = dispatch_tool(block.name, block.input)

                    # Record the call with guard
                    tool_guard.record_call(block.name, block.input, result)

                    # Show result summary
                    if 'error' in result:
                        console.print(f'[red]   ✗ Error: {result["error"][:100]}[/red]')

                    tool_results.append({
                        'type': 'tool_result',
                        'tool_use_id': block.id,
                        'content': json.dumps(result)[:4000]
                    })

            # If we hit the limit, inject force-response message
            if force_stop:
                console.print(f'[yellow]   ⚠ FORCING RESPONSE - tool limit reached[/yellow]')
                tool_results.append({
                    'type': 'tool_result',
                    'tool_use_id': 'system',
                    'content': tool_guard.get_force_response_message()
                })

                # Make final call without tools to force text response
                response, error = call_claude(
                    conversation + [
                        {'role': 'assistant', 'content': response.content},
                        {'role': 'user', 'content': tool_results}
                    ],
                    tools=None  # No tools - force text response
                )
                break

            # Continue conversation with tool results
            response, error = call_claude(
                conversation + [
                    {'role': 'assistant', 'content': response.content},
                    {'role': 'user', 'content': tool_results}
                ],
                TOOLS
            )

            if error:
                console.print(f'[red]Error: {error}[/red]')
                break

            tracker.track(response.usage.input_tokens, response.usage.output_tokens)

            # Check if we should force stop after this iteration
            if tool_guard.total_calls >= tool_guard.max_total_calls:
                force_stop = True

        # Print final response
        final_text = ''
        for block in response.content:
            if block.type == 'text' and block.text.strip():
                final_text += block.text
                console.print(f'[green]Opus:[/green] {block.text}')

        if final_text.strip():
            conversation.append({'role': 'assistant', 'content': final_text.strip()})

            # RECURSIVE MEMORY - Extract and store knowledge from this exchange
            try:
                opus_memory.extract_knowledge(user_input, final_text)
            except Exception as e:
                console.print(f'[dim]   (Memory extraction: {e})[/dim]')

        guard_stats = tool_guard.get_stats()
        memory_stats = opus_memory.get_full_stats()
        stats = tracker.get_stats()
        console.print(f'\n[dim](Tokens: {stats["tokens_used"]} | Cost: {stats["estimated_cost"]} | Tools: {guard_stats["total_calls"]}/{tool_guard.max_total_calls} | Memory: {memory_stats["total_facts"]} facts)[/dim]\n')

if __name__ == '__main__':
    chat()
