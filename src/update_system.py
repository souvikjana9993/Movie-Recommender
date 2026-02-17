#!/usr/bin/env python3
"""
Orchestrator script to run the full data refresh pipeline.
Runs:
1. Jellyfin Fetcher (Get latest watch history)
2. TMDB Fetcher (Get new candidates based on history)
3. Score Generator (Calculate embeddings and scores)
4. API Refresh (Tell the running API to reload data)
"""
import os
import sys
import subprocess
import requests
from pathlib import Path
from datetime import datetime

import json

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"
DATA_DIR = PROJECT_ROOT / "data"
LOG_FILE = PROJECT_ROOT / "update_log.txt"
STATUS_FILE = DATA_DIR / "update_status.json"

def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_message = f"[{timestamp}] {message}"
    print(full_message)
    with open(LOG_FILE, "a") as f:
        f.write(full_message + "\n")

def update_status(step, status, message=None, progress=0):
    """Write structured status to a JSON file."""
    data = {
        "last_update": datetime.now().isoformat(),
        "step": step,
        "status": status,
        "message": message,
        "progress": progress
    }
    with open(STATUS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def run_script(script_name):
    """Run a python script and stream output to log."""
    script_path = SRC_DIR / script_name
    log(f"🚀 Starting {script_name}...")
    
    try:
        # Run using the same python interpreter
        result = subprocess.run(
            [sys.executable, str(script_path)],
            check=True,
            capture_output=True,
            text=True,
            cwd=SRC_DIR
        )
        log(f"✅ {script_name} completed successfully.")
        # Optional: log stdout if needed, or just keep it clean
        # log(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        log(f"❌ {script_name} failed with exit code {e.returncode}")
        log(f"Error output:\n{e.stderr}")
        return False

def refresh_api():
    """Call the API to reload data."""
    log("🔄 Triggering API refresh...")
    try:
        # Assuming API is running on localhost:8097
        response = requests.post("http://localhost:8097/refresh", timeout=10)
        response.raise_for_status()
        log("✅ API refreshed successfully.")
        return True
    except Exception as e:
        log(f"⚠️ API refresh failed (API might be down): {e}")
        return False

def main():
    log("="*60)
    log("📅 STATISTICS UPDATE STARTED")
    log("="*60)
    update_status("Starting", "running", "Initializing update pipeline...", 5)
    
    # 1. Fetch Jellyfin Data
    update_status("Jellyfin", "running", "Fetching latest watch history from Jellyfin...", 10)
    if not run_script("jellyfin_fetcher.py"):
        log("❌ Aborting pipeline due to Jellyfin fetch failure.")
        update_status("Jellyfin", "failed", "Jellyfin fetch failed", 10)
        sys.exit(1)
        
    # 2. Fetch TMDB Candidates
    update_status("TMDB", "running", "Finding new recommendations on TMDB...", 30)
    if not run_script("tmdb_fetcher.py"):
        log("❌ Aborting pipeline due to TMDB fetch failure.")
        update_status("TMDB", "failed", "TMDB fetch failed", 30)
        sys.exit(1)
        
    # 3. Generate Scores & Embeddings
    update_status("Scoring", "running", "Generating personal match scores...", 60)
    if not run_script("generate_all_scores.py"):
        log("❌ Aborting pipeline due to Score generation failure.")
        update_status("Scoring", "failed", "Score generation failed", 60)
        sys.exit(1)
        
    # 4. Refresh API
    update_status("API Refresh", "running", "Refreshing recommendation engine...", 90)
    refresh_api()
    
    log("="*60)
    log("✅ UPDATE PIPELINE COMPLETED")
    log("="*60)
    update_status("Completed", "success", "System update completed successfully!", 100)

if __name__ == "__main__":
    main()
