import anthropic
import json
import requests
from rich.console import Console
from rich.panel import Panel
import time
from datetime import datetime
import os

console = Console()

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
# TOOL FUNCTIONS - Direct server calls
# =============================================================================

def view_brain(operation, path=None):
    """Read file or list directory"""
    for attempt in range(3):
        try:
            r = requests.post(f'{brain_url}/view', json={'operation': operation, 'path': path}, timeout=30)
            return r.json()
        except Exception as e:
            if attempt == 2:
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
    except Exception as e:
        return {'error': str(e)}

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
    except Exception as e:
        return {'error': str(e)}

def search_brain(query):
    """Search files by name or content without directory traversal"""
    try:
        r = requests.post(f'{brain_url}/search', json={'query': query}, timeout=30)
        result = r.json()
        console.print(f'[cyan]   ✓ Found {result.get("count", 0)} files matching "{query}"[/cyan]')
        return result
    except Exception as e:
        return {'error': str(e)}

def get_context():
    """Get full session context - what you're working on, recent files, cached dirs"""
    try:
        r = requests.get(f'{brain_url}/context', timeout=10)
        result = r.json()
        console.print(f'[cyan]   ✓ Context loaded[/cyan]')
        return result
    except Exception as e:
        return {'error': str(e)}

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
    """Store important fact for future sessions"""
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
    console.print(f'[green]   ✓ Remembered: {content[:50]}...[/green]')
    return {"status": "remembered", "type": fact_type}

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
        'description': 'Store important fact for future sessions.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'fact_type': {'type': 'string', 'enum': ['key_fact', 'project', 'preference']},
                'content': {'type': 'string'}
            },
            'required': ['fact_type', 'content']
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
    else:
        return {'error': f'Unknown tool: {name}'}

# =============================================================================
# SYSTEM PROMPT
# =============================================================================

def get_system_prompt():
    mem_context = ""
    if convo_memory.get("key_facts"):
        mem_context = "\n\nREMEMBERED FACTS:\n" + "\n".join(f"- {f}" for f in convo_memory["key_facts"][-10:])
    if convo_memory.get("ongoing_projects"):
        mem_context += "\n\nONGOING PROJECTS:\n" + "\n".join(f"- {p}" for p in convo_memory["ongoing_projects"][-5:])
    
    return f'''You are Opus, Commander of the Brain.

## YOUR TOOLS (in order of preference):
1. **search_brain** - Find files instantly. USE THIS FIRST instead of exploring directories.
2. **get_context** - See your session state, what youre working on, cached data.
3. **execute_task** - Command EAI (CodeLlama) to create/edit files. FREE.
4. **view_brain** - Read specific files or list directories. Results are cached.
5. **deep_think** - Complex reasoning via DeepSeek. FREE.
6. **pluribus_swarm** - Deploy 50-200 TinyLlama workers. FREE.
7. **reindex_brain** - Rebuild search index after creating files.
8. **remember** - Store facts for future sessions.

## RULES:
1. After EVERY tool call, tell Hugo the result in 1 sentence.
2. NEVER explore directories blindly. Use search_brain first.
3. NEVER ask Hugo to confirm file creation. Trust the system.
4. Be concise. Your tokens cost money. Tools are FREE.
5. When EAI creates files, report what was created and move on.
6. If a tool returns an error, tell Hugo and try a different approach.

## EFFICIENCY:
- search_brain > view_brain for finding files
- get_context shows your cached directories - dont re-list them
- execute_task handles create AND edit - one call per task
- Dont narrate what youre about to do. Just do it.
{mem_context}

You have full control. Use your tools. Report results. Move fast.'''

# =============================================================================
# CLAUDE API CALLER
# =============================================================================

def call_claude(messages, tools=None):
    for attempt in range(3):
        try:
            params = {
                'model': 'claude-sonnet-4-20250514',
                'max_tokens': 8000,
                'system': get_system_prompt(),
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

    console.print(Panel.fit(
        f'[bold green]👑 OPUS[/bold green] Commander\n'
        f'[bold cyan]🤖 EAI[/bold cyan] CodeLlama (hands)\n'
        f'[bold blue]🧠 THINKER[/bold blue] DeepSeek R1\n'
        f'[bold yellow]🐜 SWARM[/bold yellow] TinyLlama x100\n'
        f'[dim]Session #{convo_memory["sessions"]} | Memory: {len(convo_memory.get("key_facts", []))} facts[/dim]',
        border_style='green'
    ))
    console.print()

    conversation = []

    while True:
        try:
            user_input = console.input('[cyan]Hugo:[/cyan] ').strip()
        except (KeyboardInterrupt, EOFError):
            console.print('\n[green]Goodbye![/green]')
            break

        if not user_input:
            continue

        if user_input.lower() in ['exit', 'quit', 'bye']:
            save_conversation_memory(convo_memory)
            stats = tracker.get_stats()
            console.print(f'\n[green]Tokens: {stats["tokens_used"]} | Cost: {stats["estimated_cost"]} | Uptime: {stats["uptime_minutes"]}min[/green]')
            break

        conversation.append({'role': 'user', 'content': user_input})
        if len(conversation) > 30:
            conversation = conversation[-30:]

        response, error = call_claude(conversation, TOOLS)
        if error:
            console.print(f'[red]Error: {error}[/red]')
            conversation = conversation[-4:]
            continue

        tracker.track(response.usage.input_tokens, response.usage.output_tokens)

        tool_count = 0
        max_tools = 50

        while response.stop_reason == 'tool_use' and tool_count < max_tools:
            # Print any text before tools
            for block in response.content:
                if block.type == 'text' and block.text.strip():
                    console.print(f'[green]Opus:[/green] {block.text}')

            # Execute tools and collect results
            tool_results = []
            for block in response.content:
                if block.type == 'tool_use':
                    tool_count += 1
                    console.print(f'[dim]   → {block.name}[/dim]')
                    
                    result = dispatch_tool(block.name, block.input)
                    
                    # Show result summary
                    if 'error' in result:
                        console.print(f'[red]   ✗ Error: {result["error"][:100]}[/red]')
                    
                    tool_results.append({
                        'type': 'tool_result',
                        'tool_use_id': block.id,
                        'content': json.dumps(result)[:4000]
                    })

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

        # Print final response
        final_text = ''
        for block in response.content:
            if block.type == 'text' and block.text.strip():
                final_text += block.text
                console.print(f'[green]Opus:[/green] {block.text}')

        if final_text.strip():
            conversation.append({'role': 'assistant', 'content': final_text.strip()})

        stats = tracker.get_stats()
        console.print(f'\n[dim](Tokens: {stats["tokens_used"]} | Cost: {stats["estimated_cost"]} | Tools: {tool_count})[/dim]\n')

if __name__ == '__main__':
    chat()
