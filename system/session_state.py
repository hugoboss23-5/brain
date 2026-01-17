import json
import os
from datetime import datetime

class SessionState:
    '''Manages persistent session state for infinite operation'''
    
    def __init__(self, state_file='system/session_state.json'):
        self.state_file = state_file
        self.state = self.load()
    
    def load(self):
        '''Load session state'''
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    return json.load(f)
        except:
            pass
        
        return {
            'session_count': 0,
            'total_tokens_used': 0,
            'active_tasks': [],
            'completed_tasks': [],
            'context_summary': '',
            'last_updated': None
        }
    
    def save(self):
        '''Save session state'''
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        self.state['last_updated'] = datetime.now().isoformat()
        with open(self.state_file, 'w') as f:
            json.dump(self.state, f, indent=2)
    
    def add_task(self, task_description, priority='normal'):
        '''Add task to queue'''
        task = {
            'id': len(self.state['active_tasks']) + 1,
            'description': task_description,
            'priority': priority,
            'added': datetime.now().isoformat(),
            'status': 'pending'
        }
        self.state['active_tasks'].append(task)
        self.save()
        return task['id']
    
    def complete_task(self, task_id):
        '''Mark task as completed'''
        for task in self.state['active_tasks']:
            if task['id'] == task_id:
                task['status'] = 'completed'
                task['completed'] = datetime.now().isoformat()
                self.state['completed_tasks'].append(task)
                self.state['active_tasks'].remove(task)
                break
        self.save()
    
    def get_active_tasks(self):
        '''Get all pending tasks'''
        return [t for t in self.state['active_tasks'] if t['status'] == 'pending']
    
    def update_context(self, summary):
        '''Update context summary'''
        self.state['context_summary'] = summary
        self.save()
    
    def increment_session(self):
        '''Increment session counter'''
        self.state['session_count'] += 1
        self.save()
    
    def add_tokens(self, count):
        '''Track total tokens used'''
        self.state['total_tokens_used'] += count
        self.save()

# Global session state
session_state = SessionState()
