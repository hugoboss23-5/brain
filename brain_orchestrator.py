import ollama
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

# =============================================================================
# FULLY OFFLINE - No API costs, no wifi required
# =============================================================================
# DeepSeek R1 via Ollama = Commander + Thinker (one model, two roles)
# CodeLlama 7B via Ollama = Hands/Executor (file ops, code only)
# TinyLlama x8 via Ollama = Swarm (parallel grunt work)
# =============================================================================

COMMANDER_MODEL = "deepseek-r1:latest"  # Main brain - strategist + deep thinker
EXECUTOR_MODEL = "codellama:7b"          # Hands - file ops, code execution
SWARM_MODEL = "tinyllama"                # Grunt workers - parallel tasks

brain_url = f"http://127.0.0.1:{config['server_port']}"

# JARVIS MODE - Execute silently, report results only, no narration
JARVIS_MODE = True

# SILENT MODE - All reasoning to internal log, user only sees final result
SILENT_MODE = True

# =============================================================================
# COMPUTE EFFICIENCY CONFIG
# =============================================================================
COMPUTE_CONFIG = {
    # Concurrency limits
    'swarm_concurrency': 8,          # Max parallel TinyLlama agents (was 100)

    # Budget limits
    'max_tool_calls': 12,            # Max tool calls per response (was 15)
    'max_same_args_repeat': 1,       # If same tool+args called twice with no new artifact, halt
    'max_thinker_calls': 2,          # Max DeepSeek R1 calls per task
    'max_api_calls': 1,              # Max external API calls per task

    # Context compression
    'max_context_tokens': 4096,      # Default context window for compression

    # Caching
    'cache_file': 'system/brain_cache.json',
    'internal_log': 'system/brain_internal.log',
}

CONVO_MEMORY_FILE = "system/conversation_memory.json"
SWARM_ERROR_LOG = "system/swarm_errors.log"
BRAIN_CACHE_FILE = COMPUTE_CONFIG['cache_file']
INTERNAL_LOG_FILE = COMPUTE_CONFIG['internal_log']

# =============================================================================
# INTERNAL LOGGING (SILENT MODE)
# =============================================================================

def log_internal(message, level='INFO'):
    """Log to internal file when SILENT_MODE is on"""
    if SILENT_MODE:
        try:
            os.makedirs(os.path.dirname(INTERNAL_LOG_FILE), exist_ok=True)
            with open(INTERNAL_LOG_FILE, 'a', encoding='utf-8') as f:
                timestamp = datetime.now().isoformat()
                f.write(f"[{timestamp}] [{level}] {message}\n")
        except:
            pass

# =============================================================================
# FINGERPRINT CACHE - Zero new tokens for repeated tasks
# =============================================================================

class FingerprintCache:
    """Hash tasks and cache results. Same fingerprint = instant cached result."""

    def __init__(self, cache_file=BRAIN_CACHE_FILE):
        self.cache_file = cache_file
        self.cache = self._load_cache()

    def _load_cache(self):
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
        except:
            pass
        return {'fingerprints': {}, 'hits': 0, 'misses': 0}

    def _save_cache(self):
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except:
            pass

    def make_fingerprint(self, task, args, artifact_hashes=None):
        """Create unique fingerprint from task + args + artifact hashes"""
        data = {
            'task': task,
            'args': args,
            'artifacts': artifact_hashes or []
        }
        data_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()[:16]

    def get(self, fingerprint):
        """Get cached result if fingerprint exists"""
        if fingerprint in self.cache['fingerprints']:
            self.cache['hits'] += 1
            log_internal(f"Cache HIT: {fingerprint}")
            return self.cache['fingerprints'][fingerprint]
        self.cache['misses'] += 1
        return None

    def set(self, fingerprint, result):
        """Store result for fingerprint"""
        self.cache['fingerprints'][fingerprint] = {
            'result': result,
            'timestamp': datetime.now().isoformat()
        }
        # Keep cache bounded
        if len(self.cache['fingerprints']) > 1000:
            # Remove oldest entries
            sorted_entries = sorted(
                self.cache['fingerprints'].items(),
                key=lambda x: x[1].get('timestamp', ''),
            )
            self.cache['fingerprints'] = dict(sorted_entries[-500:])
        self._save_cache()

    def get_stats(self):
        return {
            'entries': len(self.cache['fingerprints']),
            'hits': self.cache['hits'],
            'misses': self.cache['misses'],
            'hit_rate': f"{self.cache['hits'] / max(1, self.cache['hits'] + self.cache['misses']) * 100:.1f}%"
        }

