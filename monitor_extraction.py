#!/usr/bin/env python3
"""
Data Extraction Monitor

This script monitors the progress of the data extraction process.
"""

import os
import json
import time
from datetime import datetime

def format_size(bytes):
    """Format file size in human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024.0:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024.0

def read_progress_files():
    """Read progress from all country progress files"""
    progress_dir = "energy_label_data/extracted_data"
    progress_files = [f for f in os.listdir(progress_dir) if f.endswith('_progress.json')]
    
    total_processed = 0
    countries_progress = {}
    
    for progress_file in progress_files:
        country = progress_file.replace('_progress.json', '')
        try:
            with open(os.path.join(progress_dir, progress_file), 'r') as f:
                data = json.load(f)
                processed = len(data.get('processed_asins', []))
                total_processed += processed
                countries_progress[country] = processed
        except Exception as e:
            countries_progress[country] = f"Error: {str(e)}"
    
    return total_processed, countries_progress

def count_links_files():
    """Count total links available for processing"""
    links_dir = "energy_label_data/product_links"
    link_files = [f for f in os.listdir(links_dir) if 'product_links_' in f and f.endswith('.json')]
    
    total_links = 0
    countries_links = {}
    
    for link_file in link_files:
        if 'spain' not in link_file:  # Skip old spain test files
            try:
                with open(os.path.join(links_dir, link_file), 'r') as f:
                    data = json.load(f)
                    links_count = data.get('total_links', 0)
                    total_links += links_count
                    
                    # Extract country from filename
                    country = link_file.split('_product_links_')[0]
                    countries_links[country] = links_count
            except Exception as e:
                pass
    
    return total_links, countries_links

def check_log_file():
    """Check the latest log entries"""
    log_file = "extraction_full.log"
    if os.path.exists(log_file):
        # Get file size and last few lines
        size = os.path.getsize(log_file)
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()
                return size, lines[-10:] if len(lines) >= 10 else lines
        except:
            return size, ["Could not read log file"]
    return 0, ["Log file not found"]

def main():
    """Main monitoring function"""
    print("Data Extraction Monitor")
    print("=" * 60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Check if process is running
    try:
        result = os.popen("ps aux | grep 'energy_label_data_extractor.py' | grep -v grep").read()
        if result.strip():
            print("✅ Data extraction process is running")
            lines = result.strip().split('\n')
            for line in lines:
                parts = line.split()
                if len(parts) >= 2:
                    print(f"   Process ID: {parts[1]}")
        else:
            print("❌ Data extraction process not found")
    except:
        print("❓ Could not check process status")
    
    print()
    
    # Progress statistics
    total_links, countries_links = count_links_files()
    total_processed, countries_progress = read_progress_files()
    
    if total_links > 0:
        percentage = (total_processed / total_links) * 100
        print(f"Overall Progress: {total_processed:,} / {total_links:,} ({percentage:.1f}%)")
        print()
        
        print("Country Progress:")
        print("-" * 40)
        for country in countries_links:
            links = countries_links[country]
            processed = countries_progress.get(country, 0)
            if isinstance(processed, int):
                country_percentage = (processed / links) * 100 if links > 0 else 0
                print(f"  {country:12}: {processed:4,} / {links:4,} ({country_percentage:5.1f}%)")
            else:
                print(f"  {country:12}: {processed}")
    else:
        print("No link files found")
    
    print()
    
    # Log file status
    log_size, recent_lines = check_log_file()
    print(f"Log file size: {format_size(log_size)}")
    print("\nRecent log entries:")
    print("-" * 40)
    for line in recent_lines:
        print(f"  {line.strip()}")
    
    print()
    print("Commands:")
    print("  python monitor_extraction.py     - Run this monitor")
    print("  tail -f extraction_full.log      - Follow live log")
    print("  pkill -f energy_label_data       - Stop extraction")
    print("  ls -la energy_label_data/extracted_data/  - Check output files")

if __name__ == "__main__":
    main() 