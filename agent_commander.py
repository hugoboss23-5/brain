import json
import time
from datetime import datetime
import os
class AgentCommander:
    def __init__(self):
        self.agents = {}
        self.tasks = []
        self.completed_tasks = []
        self.log_file = "commander_log.json"

    def register_agent(self, name, capabilities):
        self.agents[name] = {
            "status": "ready",
            "capabilities": capabilities,
            "current_task": None,
            "completed_tasks": 0
        }

    def assign_task(self, agent_name, task_description):
        if agent_name in self.agents:
            self.agents[agent_name]["current_task"] = task_description
            self.agents[agent_name]["status"] = "working"

    def complete_task(self, agent_name, result):
        if agent_name in self.agents:
            self.agents[agent_name]["status"] = "ready"
            self.agents[agent_name]["completed_tasks"] += 1
            self.completed_tasks.append({
                "agent": agent_name,
                "result": result,
                "timestamp": datetime.now().isoformat()
            })

    def get_status(self):
        return {
            "agents": self.agents,
            "total_completed": len(self.completed_tasks),
            "timestamp": datetime.now().isoformat()
        }

# Initialize the command center
commander = AgentCommander()