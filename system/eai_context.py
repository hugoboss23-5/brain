import json
import os

CONTEXT_FILE = "system/eai_context.json"

DEFAULT_CONTEXT = {
    "coding_standards": {
        "python": {
            "style": "Clean, production-ready, with error handling",
            "includes": ["type hints", "docstrings", "logging", "try/except"],
            "avoids": ["print debugging", "bare except", "magic numbers"]
        },
        "javascript": {
            "style": "Modern ES6+, async/await, proper error handling",
            "includes": ["const/let", "arrow functions", "destructuring"],
            "avoids": ["var", "callback hell", "any type"]
        },
        "html": {
            "style": "Modern, responsive, accessible",
            "includes": ["semantic tags", "ARIA labels", "mobile-first"],
            "avoids": ["inline styles", "tables for layout", "deprecated tags"]
        }
    },
    "project_patterns": {
        "FEELD": {
            "stack": "Python backend, React frontend, PostgreSQL",
            "patterns": ["REST API", "JWT auth", "Vault system"],
            "key_files": {
                "payment_flow": "FEELD/src/payment_flow.py",
                "vault_system": "FEELD/src/vaults.py",
                "api": "FEELD/src/api.py"
            }
        },
        "Brain": {
            "stack": "Python, FastAPI, Ollama",
            "patterns": ["Tool-based AI", "Swarm workers", "Persistent memory"],
            "key_files": {
                "server": "brain_server.py",
                "orchestrator": "brain_orchestrator.py",
                "swarm": "swarm/swarm_commander.py"
            }
        }
    },
    "hugo_preferences": {
        "communication": "Direct, no fluff, action-oriented",
        "code_quality": "Production-ready, not prototypes",
        "confirmation": "Trust the system, don't ask for verification",
        "format": "Terminal blocks only for edits"
    },
    "quality_rules": [
        "Every function has error handling",
        "Every file has a clear purpose",
        "No stub implementations - full working code",
        "Include logging for debugging",
        "Match existing code style in the project"
    ]
}

def load_eai_context():
    try:
        if os.path.exists(CONTEXT_FILE):
            with open(CONTEXT_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return DEFAULT_CONTEXT

def save_eai_context(context):
    os.makedirs(os.path.dirname(CONTEXT_FILE), exist_ok=True)
    with open(CONTEXT_FILE, 'w') as f:
        json.dump(context, f, indent=2)

def get_eai_system_prompt(task_description: str) -> str:
    ctx = load_eai_context()
    
    # Detect project from task
    project = None
    if "feeld" in task_description.lower() or "payment" in task_description.lower():
        project = "FEELD"
    elif "brain" in task_description.lower() or "swarm" in task_description.lower():
        project = "Brain"
    
    prompt = """You are EAI, an executor. You DO, you don't think. RESPOND ONLY WITH JSON.

QUALITY RULES:
"""
    for rule in ctx["quality_rules"]:
        prompt += f"- {rule}\n"
    
    if project and project in ctx["project_patterns"]:
        proj = ctx["project_patterns"][project]
        prompt += f"\nPROJECT CONTEXT ({project}):\n"
        prompt += f"- Stack: {proj['stack']}\n"
        prompt += f"- Patterns: {', '.join(proj['patterns'])}\n"
    
    prompt += f"\nHUGO'S STANDARDS:\n"
    prompt += f"- {ctx['hugo_preferences']['code_quality']}\n"
    prompt += f"- {ctx['hugo_preferences']['confirmation']}\n"
    
    prompt += """
OUTPUT FORMAT:
{"action": "create_file", "path": "file.py", "content": "full production code"}
[{"action": "create_file", "path": "a.py", "content": "..."}, {"action": "create_file", "path": "b.py", "content": "..."}]
{"action": "execute_python", "code": "..."}
{"action": "list_dir", "path": "folder"}

ONLY JSON. NO MARKDOWN. NO EXPLANATION."""
    
    return prompt

# Initialize context file
if not os.path.exists(CONTEXT_FILE):
    save_eai_context(DEFAULT_CONTEXT)
