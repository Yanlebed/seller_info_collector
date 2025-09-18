#!/usr/bin/env python3
"""
Monitor Spain Extraction Progress (Resume)
==========================================
Monitors the resumed Spain extraction process after laptop reboot.
"""

import json
import os
import time
from datetime import datetime

def get_progress():
    """Get current extraction progress"""
    progress_file = "energy_label_data/extracted_data/spain_progress.json"
    log_file = "spain_extraction_resume.log"
    
    # Get processed count
    processed_count = 0
    if os.path.exists(progress_file):
        try:
            with open(progress_file, 'r') as f:
                data = json.load(f)
                processed_count = len(data.get('processed_asins', []))
        except:
            pass
    
    # Get total count from log
    total_count = 3057  # Known total for Spain
    
    # Get latest log entries
    latest_logs = []
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()
                latest_logs = [line.strip() for line in lines[-10:] if line.strip()]
        except:
            pass
    
    return {
        'processed': processed_count,
        'total': total_count,
        'remaining': total_count - processed_count,
        'percentage': (processed_count / total_count * 100) if total_count > 0 else 0,
        'latest_logs': latest_logs
    }

def main():
    print("🇪🇸 Spain Extraction Monitor (Resume)")
    print("=" * 50)
    print(f"Started monitoring at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    start_time = time.time()
    last_processed = 0
    
    try:
        while True:
            progress = get_progress()
            current_time = datetime.now().strftime('%H:%M:%S')
            elapsed = time.time() - start_time
            
            # Calculate rate
            if elapsed > 0 and progress['processed'] > last_processed:
                rate = (progress['processed'] - last_processed) / (elapsed / 3600)  # per hour
                eta_hours = progress['remaining'] / rate if rate > 0 else 0
                eta_str = f" | ETA: {eta_hours:.1f}h" if eta_hours > 0 else ""
            else:
                rate = 0
                eta_str = ""
            
            print(f"[{current_time}] Progress: {progress['processed']:,}/{progress['total']:,} "
                  f"({progress['percentage']:.1f}%) | Remaining: {progress['remaining']:,}"
                  f" | Rate: {rate:.0f}/h{eta_str}")
            
            # Show latest activity
            if progress['latest_logs']:
                latest = progress['latest_logs'][-1]
                if "✓ Extracted:" in latest:
                    brand_start = latest.find("✓ Extracted: ") + 14
                    brand_info = latest[brand_start:brand_start+60] + "..." if len(latest[brand_start:]) > 60 else latest[brand_start:]
                    print(f"    Latest: {brand_info}")
                elif "Processing product" in latest:
                    print(f"    Status: {latest.split(' - INFO - ')[-1] if ' - INFO - ' in latest else latest}")
            
            print()
            
            # Update for next iteration
            if progress['processed'] != last_processed:
                last_processed = progress['processed']
                start_time = time.time()  # Reset timer for rate calculation
            
            time.sleep(30)  # Check every 30 seconds
            
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")
        final_progress = get_progress()
        print(f"Final status: {final_progress['processed']:,}/{final_progress['total']:,} "
              f"({final_progress['percentage']:.1f}%) completed")

if __name__ == "__main__":
    main() 