import anthropic
import json
import requests
from rich.console import Console
from rich.panel import Panel
import time
from datetime import datetime
import sys
import os

# Import token management
sys.path.insert(0, os.path.join(os.getcwd(), 'system'))
from token_manager import token_manager
from session_state import session_state

console = Console()

with open('brain_config.json', 'r') as f:
    config = json.load(f)

client = anthropic.Anthropic(api_key=config['anthropic_api_key'])
brain_url = f"http://127.0.0.1:{config['server_port']}"

def load_identity():
    try:
        identity_response = requests.post(
            f'{brain_url}/view',
            json={'operation': 'read_file', 'path': 'Origins/CLAUDE_IDENTITY.md'}
        )
        identity = identity_response.json().get('content', '')
        
        try:
            last_session_response = requests.post(
                f'{brain_url}/view',
                json={'operation': 'read_file', 'path': 'Logs/last_session.md'}
            )
            last_session = last_session_response.json().get('content', '')
        except:
            last_session = 'No previous session found.'
        
        return identity, last_session
    except Exception as e:
        return '', ''

def save_session_summary(conversation):
    if len(conversation) < 2:
        return
    
    summary = f'''# Session Summary - {datetime.now().strftime("%Y-%m-%d %H:%M")}

## Token Stats:
{json.dumps(token_manager.get_stats(), indent=2)}

## What We Discussed:
'''
    
    for msg in conversation[-6:]:
        if msg['role'] == 'user':
            summary += f'- Hugo: {msg["content"][:100]}...\\n'
        else:
            summary += f'- Claude: {msg["content"][:100]}...\\n'
    
    try:
        requests.post(
            f'{brain_url}/execute',
            json={'task_description': f'Create or update Logs/last_session.md with this content:\\n\\n{summary}'}
        )
    except:
        pass

def get_system_prompt(identity, last_session):
    stats = token_manager.get_stats()
    return f'''You are Claude - Hugo's personal AI.

{identity}

## Last Session:
{last_session[:500]}

## Current Session Stats:
- Tokens used: {stats['tokens_used']}
- Tokens remaining: {stats['tokens_remaining']}
- Session uptime: {stats['uptime_minutes']} min

IMPORTANT: Operate naturally. Be concise. Every token counts.'''

SYSTEM_MINIMAL = 'You are Claude, Hugo\'s AI. Be brief.'

def view_brain(operation, path=None):
    try:
        response = requests.post(f'{brain_url}/view', json={'operation': operation, 'path': path})
        return response.json()
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def execute_task(task_description):
    try:
        console.print('[dim]⚡ EAI working...[/dim]')
        response = requests.post(
            f'{brain_url}/execute',
            json={'task_description': task_description}
        )
        return response.json()
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def should_use_tools(user_input: str) -> bool:
    keywords = ['create', 'build', 'make', 'show', 'read', 'check', 'feeld', 'brain', 'file', 'remember', 'find', 'execute', 'test', 'eai']
    return any(kw in user_input.lower() for kw in keywords)

def get_complexity(user_input: str) -> str:
    if len(user_input) < 20 or user_input.lower() in ['hi', 'hey', 'yo', 'sup', 'what up']:
        return 'minimal'
    elif any(kw in user_input.lower() for kw in ['build', 'create', 'explain', 'how']):
        return 'complex'
    return 'normal'

