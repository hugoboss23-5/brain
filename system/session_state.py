import json
import os
from datetime import datetime

SESSION_STATE_FILE = "system/session_state.json"

class SessionState:
    def __init__(self):
        self.state = self._load()
    
    def _load(self):
        try:
            if os.path.exists(SESSION_STATE_FILE):
                with open(SESSION_STATE_FILE, 'r') as f:
                    return json.load(f)
        except:
            pass
        return {
            "created": datetime.now().isoformat(),
            "last_session": None,
            "working_on": None,
            "discovered_files": {},
            "directory_cache": {},
            "active_problems": [],
            "solved_problems": [],
            "hugo_preferences": {
                "wants_production_ready": True,
                "hates_confirmation_theater": True,
                "prefers_action_over_narration": True,
                "terminal_blocks_only": True,
                "building": ["FEELD", "Brain"]
            },
            "project_context": {
                "FEELD": "Payment system with 1% fee for global infrastructure. Safety Vault (20% cap) + Growth Vault (unlimited).",
                "Brain": "AI command center. Opus=commander, CodeLlama=hands, DeepSeek=thinker, TinyLlama=swarm."
            },
            "file_index": {},
            "last_viewed": [],
            "conversation_summary": ""
        }
    
    def save(self):
        os.makedirs(os.path.dirname(SESSION_STATE_FILE), exist_ok=True)
        self.state["last_updated"] = datetime.now().isoformat()
        with open(SESSION_STATE_FILE, 'w') as f:
            json.dump(self.state, f, indent=2)
    
    def set_working_on(self, task: str):
        self.state["working_on"] = {"task": task, "started": datetime.now().isoformat()}
        self.save()
    
    def cache_directory(self, path: str, contents: list):
        self.state["directory_cache"][path] = {
            "contents": contents,
            "cached_at": datetime.now().isoformat()
        }
        self.save()
    
    def get_cached_directory(self, path: str):
        cached = self.state["directory_cache"].get(path)
        if cached:
            return cached["contents"]
        return None
    
    def mark_file_viewed(self, path: str, summary: str = None):
        self.state["discovered_files"][path] = {
            "viewed_at": datetime.now().isoformat(),
            "summary": summary
        }
        self.state["last_viewed"] = (self.state["last_viewed"] + [path])[-20:]
        self.save()
    
    def add_problem(self, problem: str):
        self.state["active_problems"].append({
            "problem": problem,
            "added": datetime.now().isoformat()
        })
        self.save()
    
    def solve_problem(self, problem: str, solution: str):
        for p in self.state["active_problems"]:
            if p["problem"] == problem:
                self.state["active_problems"].remove(p)
                self.state["solved_problems"].append({
                    "problem": problem,
                    "solution": solution,
                    "solved": datetime.now().isoformat()
                })
                break
        self.save()
    
    def index_file(self, path: str, file_type: str, purpose: str):
        self.state["file_index"][path] = {
            "type": file_type,
            "purpose": purpose,
            "indexed": datetime.now().isoformat()
        }
        self.save()
    
    def search_files(self, query: str) -> list:
        results = []
        query_lower = query.lower()
        for path, info in self.state["file_index"].items():
            if query_lower in path.lower() or query_lower in info.get("purpose", "").lower():
                results.append({"path": path, **info})
        return results
    
    def get_context_summary(self) -> str:
        summary = []
        if self.state["working_on"]:
            summary.append(f"WORKING ON: {self.state['working_on']['task']}")
        if self.state["active_problems"]:
            summary.append(f"ACTIVE PROBLEMS: {', '.join(p['problem'] for p in self.state['active_problems'][:3])}")
        if self.state["last_viewed"]:
            summary.append(f"RECENTLY VIEWED: {', '.join(self.state['last_viewed'][-5:])}")
        return "\n".join(summary)
    
    def end_session(self, summary: str):
        self.state["last_session"] = {
            "ended": datetime.now().isoformat(),
            "summary": summary,
            "was_working_on": self.state.get("working_on")
        }
        self.state["conversation_summary"] = summary
        self.save()

session_state = SessionState()
