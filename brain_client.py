import requests
import json

class BrainClient:
    def __init__(self, base_url='http://127.0.0.1:8000'):
        self.base_url = base_url
    
    def execute(self, operation, **kwargs):
        response = requests.post(
            f'{self.base_url}/execute',
            json={'operation': operation, **kwargs}
        )
        return response.json()
    
    def claude_task(self, message, context=None):
        response = requests.post(
            f'{self.base_url}/claude_task',
            json={'message': message, 'context': context}
        )
        return response.json()
    
    def status(self):
        response = requests.get(f'{self.base_url}/status')
        return response.json()

# Example usage
if __name__ == '__main__':
    brain = BrainClient()
    print(brain.status())