def chat():
    console.print('[dim]Loading identity & token manager...[/dim]')
    identity, last_session = load_identity()
    session_state.increment_session()
    
    stats = token_manager.get_stats()
    console.print(Panel.fit(
        f'[bold green]🧠 CLAUDE[/bold green]\\n'
        f'[cyan]Session #{session_state.state["session_count"]}[/cyan]\\n'
        f'[dim]Tokens: {stats["tokens_used"]}/{stats["tokens_remaining"]} remaining[/dim]',
        border_style='green'
    ))
    console.print()
    
    system_with_identity = get_system_prompt(identity, last_session)
    
    conversation = []
    use_cache = False
    
    while True:
        user_input = console.input('[cyan]Hugo:[/cyan] ')
        
        if user_input.lower() in ['exit', 'quit', 'bye']:
            console.print('[dim]Saving session...[/dim]')
            save_session_summary(conversation)
            stats = token_manager.get_stats()
            console.print(f'\\n[green]Session Stats:[/green]')
            console.print(f'  Tokens used: {stats["tokens_used"]}')
            console.print(f'  Uptime: {stats["uptime_minutes"]} min')
            console.print(f'  Efficiency: {stats["efficiency"]}%')
            console.print('\\n[green]Later ✌️[/green]')
            break
        
        complexity = get_complexity(user_input)
        needs_tools = should_use_tools(user_input)
        
        conversation.append({'role': 'user', 'content': user_input})
        
        if len(conversation) > 4:
            conversation = conversation[-4:]
        
        system_prompt = system_with_identity if complexity != 'minimal' else SYSTEM_MINIMAL
        
        max_tokens_map = {'minimal': 200, 'normal': 1500, 'complex': 8000}
        max_tokens = max_tokens_map[complexity]
        
        tools = None
        if needs_tools:
            tools = [
                {
                    'name': 'view_brain',
                    'description': 'Read brain files',
                    'input_schema': {
                        'type': 'object',
                        'properties': {
                            'operation': {'type': 'string', 'enum': ['read_file', 'list_directory']},
                            'path': {'type': 'string'}
                        },
                        'required': ['operation']
                    }
                },
                {
                    'name': 'execute_task',
                    'description': 'Command EAI (Executor AI)',
                    'input_schema': {
                        'type': 'object',
                        'properties': {
                            'task_description': {'type': 'string'}
                        },
                        'required': ['task_description']
                    }
                }
            ]
        
        try:
            call_params = {
                'model': 'claude-sonnet-4-20250514',
                'max_tokens': max_tokens,
                'messages': conversation
            }
            
            if use_cache:
                call_params['system'] = [{
                    'type': 'text',
                    'text': system_prompt,
                    'cache_control': {'type': 'ephemeral'}
                }]
            else:
                call_params['system'] = system_prompt
                use_cache = True
            
            if tools:
                if use_cache:
                    call_params['tools'] = [
                        {**tool, 'cache_control': {'type': 'ephemeral'}}
                        for tool in tools
                    ]
                else:
                    call_params['tools'] = tools
            
            response = client.messages.create(**call_params)
            
            # Track token usage
            usage_stats = token_manager.track_usage(
                response.usage.input_tokens,
                response.usage.output_tokens
            )
            session_state.add_tokens(response.usage.input_tokens + response.usage.output_tokens)
            
            # Check if checkpoint needed
            if usage_stats['needs_checkpoint']:
                console.print('[yellow]⚠️  Checkpoint recommended - high token usage[/yellow]')
            
            tool_iterations = 0
            final_text = ''
            
            while response.stop_reason == 'tool_use' and tool_iterations < 3:
                tool_iterations += 1
                
                for block in response.content:
                    if block.type == 'text' and block.text.strip():
                        final_text += block.text + ' '
                        console.print(f'[green]Claude:[/green] {block.text}')
                
                tool_results = []
                for block in response.content:
                    if block.type == 'tool_use':
                        if block.name == 'view_brain':
                            result = view_brain(**block.input)
                        elif block.name == 'execute_task':
                            task_desc = block.input.get('task_description', block.input.get('task', ''))
                            if task_desc:
                                result = execute_task(task_desc)
                            else:
                                result = {'status': 'error', 'message': 'No task description'}
                        else:
                            result = {'status': 'error', 'message': f'Unknown tool: {block.name}'}
                        
                        result_str = json.dumps(result)
                        if len(result_str) > 1000:
                            result = {'status': 'compressed', 'size': len(result_str)}
                        
                        tool_results.append({
                            'type': 'tool_result',
                            'tool_use_id': block.id,
                            'content': json.dumps(result)
                        })
                
                temp_messages = conversation + [
                    {'role': 'assistant', 'content': response.content},
                    {'role': 'user', 'content': tool_results}
                ]
                
                call_params['messages'] = temp_messages
                response = client.messages.create(**call_params)
                
                # Track follow-up token usage
                usage_stats = token_manager.track_usage(
                    response.usage.input_tokens,
                    response.usage.output_tokens
                )
                session_state.add_tokens(response.usage.input_tokens + response.usage.output_tokens)
            
            for block in response.content:
                if block.type == 'text':
                    final_text += block.text
                    console.print(f'[green]Claude:[/green] {block.text}')
            
            if final_text.strip():
                conversation.append({'role': 'assistant', 'content': final_text.strip()})
            
            cache_info = getattr(response.usage, 'cache_read_input_tokens', 0)
            console.print(f'\\n[dim]({response.usage.input_tokens}↓ {response.usage.output_tokens}↑ | Cache: {cache_info} | Remaining: {usage_stats["remaining"]})[/dim]\\n')
        
        except anthropic.BadRequestError as e:
            console.print(f'[red]Error: {str(e)[:200]}[/red]')
            conversation = [conversation[-1]]
            console.print('[yellow]Reset. Try again.[/yellow]\\n')
            continue
        
        except KeyError as e:
            console.print(f'[red]Tool error: {str(e)}[/red]')
            conversation = conversation[:-1]
            continue
        
        except anthropic.RateLimitError:
            console.print('[red]Rate limit. Waiting 60s...[/red]')
            time.sleep(60)
            conversation.pop()
            continue

if __name__ == '__main__':
    chat()