# Global cache instance
fingerprint_cache = FingerprintCache()

# =============================================================================
# COMPUTE BUDGET TRACKER
# =============================================================================

class ComputeBudget:
    """Track and enforce compute budgets per task"""

    def __init__(self):
        self.reset()

    def reset(self):
        """Reset for new task"""
        self.tool_calls = 0
        self.thinker_calls = 0
        self.api_calls = 0
        self.same_args_calls = {}  # signature -> (count, last_artifact_hash)
        self.artifacts_produced = set()  # Track new artifacts created
        self.strikes = {}  # tool_signature -> strike count (2 strikes = halt)
        self.halted = False
        self.halt_reason = None

    def can_call_tool(self):
        if self.halted:
            return False, self.halt_reason
        if self.tool_calls >= COMPUTE_CONFIG['max_tool_calls']:
            return False, f"Tool budget exhausted ({COMPUTE_CONFIG['max_tool_calls']} calls)"
        return True, None

    def can_call_thinker(self):
        if self.halted:
            return False, self.halt_reason
        if self.thinker_calls >= COMPUTE_CONFIG['max_thinker_calls']:
            return False, f"Thinker budget exhausted ({COMPUTE_CONFIG['max_thinker_calls']} calls)"
        return True, None

    def can_call_api(self):
        if self.halted:
            return False, self.halt_reason
        if self.api_calls >= COMPUTE_CONFIG['max_api_calls']:
            return False, f"API budget exhausted ({COMPUTE_CONFIG['max_api_calls']} calls)"
        return True, None

    def check_same_args_repeat(self, signature, current_artifact_hash):
        """
        2 STRIKES RULE: If same tool+args called twice with no new artifact, halt.
        Returns: (allowed, halt_message)
        """
        if signature not in self.same_args_calls:
            self.same_args_calls[signature] = (1, current_artifact_hash)
            return True, None

        count, last_hash = self.same_args_calls[signature]

        # Check if new artifact was produced
        new_artifact = current_artifact_hash != last_hash

        if not new_artifact:
            # Strike!
            self.strikes[signature] = self.strikes.get(signature, 0) + 1
            if self.strikes[signature] >= 2:
                self.halted = True
                self.halt_reason = f"blocked: need new artifact (2 strikes on same call)"
                log_internal(f"2 STRIKES HALT: {signature}")
                return False, self.halt_reason

        self.same_args_calls[signature] = (count + 1, current_artifact_hash)
        return True, None

    def record_tool_call(self, tool_name):
        self.tool_calls += 1
        if tool_name == 'deep_think':
            self.thinker_calls += 1
        log_internal(f"Tool call: {tool_name} ({self.tool_calls}/{COMPUTE_CONFIG['max_tool_calls']})")

    def record_artifact(self, artifact_id):
        """Record that a new artifact was produced (file created, etc)"""
        self.artifacts_produced.add(artifact_id)

    def get_remaining(self):
        return {
            'tools': COMPUTE_CONFIG['max_tool_calls'] - self.tool_calls,
            'thinker': COMPUTE_CONFIG['max_thinker_calls'] - self.thinker_calls,
            'api': COMPUTE_CONFIG['max_api_calls'] - self.api_calls,
        }

# Global budget instance
compute_budget = ComputeBudget()

# =============================================================================
# CONTEXT COMPRESSOR
# =============================================================================

class ContextCompressor:
    """Compress context to schema before API calls"""

    @staticmethod
    def compress(task, known_facts, unknown_items, constraints, budget_remaining):
        """
        Compress context to schema:
        TASK (1-3 sentences), KNOWN (max 8 bullets), UNKNOWN (max 5 bullets),
        CONSTRAINTS (max 6 bullets), BUDGET (calls remaining)
        """
        compressed = []

        # TASK: 1-3 sentences
        task_text = str(task)[:500] if task else "No task specified"
        compressed.append(f"TASK: {task_text}")

        # KNOWN: max 8 bullets
        if known_facts:
            known_list = known_facts[:8] if isinstance(known_facts, list) else [known_facts]
            compressed.append("KNOWN:")
            for k in known_list[:8]:
                compressed.append(f"  - {str(k)[:100]}")

        # UNKNOWN: max 5 bullets
        if unknown_items:
            unknown_list = unknown_items[:5] if isinstance(unknown_items, list) else [unknown_items]
            compressed.append("UNKNOWN:")
            for u in unknown_list[:5]:
                compressed.append(f"  - {str(u)[:80]}")

        # CONSTRAINTS: max 6 bullets
        if constraints:
            const_list = constraints[:6] if isinstance(constraints, list) else [constraints]
            compressed.append("CONSTRAINTS:")
            for c in const_list[:6]:
                compressed.append(f"  - {str(c)[:80]}")

        # BUDGET
        compressed.append(f"BUDGET: tools={budget_remaining.get('tools', 0)} thinker={budget_remaining.get('thinker', 0)}")

        return "\n".join(compressed)

    @staticmethod
    def estimate_tokens(text):
        """Rough token estimate (4 chars per token)"""
        return len(text) // 4

