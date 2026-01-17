import json
import os
from datetime import datetime
import time

class TokenManager:
    '''Manages token usage to enable infinite operation'''
    
    def __init__(self, max_tokens_per_session=25000, checkpoint_interval=20000):
        self.max_tokens_per_session = max_tokens_per_session
        self.checkpoint_interval = checkpoint_interval
        self.current_usage = 0
        self.session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.session_start = time.time()
        self.state_file = 'system/token_manager_state.json'
        
        # Load previous state if exists
        self.load_state()
    
    def load_state(self):
        '''Load token manager state from previous session'''
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    self.current_usage = state.get('current_usage', 0)
        except:
            self.current_usage = 0
    
    def save_state(self):
        '''Save current state to disk'''
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        with open(self.state_file, 'w') as f:
            json.dump({
                'session_id': self.session_id,
                'current_usage': self.current_usage,
                'last_checkpoint': datetime.now().isoformat()
            }, f, indent=2)
    
    def track_usage(self, input_tokens, output_tokens):
        '''Track token usage and determine if checkpoint needed'''
        total = input_tokens + output_tokens
        self.current_usage += total
        
        needs_checkpoint = self.current_usage >= self.checkpoint_interval
        needs_reset = self.current_usage >= self.max_tokens_per_session
        
        self.save_state()
        
        return {
            'current_usage': self.current_usage,
            'needs_checkpoint': needs_checkpoint,
            'needs_reset': needs_reset,
            'remaining': self.max_tokens_per_session - self.current_usage
        }
    
    def checkpoint(self, conversation, context):
        '''Create checkpoint and compress conversation'''
        checkpoint_file = f'Logs/checkpoint_{self.session_id}.json'
        
        # Save full state
        checkpoint_data = {
            'session_id': self.session_id,
            'timestamp': datetime.now().isoformat(),
            'token_usage': self.current_usage,
            'conversation': conversation[-10:],  # Last 10 messages
            'context': context
        }
        
        os.makedirs('Logs', exist_ok=True)
        with open(checkpoint_file, 'w') as f:
            json.dump(checkpoint_data, f, indent=2)
        
        return checkpoint_file
    
    def reset(self):
        '''Reset token counter for new session'''
        self.current_usage = 0
        self.session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.session_start = time.time()
        self.save_state()
    
    def get_stats(self):
        '''Get current statistics'''
        uptime = time.time() - self.session_start
        return {
            'session_id': self.session_id,
            'uptime_minutes': round(uptime / 60, 1),
            'tokens_used': self.current_usage,
            'tokens_remaining': self.max_tokens_per_session - self.current_usage,
            'efficiency': round((1 - self.current_usage / self.max_tokens_per_session) * 100, 1)
        }

# Global token manager instance
token_manager = TokenManager()
