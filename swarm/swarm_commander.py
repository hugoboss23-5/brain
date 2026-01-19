import concurrent.futures
import time
import json
from swarm.hive_mind import hive
from swarm.swarm_worker import worker_think, parse_worker_response

def run_swarm(task: str, num_agents: int = 50, rounds: int = 2) -> dict:
    print(f"[PLURIBUS] Starting swarm: {num_agents} agents, {rounds} rounds")
    hive.set_task(task)
    
    successful_agents = 0
    failed_agents = 0
    
    for round_num in range(rounds):
        print(f"[PLURIBUS] Round {round_num + 1}/{rounds}")
        hive_state = hive.read_all()
        # mark all agents as launching for visibility
        for i in range(num_agents):
            hive.mark_agent(f"agent_{i}", "launching")
        
        def run_agent(agent_id):
            try:
                result = worker_think(f"agent_{agent_id}", task, hive_state)
                if result["status"] == "success":
                    parsed = parse_worker_response(result["response"])
                    if parsed.get("discovery"):
                        hive.broadcast(f"agent_{agent_id}", "discovery", parsed["discovery"])
                    if parsed.get("solution"):
                        hive.broadcast(f"agent_{agent_id}", "solution", parsed["solution"])
                        hive.vote(f"agent_{agent_id}", str(parsed["solution"])[:200])
                    if parsed.get("error"):
                        hive.broadcast(f"agent_{agent_id}", "error", parsed["error"])
                    hive.mark_agent(f"agent_{agent_id}", "active")
                    return {"success": True, "parsed": parsed}
                hive.mark_agent(f"agent_{agent_id}", "failed")
                return {"success": False, "error": result.get("message")}
            except Exception as e:
                hive.mark_agent(f"agent_{agent_id}", "failed")
                return {"success": False, "error": str(e)}
        
        round_success = 0
        round_fail = 0
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            futures = {executor.submit(run_agent, i): i for i in range(num_agents)}
            for future in concurrent.futures.as_completed(futures, timeout=90):
                try:
                    result = future.result(timeout=15)
                    if result.get("success"):
                        round_success += 1
                    else:
                        round_fail += 1
                except:
                    round_fail += 1
        
        successful_agents += round_success
        failed_agents += round_fail
        print(f"[PLURIBUS] Round {round_num + 1} done: {round_success} success, {round_fail} failed")
        time.sleep(0.3)
    
    consensus = hive.get_consensus()
    final_state = hive.read_all()
    
    return {
        "status": "success",
        "task": task,
        "agents_deployed": num_agents * rounds,
        "successful": successful_agents,
        "failed": failed_agents,
        "discoveries": len(final_state.get("discoveries", [])),
        "solutions": len(final_state.get("solutions", [])),
        "consensus": consensus,
        "top_discoveries": final_state.get("discoveries", [])[-5:],
        "votes": final_state.get("votes", {})
    }