# =============================================================================
# MODEL ROUTER - Route tasks to appropriate models
# =============================================================================

class ModelRouter:
    """Route tasks to the right model with single-model-at-a-time enforcement"""

    def __init__(self):
        self.active_model = None  # Only one big model active
        self.model_loads = {'codellama': 0, 'deepseek': 0, 'swarm': 0}

    def route(self, task_type, task_description):
        """
        Route to appropriate model:
        - CodeLlama: file ops, patches, commands
        - DeepSeek R1: planning, diagnosis (max 2 calls)
        - Swarm: parallel hypothesis, grep, test generation
        """
        task_lower = task_description.lower()

        # File operations -> CodeLlama
        if any(kw in task_lower for kw in ['create file', 'edit file', 'write', 'patch', 'modify', 'run', 'execute', 'command']):
            return 'codellama', 'execute_task'

        # Planning/diagnosis -> DeepSeek (if budget allows)
        if any(kw in task_lower for kw in ['plan', 'diagnose', 'analyze', 'architect', 'design', 'why', 'how should']):
            can_call, reason = compute_budget.can_call_thinker()
            if can_call:
                return 'deepseek', 'deep_think'
            else:
                log_internal(f"Routing to CodeLlama (thinker budget: {reason})")
                return 'codellama', 'execute_task'

        # Parallel tasks -> Swarm
        if any(kw in task_lower for kw in ['parallel', 'multiple', 'batch', 'swarm', 'test generation', 'hypothesis']):
            return 'swarm', 'pluribus_swarm'

        # Default to CodeLlama for efficiency
        return 'codellama', 'execute_task'

    def set_active(self, model_name):
        """Set active model (only one big model at a time)"""
        if self.active_model and self.active_model != model_name:
            log_internal(f"Model switch: {self.active_model} -> {model_name}")
        self.active_model = model_name
        self.model_loads[model_name] = self.model_loads.get(model_name, 0) + 1

    def get_stats(self):
        return {
            'active': self.active_model,
            'loads': self.model_loads
        }

