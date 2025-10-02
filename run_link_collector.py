#!/usr/bin/env python3
"""
Energy Label Link Collector Runner

This script provides an easy way to run the link collector for all countries
with robust resume functionality and error handling.

Usage:
  python run_link_collector.py                    # Run with resume (default)
  python run_link_collector.py --status           # Show current status
  python run_link_collector.py --no-resume        # Start fresh
  python run_link_collector.py --reset            # Reset progress and start over
  python run_link_collector.py --countries spain,italy  # Run specific countries
"""

import asyncio
import os
import sys
from datetime import datetime

def main():
    """Main runner function"""
    
    print("Energy Label Link Collector Runner")
    print("=" * 60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Check if we have command line arguments
    if len(sys.argv) > 1:
        # Pass arguments directly to the link collector
        os.system(f"python energy_label_link_collector.py {' '.join(sys.argv[1:])}")
    else:
        print("Running link collector for ALL countries with resume enabled...")
        print()
        print("Available options:")
        print("  --status         Show current collection status")
        print("  --no-resume      Start fresh without loading previous progress")
        print("  --reset          Reset all progress and start over")
        print("  --countries X,Y  Run only specific countries")
        print("  --no-headless    Show browser window (for debugging)")
        print()
        
        # Ask user what they want to do
        while True:
            choice = input("What would you like to do?\n"
                          "1. Check status\n"
                          "2. Start/resume collection\n"
                          "3. Reset progress\n"
                          "4. Start fresh (no resume)\n"
                          "5. Exit\n"
                          "Enter choice (1-5): ").strip()
            
            if choice == '1':
                os.system("python energy_label_link_collector.py --status")
                break
            elif choice == '2':
                print("\nStarting link collection with resume enabled...")
                os.system("python energy_label_link_collector.py")
                break
            elif choice == '3':
                confirm = input("Are you sure you want to reset all progress? (y/N): ")
                if confirm.lower() == 'y':
                    os.system("python energy_label_link_collector.py --reset")
                break
            elif choice == '4':
                confirm = input("Are you sure you want to start fresh? (y/N): ")
                if confirm.lower() == 'y':
                    print("\nStarting fresh collection...")
                    os.system("python energy_label_link_collector.py --no-resume")
                break
            elif choice == '5':
                print("Goodbye!")
                break
            else:
                print("Invalid choice. Please enter 1-5.")
                continue

if __name__ == "__main__":
    main() 