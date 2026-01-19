import json
from pathlib import Path
from datetime import datetime
import threading

class HiveMind:
    def __init__(self):
        self.memory_file = Path("swarm/hive_memory.json")
        self.memory_file.parent.mkdir(exist_ok=True)
        self.lock = threading.Lock()
        self.state = {
            "task": None,
            "discoveries": [],
            "errors": [],
            "solutions": [],
            "agent_status": {},
            "votes": {}
        }
        self._load()
    
    def _load(self):
        if self.memory_file.exists():
            try:
                self.state = json.loads(self.memory_file.read_text())
            except:
                pass
    
    def _save(self):
        self.memory_file.write_text(json.dumps(self.state, indent=2))
    
    def set_task(self, task: str):
        with self.lock:
            self.state["task"] = task
            self.state["discoveries"] = []
            self.state["errors"] = []
            self.state["solutions"] = []
            self.state["votes"] = {}
            self._save()
    
    def broadcast(self, agent_id: str, message_type: str, content):
        with self.lock:
            entry = {
                "agent": agent_id,
                "type": message_type,
                "content": content,
                "timestamp": datetime.now().isoformat()
            }
            if message_type == "discovery":
                self.state["discoveries"].append(entry)
            elif message_type == "error":
                self.state["errors"].append(entry)
            elif message_type == "solution":
                self.state["solutions"].append(entry)
            self.state["agent_status"][agent_id] = "active"
            self._save()

    def read_all(self) -> dict:
        with self.lock:
            self._load()
            return self.state.copy()
    
    def vote(self, agent_id: str, proposal: str):
        with self.lock:
            if proposal not in self.state["votes"]:
                self.state["votes"][proposal] = []
            if agent_id not in self.state["votes"][proposal]:
                self.state["votes"][proposal].append(agent_id)
            self._save()
    
    def get_consensus(self):
        with self.lock:
            if not self.state["votes"]:
                return None
            return max(self.state["votes"], key=lambda x: len(self.state["votes"][x]))
    
    def get_all_discoveries(self):
        with self.lock:
            return self.state["discoveries"]
    
    def agent_count(self):
        with self.lock:
            return len(self.state["agent_status"])

    def mark_agent(self, agent_id: str, status: str):
        """Set agent status explicitly (launching/active/failed)."""
        with self.lock:
            self.state["agent_status"][agent_id] = status
            self._save()

hive = HiveMind()