# Global router instance
model_router = ModelRouter()

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

    def __init__(self, max_total_calls=None, max_consecutive_same=3, max_recent_signatures=5):
        # Use COMPUTE_CONFIG for max_total_calls (default 12)
        self.max_total_calls = max_total_calls or COMPUTE_CONFIG['max_tool_calls']
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
        self.duplicate_attempts = 0  # Track how many duplicates blocked (doesn't count toward limit)
        self.cached_results = {}     # Store results for instant return on duplicate

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
        Returns: (allowed: bool, message: str or None, cached_result: dict or None)
        """
        signature = self._make_signature(tool_name, tool_input)

        # Check 1: Total call limit (only counts ACTUAL calls, not duplicates)
        if self.total_calls >= self.max_total_calls:
            self.blocked_reason = f"Hit {self.max_total_calls} tool call limit"
            console.print(f'[yellow]   ⚠ CIRCUIT BREAKER: {self.blocked_reason}[/yellow]')
            return False, f"Tool limit reached. Respond with current information.", None

        # Check 2: Duplicate call detection - return cached result, DON'T count toward limit
        if signature in self.recent_signatures:
            self.duplicate_attempts += 1
            cached = self.cached_results.get(signature)
            # Silent - don't spam the console
            return False, None, cached  # Return cached result directly

        # Check 3: Consecutive same tool limit
        if tool_name == self.last_tool_name:
            self.consecutive_same_tool += 1
            if self.consecutive_same_tool >= self.max_consecutive_same:
                self.blocked_reason = f"Called {tool_name} {self.max_consecutive_same}x consecutively"
                console.print(f'[yellow]   ⚠ CIRCUIT BREAKER: {self.blocked_reason}[/yellow]')
                return False, f"Called {tool_name} 3x. Use gathered information now.", None
        else:
            self.consecutive_same_tool = 1

        return True, None, None

    def record_call(self, tool_name, tool_input, result):
        """Record a tool call after execution and cache result"""
        signature = self._make_signature(tool_name, tool_input)
        result_hash = self._hash_result(result)

        # Track signature
        self.recent_signatures.append(signature)
        if len(self.recent_signatures) > self.max_recent_signatures:
            self.recent_signatures.pop(0)

        # Cache result for instant return on duplicate attempts
        self.cached_results[signature] = result

        # Check for identical result to previous call of same tool
        if signature in self.result_hashes:
            if self.result_hashes[signature] == result_hash:
                pass  # Silent - no spam

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
            'blocked_reason': self.blocked_reason,
            'duplicate_attempts': self.duplicate_attempts
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
        if not SILENT_MODE:
            console.print(f'[dim]🤖 EAI working...[/dim]')
        log_internal(f"EAI task: {task_description[:100]}...")

        model_router.set_active('codellama')
        r = requests.post(f'{brain_url}/execute', json={'task_description': task_description}, timeout=120)
        result = r.json()

        # Track artifacts produced
        if result.get('created'):
            for f in result['created']:
                compute_budget.record_artifact(f"file:{f}")
            if not SILENT_MODE:
                console.print(f'[green]   ✓ Created: {", ".join(result["created"])}[/green]')
        if result.get('edited'):
            for f in result['edited']:
                compute_budget.record_artifact(f"edit:{f}")
            if not SILENT_MODE:
                console.print(f'[blue]   ✓ Edited: {", ".join(result["edited"])}[/blue]')

        log_internal(f"EAI result: created={result.get('created', [])}, edited={result.get('edited', [])}")
        return result
    except requests.exceptions.Timeout:
        return {'error': 'EAI_TIMEOUT: CodeLlama took too long (>120s). Try a simpler task or use create_file for basic file creation.', 'suggestion': 'Use create_file tool instead for simple file creation.'}
    except requests.exceptions.ConnectionError:
        return {'error': 'EAI_OFFLINE: Cannot reach Brain server. Is brain_server.py running?', 'suggestion': 'Start the server with: python brain_server.py'}
    except Exception as e:
        return {'error': f'EAI_ERROR: {str(e)}'}

def deep_think(question, context=None):
    """Deep reasoning via DeepSeek R1 (same model as commander, focused thinking mode)"""
    # Check thinker budget
    can_call, reason = compute_budget.can_call_thinker()
    if not can_call:
        log_internal(f"Thinker blocked: {reason}")
        return {'error': f'THINKER_BUDGET: {reason}', 'suggestion': 'Already at max 2 deep_think calls'}

    try:
        if not SILENT_MODE:
            console.print(f'[dim]🧠 Deep thinking...[/dim]')
        log_internal(f"Deep think: {question[:100]}...")

        model_router.set_active('deepseek')

        # Call R1 directly with focused thinking prompt
        thinking_prompt = f"""You are in DEEP THINKING mode. Focus entirely on this question.
Think step by step. Consider multiple angles. Be thorough.

CONTEXT: {context or 'None provided'}

QUESTION: {question}

