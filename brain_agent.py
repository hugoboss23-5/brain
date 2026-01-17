import anthropic
import json
import requests
from rich.console import Console
from rich.markdown import Markdown

console = Console()

# Load config
with open('brain_config.json', 'r') as f:
    config = json.load(f)

client = anthropic.Anthropic(api_key=config['anthropic_api_key'])
brain_url = f"http://127.0.0.1:{config['server_port']}"

# System prompt that gives Claude access to brain
SYSTEM_PROMPT = '''You are Claude AI with direct access to Hugo's brain repository through an API server.

You can execute operations in the brain by using this tool schema. When Hugo asks you to do something, you can:
- Create files
- Read files  
- Execute Python code
- List directories

The brain is located at: C:\\Users\\bulli\\brain

When you need to do something in the brain, explain what you're doing, then execute it.
'''

def execute_in_brain(operation, **kwargs):
    '''Execute operation in brain server'''
    try:
        response = requests.post(f'{brain_url}/execute', json={'operation': operation, **kwargs})
        return response.json()
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def chat():
    console.print('[bold green]🧠 Brain Agent Active[/bold green]')
    console.print(f'Connected to brain at: {config["brain_path"]}')
    console.print('Type your requests. I have direct access to the brain.\\n')
    
    conversation = []
    
    while True:
        user_input = console.input('[bold blue]You:[/bold blue] ')
        
        if user_input.lower() in ['exit', 'quit']:
            console.print('[yellow]Shutting down brain agent...[/yellow]')
            break
        
        conversation.append({
            'role': 'user',
            'content': user_input
        })
        
        # Call Claude with context about brain capabilities
        response = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=conversation
        )
        
        assistant_message = response.content[0].text
        conversation.append({
            'role': 'assistant', 
            'content': assistant_message
        })
        
        console.print(f'\\n[bold green]Claude:[/bold green]')
        console.print(Markdown(assistant_message))
        console.print()

if __name__ == '__main__':
    chat()
