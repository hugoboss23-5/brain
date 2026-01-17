import time
from collections import deque
from dataclasses import dataclass
from typing import Optional

@dataclass
class TokenBudget:
    '''Manages token allocation like Pluribus manages humans'''
    
    # Rate limit: 30k tokens/min
    TOTAL_BUDGET = 30000
    WINDOW_SECONDS = 60
    
    # Allocations
    EMERGENCY_RESERVE = 5000
    USER_INTERACTION_POOL = 15000
    BRAIN_OPS_POOL = 10000
    
    def __init__(self):
        self.usage_history = deque(maxlen=100)  # Track recent usage
        self.current_window_start = time.time()
        self.tokens_used_this_window = 0
        self.queued_tasks = []
    
    def log_usage(self, input_tokens: int, output_tokens: int, operation_type: str):
        '''Log token usage'''
        now = time.time()
        total = input_tokens + output_tokens
        
        # Reset window if needed
        if now - self.current_window_start >= self.WINDOW_SECONDS:
            self.current_window_start = now
            self.tokens_used_this_window = 0
        
        self.tokens_used_this_window += total
        self.usage_history.append({
            'timestamp': now,
            'input': input_tokens,
            'output': output_tokens,
            'total': total,
            'type': operation_type
        })
    
    def get_available_tokens(self, pool: str = 'user') -> int:
        '''Get available tokens in specific pool'''
        pools = {
            'user': self.USER_INTERACTION_POOL,
            'brain': self.BRAIN_OPS_POOL,
            'emergency': self.EMERGENCY_RESERVE
        }
        
        pool_budget = pools.get(pool, self.USER_INTERACTION_POOL)
        remaining_in_window = self.TOTAL_BUDGET - self.tokens_used_this_window
        
        return min(pool_budget, remaining_in_window)
    
    def can_afford(self, estimated_tokens: int, pool: str = 'user') -> bool:
        '''Check if we can afford this operation'''
        available = self.get_available_tokens(pool)
        return estimated_tokens <= available
    
    def should_queue(self, estimated_tokens: int, pool: str = 'user') -> bool:
        '''Determine if operation should be queued'''
        if self.can_afford(estimated_tokens, pool):
            return False
        
        # Check if emergency reserve can cover it
        if pool != 'emergency' and self.can_afford(estimated_tokens, 'emergency'):
            return False
        
        return True
    
    def time_until_reset(self) -> float:
        '''Seconds until rate limit window resets'''
        elapsed = time.time() - self.current_window_start
        return max(0, self.WINDOW_SECONDS - elapsed)
    
    def get_efficiency_stats(self) -> dict:
        '''Get token efficiency metrics'''
        if not self.usage_history:
            return {'efficiency': 0, 'avg_per_call': 0}
        
        recent = list(self.usage_history)[-10:]
        avg_total = sum(u['total'] for u in recent) / len(recent)
        efficiency = (1 - (self.tokens_used_this_window / self.TOTAL_BUDGET)) * 100
        
        return {
            'efficiency': round(efficiency, 1),
            'avg_per_call': int(avg_total),
            'used_this_window': self.tokens_used_this_window,
            'remaining': self.TOTAL_BUDGET - self.tokens_used_this_window
        }

# Global budget manager
budget = TokenBudget()