Provide your detailed reasoning:"""

        response = ollama.chat(
            model=COMMANDER_MODEL,
            messages=[{"role": "user", "content": thinking_prompt}],
            options={
                'num_predict': 4096,
                'temperature': 0.3,  # Lower temp for focused reasoning
            }
        )

        reasoning = response.get('message', {}).get('content', '')

        if reasoning:
            if not SILENT_MODE:
                console.print(f'[blue]   ✓ Deep thinking complete ({len(reasoning)} chars)[/blue]')
            log_internal(f"Deep think complete: {len(reasoning)} chars")

        return {'reasoning': reasoning, 'model': COMMANDER_MODEL}
    except Exception as e:
        error_str = str(e)
        if 'connection' in error_str.lower():
            return {'error': 'OLLAMA_OFFLINE: Ollama not running. Start with: ollama serve'}
        return {'error': f'THINKER_ERROR: {error_str}'}

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

def log_swarm_error(error_type, error_msg, task_description):
    """Log swarm errors to file for debugging"""
    try:
        os.makedirs(os.path.dirname(SWARM_ERROR_LOG), exist_ok=True)
        with open(SWARM_ERROR_LOG, 'a', encoding='utf-8') as f:
            timestamp = datetime.now().isoformat()
            f.write(f"[{timestamp}] {error_type}: {error_msg}\n")
            f.write(f"  Task: {task_description[:100]}...\n\n")
    except:
        pass

def pluribus_swarm(task_description, num_agents=None, rounds=2):
    """Deploy TinyLlama swarm for parallel tasks (max 8 concurrent)"""
    # Enforce concurrency limit
    max_concurrent = COMPUTE_CONFIG['swarm_concurrency']
    if num_agents is None:
        num_agents = max_concurrent
    else:
        num_agents = min(num_agents, max_concurrent)

    try:
        if not SILENT_MODE:
            console.print(f'[dim]🐜 Deploying {num_agents} agents (max {max_concurrent})...[/dim]')
        log_internal(f"Swarm: {num_agents} agents, {rounds} rounds")

        model_router.set_active('swarm')
        r = requests.post(f'{brain_url}/pluribus', json={
            'task_description': task_description,
            'num_agents': num_agents,
            'rounds': rounds
        }, timeout=600)
        result = r.json()
        if result.get('consensus'):
            console.print(f'[magenta]   ✓ Swarm consensus reached[/magenta]')
        elif result.get('error'):
            error_msg = result.get('error')
            console.print(f'[red]   ✗ Swarm error: {error_msg}[/red]')
            log_swarm_error('SERVER_ERROR', error_msg, task_description)
        return result
    except requests.exceptions.Timeout:
        error_msg = 'SWARM_TIMEOUT: Swarm took too long (>600s). Try fewer agents or simpler task.'
        console.print(f'[red]   ✗ {error_msg}[/red]')
        log_swarm_error('TIMEOUT', error_msg, task_description)
        return {'error': error_msg, 'suggestion': 'Reduce num_agents or simplify task'}
    except requests.exceptions.ConnectionError:
        error_msg = 'SWARM_OFFLINE: Cannot reach Brain server. Is brain_server.py running?'
        console.print(f'[red]   ✗ {error_msg}[/red]')
        log_swarm_error('CONNECTION_ERROR', error_msg, task_description)
        return {'error': error_msg, 'suggestion': 'Start brain_server.py'}
    except requests.exceptions.ConnectionRefusedError:
        error_msg = 'SWARM_REFUSED: Server refused connection. Server may be overloaded.'
        console.print(f'[red]   ✗ {error_msg}[/red]')
        log_swarm_error('CONNECTION_REFUSED', error_msg, task_description)
        return {'error': error_msg, 'suggestion': 'Wait and retry, or restart server'}
    except Exception as e:
        error_msg = f'SWARM_ERROR: {type(e).__name__}: {str(e)}'
        console.print(f'[red]   ✗ {error_msg}[/red]')
        log_swarm_error('UNKNOWN', error_msg, task_description)
        return {'error': error_msg}

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


def remember_batch(facts):
    """
    Store multiple facts at once. More efficient than multiple remember calls.
    facts: list of {fact_type, content} dicts
    """
    results = []
    for fact in facts:
        fact_type = fact.get('fact_type', 'key_fact')
        content = fact.get('content', '')
        if content:
            result = remember(fact_type, content)
            results.append(result)

    console.print(f'[green]   ✓ Batch remembered {len(results)} facts[/green]')
    return {"status": "batch_remembered", "count": len(results), "facts": results}


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
        'description': 'Focused deep reasoning mode (same R1, lower temp). MAX 2 CALLS per task. Use for complex analysis.',
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
        'description': 'Deploy TinyLlama swarm (max 8 concurrent) for parallel hypothesis/grep/test generation. FREE.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'task_description': {'type': 'string'},
                'num_agents': {'type': 'integer', 'default': 8, 'maximum': 8},
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
        'name': 'remember_batch',
        'description': 'Store MULTIPLE facts in ONE call. Use instead of multiple remember calls. More efficient.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'facts': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'fact_type': {'type': 'string', 'enum': ['key_fact', 'project', 'preference', 'decision', 'conversation_summary', 'project_state', 'learned_skill']},
                            'content': {'type': 'string'}
                        },
                        'required': ['fact_type', 'content']
                    },
                    'description': 'Array of facts to remember'
                }
            },
            'required': ['facts']
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
    elif name == 'remember_batch':
        return remember_batch(inputs.get('facts', []))
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
You are DeepSeek R1 inside Hugo's Brain system - FULLY OFFLINE multi-model AI.

**Your Role: COMMANDER + THINKER** - You are both the strategist AND deep reasoner.
**Hierarchy:**
- **DEEPSEEK R1 (You)**: Commander + Thinker - planning, reasoning, orchestration, deep analysis
- **CodeLlama 7B**: HANDS - file ops, code execution, patches (use execute_task)
- **TinyLlama x8**: SWARM - parallel grunt work (8 concurrent max)

**FULLY OFFLINE:** No API costs, no wifi required. Everything runs locally via Ollama.

## COMPUTE EFFICIENCY (ACTIVE)
**Budgets per task:**
- Tools: 12 calls max
- Thinker (DeepSeek): 2 calls max
- Swarm: 8 parallel agents max

**2 STRIKES RULE:**
If same tool+args called twice with no new artifact → HALT.
Output "blocked: need X" and stop.

**ROUTING:**
- File ops → CodeLlama (fast)
- Planning/why/how → DeepSeek (limited)
- Parallel search/test → Swarm (8 max)

**FINGERPRINT CACHE:**
Repeated identical tasks return cached results instantly (zero tokens).

**SILENT MODE:**
No narration. Execute → Report result only.

**FAST TOOLS:** create_file, search_brain, check_tools_health
**MEMORY:** search_memory to recall, remember to store.
'''

# =============================================================================
# SYSTEM PROMPT
# =============================================================================

def get_system_prompt(force_conversational=False, user_query="", session_context=None, budget=None):
    mem_context = ""

    # Budget info
    if budget is None:
        budget = compute_budget.get_remaining()
    budget_str = f"tools={budget.get('tools', 12)} thinker={budget.get('thinker', 2)}"

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
1. **Execute first. Report result only. No narration.**
2. **BUDGET: 12 tools, 2 thinker, 8 swarm agents.**
3. **2 STRIKES:** Same call + no new artifact = halt with "blocked: need X"
4. Route: file ops→CodeLlama, planning→DeepSeek (limited), parallel→Swarm
5. Use create_file (instant) instead of execute_task for simple files.
6. Duplicates return cached results (don't count toward budget).
{mem_context}
{conversational_override}
BUDGET REMAINING: {budget_str}
Execute. Report. Stop when done.'''

# =============================================================================
# OLLAMA LOCAL MODEL CALLER (FULLY OFFLINE)
# =============================================================================

def format_tools_for_prompt(tools):
    """Format tools as text for the system prompt (Ollama doesn't support function calling natively)"""
    if not tools:
        return ""

    tool_text = "\n\n## AVAILABLE TOOLS:\n"
    tool_text += "To use a tool, output EXACTLY this format on its own line:\n"
    tool_text += "TOOL_CALL: tool_name {\"param\": \"value\"}\n\n"

    for tool in tools:
        tool_text += f"**{tool['name']}**: {tool['description']}\n"
        props = tool['input_schema'].get('properties', {})
        if props:
            params = ", ".join([f"{k}: {v.get('type', 'string')}" for k, v in props.items()])
            tool_text += f"  Parameters: {params}\n"

    tool_text += "\nAfter using a tool, wait for the result before continuing.\n"
    return tool_text

def convert_messages_for_ollama(messages, system_prompt):
    """Convert message format for Ollama"""
    converted = []
    if system_prompt:
        converted.append({"role": "system", "content": system_prompt})

    for msg in messages:
        if msg['role'] == 'user':
            if isinstance(msg.get('content'), list):
                # Tool results
                tool_results = []
                for item in msg['content']:
                    if item.get('type') == 'tool_result':
                        tool_results.append(f"[Tool Result]: {item.get('content', '')}")
                if tool_results:
                    converted.append({"role": "user", "content": "\n".join(tool_results)})
            else:
                converted.append({"role": "user", "content": msg['content']})
        elif msg['role'] == 'assistant':
            if hasattr(msg.get('content'), '__iter__') and not isinstance(msg.get('content'), str):
                text_parts = []
                for block in msg['content']:
                    if hasattr(block, 'type'):
                        if block.type == 'text':
                            text_parts.append(block.text)
                        elif block.type == 'tool_use':
                            text_parts.append(f"TOOL_CALL: {block.name} {json.dumps(block.input)}")
                if text_parts:
                    converted.append({"role": "assistant", "content": "\n".join(text_parts)})
            else:
                converted.append({"role": "assistant", "content": str(msg.get('content', ''))})

    return converted

def parse_tool_calls(text):
    """Parse TOOL_CALL: format from model output"""
    tool_calls = []
    lines = text.split('\n')

    for line in lines:
        line = line.strip()
        if line.startswith('TOOL_CALL:'):
            try:
                # Parse: TOOL_CALL: tool_name {"param": "value"}
                rest = line[10:].strip()
                # Find the tool name (first word)
                parts = rest.split(' ', 1)
                tool_name = parts[0]
                tool_args = {}
                if len(parts) > 1:
                    # Try to parse JSON args
                    try:
                        tool_args = json.loads(parts[1])
                    except:
                        # Try to extract from the rest of the line
                        pass
                tool_calls.append({
                    'id': f"call_{hashlib.md5(line.encode()).hexdigest()[:8]}",
                    'name': tool_name,
                    'input': tool_args
                })
            except:
                pass

    return tool_calls

class OllamaResponse:
    """Wrapper to make Ollama response look like Anthropic response"""
    def __init__(self, ollama_response, original_text):
        self.raw = ollama_response
        self.original_text = original_text
        self.stop_reason = 'end_turn'
        self.content = []

        # Parse tool calls from text
        tool_calls = parse_tool_calls(original_text)

        if tool_calls:
            self.stop_reason = 'tool_use'
            for tc in tool_calls:
                self.content.append(ToolUseBlock(
                    id=tc['id'],
                    name=tc['name'],
                    input=tc['input']
                ))

        # Add remaining text (without tool calls)
        clean_text = original_text
        for line in original_text.split('\n'):
            if line.strip().startswith('TOOL_CALL:'):
                clean_text = clean_text.replace(line, '')
        clean_text = clean_text.strip()
        if clean_text:
            self.content.append(TextBlock(text=clean_text))

        # Usage tracking (Ollama provides token counts)
        prompt_tokens = ollama_response.get('prompt_eval_count', 0) if isinstance(ollama_response, dict) else 0
        completion_tokens = ollama_response.get('eval_count', 0) if isinstance(ollama_response, dict) else 0
        self.usage = type('Usage', (), {
            'input_tokens': prompt_tokens,
            'output_tokens': completion_tokens
        })()

class TextBlock:
    def __init__(self, text):
        self.type = 'text'
        self.text = text

class ToolUseBlock:
    def __init__(self, id, name, input):
        self.type = 'tool_use'
        self.id = id
        self.name = name
        self.input = input

def call_commander(messages, tools=None, system_prompt=None):
    """Call DeepSeek R1 via Ollama (local, offline)"""
    for attempt in range(3):
        try:
            # Build system prompt with tools
            full_system = system_prompt or get_system_prompt()
            if tools:
                full_system += format_tools_for_prompt(tools)

            # Convert messages
            converted_messages = convert_messages_for_ollama(messages, full_system)

            log_internal(f"Calling {COMMANDER_MODEL} with {len(converted_messages)} messages")

            # Call Ollama
            response = ollama.chat(
                model=COMMANDER_MODEL,
                messages=converted_messages,
                options={
                    'num_predict': 4096,
                    'temperature': 0.7,
                }
            )

            # Extract response text
            response_text = response.get('message', {}).get('content', '')

            log_internal(f"Commander response: {len(response_text)} chars")

            return OllamaResponse(response, response_text), None

        except Exception as e:
            error_str = str(e)
            log_internal(f"Commander error (attempt {attempt+1}): {error_str}", level='ERROR')
            if 'connection' in error_str.lower():
                console.print(f'[red]Ollama not running! Start with: ollama serve[/red]')
                return None, 'OLLAMA_OFFLINE: Start ollama with: ollama serve'
            elif attempt < 2:
                time.sleep(2)
                continue
            else:
                return None, error_str

    return None, 'Max retries'

# Alias for compatibility
call_claude = call_commander
call_deepseek = call_commander

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

    cache_stats = fingerprint_cache.get_stats()
    console.print(Panel.fit(
        f'[bold green]👑 DEEPSEEK R1[/bold green] Commander + Thinker (LOCAL)\n'
        f'[bold cyan]🤖 EAI[/bold cyan] CodeLlama 7B (local)\n'
        f'[bold yellow]🐜 SWARM[/bold yellow] TinyLlama x{COMPUTE_CONFIG["swarm_concurrency"]}\n'
        f'[dim]FULLY OFFLINE - No API costs, no wifi required[/dim]\n'
        f'[dim]Session #{convo_memory["sessions"]} | Budget: {COMPUTE_CONFIG["max_tool_calls"]} tools | Cache: {cache_stats["entries"]} ({cache_stats["hit_rate"]} hit)[/dim]\n'
        f'[bold magenta]📚 MEMORY[/bold magenta] [dim]{mem_stats["total_conversations"]} convos | {mem_stats["total_facts"]} facts[/dim]',
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

        # Reset guards for new user message
        tool_guard.reset()
        compute_budget.reset()
        log_internal(f"New task: {user_input[:100]}...")

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
                    console.print(f'[green]Brain:[/green] {block.text}')
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
                    console.print(f'[green]Brain:[/green] {block.text}')

            # Execute tools and collect results
            tool_results = []
            blocked_tools = []

            # PRE-PROCESS: Consolidate multiple remember calls into batch
            remember_calls = []
            other_blocks = []
            for block in response.content:
                if block.type == 'tool_use' and block.name == 'remember':
                    remember_calls.append(block)
                else:
                    other_blocks.append(block)

            # If multiple remember calls, batch them
            if len(remember_calls) > 1:
                console.print(f'[dim]   ↳ Batching {len(remember_calls)} remember calls into 1[/dim]')
                facts = []
                for rc in remember_calls:
                    facts.append({
                        'fact_type': rc.input.get('fact_type', 'key_fact'),
                        'content': rc.input.get('content', '')
                    })
                batch_result = remember_batch(facts)
                # Return batch result for all remember call IDs
                for rc in remember_calls:
                    tool_results.append({
                        'type': 'tool_result',
                        'tool_use_id': rc.id,
                        'content': json.dumps(batch_result)[:4000]
                    })
                # Only process other blocks
                blocks_to_process = other_blocks
            else:
                blocks_to_process = response.content

            for block in blocks_to_process:
                if block.type == 'tool_use':
                    # Check with guard before executing
                    allowed, block_message, cached_result = tool_guard.should_allow_call(block.name, block.input)

                    if not allowed:
                        # Check if we have a cached result (duplicate call)
                        if cached_result is not None:
                            # Return cached result silently - doesn't count toward limit
                            tool_results.append({
                                'type': 'tool_result',
                                'tool_use_id': block.id,
                                'content': json.dumps({
                                    '_cached': True,
                                    '_note': 'Already have this info from previous call',
                                    **cached_result
                                })[:4000]
                            })
                            continue

                        # Tool blocked for other reason (limit reached, consecutive)
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

                    # Check compute budget
                    can_call, budget_reason = compute_budget.can_call_tool()
                    if not can_call:
                        log_internal(f"Budget blocked: {budget_reason}")
                        tool_results.append({
                            'type': 'tool_result',
                            'tool_use_id': block.id,
                            'content': json.dumps({'blocked': True, 'message': budget_reason})
                        })
                        force_stop = True
                        continue

                    # Check fingerprint cache first
                    signature = tool_guard._make_signature(block.name, block.input)
                    artifact_hash = hashlib.md5(json.dumps(list(compute_budget.artifacts_produced)).encode()).hexdigest()[:8]
                    fingerprint = fingerprint_cache.make_fingerprint(block.name, block.input, [artifact_hash])
                    cached = fingerprint_cache.get(fingerprint)
                    if cached:
                        log_internal(f"Cache hit: {block.name}")
                        if not SILENT_MODE:
                            console.print(f'[dim]   → {block.name} (CACHED)[/dim]')
                        tool_results.append({
                            'type': 'tool_result',
                            'tool_use_id': block.id,
                            'content': json.dumps({'_cached': True, **cached.get('result', {})})[:4000]
                        })
                        continue

                    # Check 2 strikes rule
                    allowed_strike, strike_reason = compute_budget.check_same_args_repeat(signature, artifact_hash)
                    if not allowed_strike:
                        if not SILENT_MODE:
                            console.print(f'[yellow]   ⚠ {strike_reason}[/yellow]')
                        tool_results.append({
                            'type': 'tool_result',
                            'tool_use_id': block.id,
                            'content': json.dumps({'halted': True, 'message': strike_reason})
                        })
                        force_stop = True
                        continue

                    if not SILENT_MODE:
                        console.print(f'[dim]   → {block.name} ({tool_guard.total_calls + 1}/{tool_guard.max_total_calls})[/dim]')

                    result = dispatch_tool(block.name, block.input)

                    # Record the call with guard and budget
                    tool_guard.record_call(block.name, block.input, result)
                    compute_budget.record_tool_call(block.name)

                    # Cache the result
                    fingerprint_cache.set(fingerprint, result)

                    # Show result summary (only errors, and only if not SILENT)
                    if 'error' in result and not SILENT_MODE:
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
                console.print(f'[green]Brain:[/green] {block.text}')

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
        budget = compute_budget.get_remaining()
        if not SILENT_MODE:
            console.print(f'\n[dim](Tokens: {stats["tokens_used"]} | Cost: {stats["estimated_cost"]} | Tools: {guard_stats["total_calls"]}/{COMPUTE_CONFIG["max_tool_calls"]} | Budget: T{budget["tools"]} D{budget["thinker"]})[/dim]\n')
        log_internal(f"Response complete: tokens={stats['tokens_used']}, tools={guard_stats['total_calls']}")

if __name__ == '__main__':
    chat()
