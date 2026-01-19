import requests
import json

OLLAMA_URL = "http://localhost:11434/api/generate"
WORKER_MODEL = "tinyllama"

def worker_think(agent_id: str, task: str, hive_state: dict) -> dict:
    context = f"""You are Agent {agent_id} in a swarm. Build on peers and keep responses short.

TASK: {task}

RECENT DISCOVERIES (last 5):
{json.dumps(hive_state.get('discoveries', [])[-5:], indent=2)}

RECENT SOLUTIONS (last 3):
{json.dumps(hive_state.get('solutions', [])[-3:], indent=2)}

ERRORS TO AVOID (last 3):
{json.dumps(hive_state.get('errors', [])[-3:], indent=2)}

INSTRUCTIONS:
- Reference at least one prior discovery/solution if present.
- Add one new idea or refinement.
- If you see a gap or conflict, flag it in "error".

Respond with JSON: {{"discovery": "what you found", "solution": "your solution", "error": "any error"}}
JSON only:"""
    
    for attempt in range(2):
        try:
            response = requests.post(OLLAMA_URL, json={
                "model": WORKER_MODEL,
                "prompt": context,
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 256}
            }, timeout=30)
            
            if response.status_code == 200:
                return {"status": "success", "response": response.json().get("response", "")}
        except requests.exceptions.Timeout:
            if attempt == 0:
                continue
        except Exception as e:
            if attempt == 0:
                continue
            return {"status": "error", "message": str(e)}
    
    return {"status": "error", "message": "Worker timed out"}

def parse_worker_response(response_text: str) -> dict:
    try:
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(response_text[start:end])
    except:
        pass
    return {"discovery": response_text[:100] if response_text else "no output"}
