import subprocess
import os
import sys
import time

def run_backend():
    print("Starting Backend (FastAPI)...")
    return subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--reload", "--port", "8000"], cwd="backend")

def run_frontend():
    print("Starting Frontend Server (Python http.server)...")
    return subprocess.Popen([sys.executable, "-m", "http.server", "3001"], cwd="frontend")

if __name__ == "__main__":
    backend_proc = None
    frontend_proc = None
    try:
        backend_proc = run_backend()
        frontend_proc = run_frontend()
        
        print("\n" + "="*50)
        print("STRATEGIC WAR ROOM IS NOW ACTIVE")
        print("Backend running at: http://localhost:8000")
        print("Frontend running at: http://localhost:3001")
        print("="*50 + "\n")
        
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        if backend_proc: backend_proc.terminate()
        if frontend_proc: frontend_proc.terminate()
