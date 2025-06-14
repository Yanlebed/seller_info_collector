#!/usr/bin/env python3
"""
Diagnostic script to check if EnergyLabelScraper has all required methods
"""

import sys
import os

try:
    from energy_label_scraper import EnergyLabelScraper

    print("✓ Successfully imported EnergyLabelScraper")

    # Check for required methods
    methods_to_check = [
        'handle_cookie_banner',
        'handle_intermediate_page',
        'check_for_energy_label',
        'extract_product_info',
        'search_category',
        'process_search_results',
        'random_delay'
    ]

    print("\nChecking for required methods:")
    for method_name in methods_to_check:
        if hasattr(EnergyLabelScraper, method_name):
            print(f"✓ {method_name} - Found")
        else:
            print(f"✗ {method_name} - NOT FOUND")

    # List all methods in the class
    print("\nAll methods in EnergyLabelScraper:")
    for attr in dir(EnergyLabelScraper):
        if not attr.startswith('_') and callable(getattr(EnergyLabelScraper, attr)):
            print(f"  - {attr}")

    # Check file location
    import energy_label_scraper

    print(f"\nLoaded from: {energy_label_scraper.__file__}")

    # Check file modification time
    if os.path.exists(energy_label_scraper.__file__):
        import datetime

        mtime = os.path.getmtime(energy_label_scraper.__file__)
        mod_time = datetime.datetime.fromtimestamp(mtime)
        print(f"Last modified: {mod_time}")

except ImportError as e:
    print(f"✗ Failed to import EnergyLabelScraper: {e}")
    sys.exit(1)