#!/usr/bin/env python3
"""
EMERGENCY SHUTDOWN SCRIPT - FEELD Team Agents
Stops all running FEELD processes to prevent token burn
"""

import psutil
import os
import sys
import signal
import time
from datetime import datetime

def find_and_kill_feeld_processes():
    """Find and kill all FEELD-related processes"""
    killed_processes = []
    
    print(f"[{datetime.now()}] EMERGENCY SHUTDOWN - Scanning for FEELD processes...")
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
        try:
            cmdline_str = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
            
            # Look for FEELD, agent, or brain processes
            keywords = ['feeld', 'agent', 'brain_agent', 'brain_server', 'brain_orchestrator']
            
            if any(keyword in cmdline_str.lower() for keyword in keywords):
                print(f"FOUND TARGET: PID {proc.info['pid']} - {cmdline_str}")
                
                # Don't kill ourselves
                if proc.info['pid'] == os.getpid():
                    print("  -> Skipping self")
                    continue
                
                try:
                    # Try graceful shutdown first
                    proc.terminate()
                    proc.wait(timeout=3)
                    killed_processes.append({
                        'pid': proc.info['pid'],
                        'cmdline': cmdline_str,
                        'method': 'terminate'
                    })
                    print(f"  -> TERMINATED PID {proc.info['pid']}")
                    
                except psutil.TimeoutExpired:
                    # Force kill if graceful doesn't work
                    proc.kill()
                    killed_processes.append({
                        'pid': proc.info['pid'],
                        'cmdline': cmdline_str,
                        'method': 'kill'
                    })
                    print(f"  -> FORCE KILLED PID {proc.info['pid']}")
                    
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except Exception as e:
            print(f"Error processing PID {proc.info['pid']}: {e}")
    
    return killed_processes

def main():
    print("="*60)
    print("EMERGENCY FEELD AGENT SHUTDOWN")
    print("="*60)
    
    killed = find_and_kill_feeld_processes()
    
    if killed:
        print(f"\nSUCCESS: Killed {len(killed)} processes:")
        for proc in killed:
            print(f"  - PID {proc['pid']} ({proc['method']}): {proc['cmdline'][:80]}...")
    else:
        print("\nNo FEELD processes found running.")
    
    print(f"\nShutdown completed at {datetime.now()}")
    print("="*60)

if __name__ == "__main__":
    main()