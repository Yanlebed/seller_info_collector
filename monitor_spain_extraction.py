#!/usr/bin/env python3
"""
Monitor Spain Data Extraction Progress
"""

import os
import json
import subprocess
from datetime import datetime

def check_process_running():
    """Check if the extraction process is running"""
    try:
        result = subprocess.run(['pgrep', '-f', 'energy_label_data_extractor.*spain'], 
                              capture_output=True, text=True)
        return bool(result.stdout.strip())
    except:
        return False

def get_progress():
    """Get extraction progress for Spain"""
    progress_file = "energy_label_data/extracted_data/spain_progress.json"
    
    if os.path.exists(progress_file):
        with open(progress_file, 'r') as f:
            progress = json.load(f)
        return len(progress.get('processed_asins', []))
    return 0

def get_log_info():
    """Get recent log entries"""
    log_file = "spain_extraction.log"
    if os.path.exists(log_file):
        try:
            # Get file size
            size = os.path.getsize(log_file) / (1024 * 1024)  # MB
            
            # Get last few lines
            with open(log_file, 'r') as f:
                lines = f.readlines()
                recent_lines = lines[-5:] if len(lines) >= 5 else lines
            
            return size, recent_lines
        except:
            return 0, []
    return 0, []

def main():
    print("Spain Data Extraction Monitor")
    print("=" * 60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Check if process is running
    is_running = check_process_running()
    if is_running:
        print("✅ Spain extraction process is running")
        try:
            result = subprocess.run(['pgrep', '-f', 'energy_label_data_extractor.*spain'], 
                                  capture_output=True, text=True)
            pid = result.stdout.strip()
            print(f"   Process ID: {pid}")
        except:
            pass
    else:
        print("❌ Spain extraction process not found")
    
    print()
    
    # Get progress
    processed = get_progress()
    total = 3057  # Total links collected
    percentage = (processed / total * 100) if total > 0 else 0
    
    print(f"Spain Progress: {processed:,} / {total:,} ({percentage:.1f}%)")
    print()
    
    # Progress bar
    bar_length = 50
    filled_length = int(bar_length * processed / total) if total > 0 else 0
    bar = '█' * filled_length + '░' * (bar_length - filled_length)
    print(f"[{bar}] {percentage:.1f}%")
    print()
    
    # Log info
    log_size, recent_lines = get_log_info()
    print(f"Log file size: {log_size:.1f} MB")
    print()
    
    if recent_lines:
        print("Recent log entries:")
        print("-" * 40)
        for line in recent_lines:
            print(f"  {line.strip()}")
    
    print()
    print("Commands:")
    print("  python monitor_spain_extraction.py  - Run this monitor")
    print("  tail -f spain_extraction.log        - Follow live log")
    print("  pkill -f energy_label_data.*spain   - Stop extraction")
    print("  ls -la energy_label_data/extracted_data/spain/  - Check output files")

if __name__ == "__main__":
    main() 