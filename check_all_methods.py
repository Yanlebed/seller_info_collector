#!/usr/bin/env python3
"""
Comprehensive diagnostic script to check if EnergyLabelScraper has all required methods
"""

import sys
import os
import inspect

try:
    from energy_label_scraper import EnergyLabelScraper

    print("✓ Successfully imported EnergyLabelScraper")

    # Define all methods that should exist
    required_methods = {
        # Core scraping methods
        'random_delay': 'Add random delay between actions',
        'setup_camoufox': 'Setup Camoufox browser with fingerprinting',
        'handle_cookie_banner': 'Handle cookie consent banners',
        'handle_intermediate_page': 'Handle intermediate pages (IT, ES, FR)',
        'check_for_energy_label': 'Check if product has energy label',
        'extract_brand_from_product_page': 'Extract brand from product page',
        'extract_product_info': 'Extract all product information',
        'search_category': 'Search for a product category',
        'process_search_results': 'Process search results page by page',

        # Country and data processing
        'scrape_country': 'Scrape all categories for a country',
        'scrape_all_countries': 'Scrape all configured countries',

        # Saving methods - Overall
        'save_results': 'Save overall results',
        'save_detailed_results': 'Save detailed product information',
        'save_brand_summary': 'Save brand summary',
        'save_overall_summary': 'Save overall summary across countries',

        # Saving methods - Country specific
        'save_country_results': 'Save results for specific country',
        'save_country_detailed_results': 'Save country-specific product details',
        'save_country_brand_summary': 'Save country-specific brand summary',
        'save_country_brand_analysis': 'Save country-specific brand analysis',

        # Utility methods
        'print_summary': 'Print results summary',
    }

    print(f"\nChecking for {len(required_methods)} required methods:")
    print("=" * 70)

    missing_methods = []
    found_methods = []

    for method_name, description in required_methods.items():
        if hasattr(EnergyLabelScraper, method_name):
            method = getattr(EnergyLabelScraper, method_name)
            if callable(method):
                print(f"✓ {method_name:<35} - {description}")
                found_methods.append(method_name)
            else:
                print(f"✗ {method_name:<35} - EXISTS but NOT CALLABLE")
                missing_methods.append(method_name)
        else:
            print(f"✗ {method_name:<35} - NOT FOUND")
            missing_methods.append(method_name)

    print("\n" + "=" * 70)
    print(f"Summary: {len(found_methods)}/{len(required_methods)} methods found")

    if missing_methods:
        print(f"\n⚠️  Missing {len(missing_methods)} methods:")
        for method in missing_methods:
            print(f"   - {method}")
    else:
        print("\n✅ All required methods are present!")

    # Check for method signatures of critical methods
    print("\n" + "=" * 70)
    print("Checking method signatures for critical methods:")
    print("=" * 70)

    critical_methods = [
        'handle_cookie_banner',
        'handle_intermediate_page',
        'check_for_energy_label',
        'extract_product_info',
        'save_country_results'
    ]

    for method_name in critical_methods:
        if hasattr(EnergyLabelScraper, method_name):
            method = getattr(EnergyLabelScraper, method_name)
            if callable(method):
                sig = inspect.signature(method)
                params = [p for p in sig.parameters.keys() if p != 'self']
                print(f"\n{method_name}({', '.join(params)})")

                # Get docstring if available
                if method.__doc__:
                    first_line = method.__doc__.strip().split('\n')[0]
                    print(f"   → {first_line}")

    # List all methods in the class (including inherited)
    print("\n" + "=" * 70)
    print("All methods in EnergyLabelScraper:")
    print("=" * 70)

    all_methods = []
    for attr in dir(EnergyLabelScraper):
        if not attr.startswith('_'):
            obj = getattr(EnergyLabelScraper, attr)
            if callable(obj):
                all_methods.append(attr)

    # Group methods by category
    print("\nCore Methods:")
    core_methods = [m for m in all_methods if m in ['random_delay', 'setup_camoufox', 'handle_cookie_banner',
                                                    'handle_intermediate_page', 'check_for_energy_label']]
    for method in sorted(core_methods):
        print(f"  - {method}")

    print("\nExtraction Methods:")
    extract_methods = [m for m in all_methods if 'extract' in m or 'search' in m or 'process' in m]
    for method in sorted(extract_methods):
        print(f"  - {method}")

    print("\nScraping Methods:")
    scrape_methods = [m for m in all_methods if 'scrape' in m]
    for method in sorted(scrape_methods):
        print(f"  - {method}")

    print("\nSaving Methods:")
    save_methods = [m for m in all_methods if 'save' in m]
    for method in sorted(save_methods):
        print(f"  - {method}")

    print("\nOther Methods:")
    other_methods = [m for m in all_methods if m not in core_methods + extract_methods + scrape_methods + save_methods]
    for method in sorted(other_methods):
        print(f"  - {method}")

    # Check file location and modification time
    import energy_label_scraper

    print(f"\n{'=' * 70}")
    print(f"File Information:")
    print(f"{'=' * 70}")
    print(f"Loaded from: {energy_label_scraper.__file__}")

    if os.path.exists(energy_label_scraper.__file__):
        import datetime

        mtime = os.path.getmtime(energy_label_scraper.__file__)
        mod_time = datetime.datetime.fromtimestamp(mtime)
        print(f"Last modified: {mod_time}")

        # Get file size
        size = os.path.getsize(energy_label_scraper.__file__)
        print(f"File size: {size:,} bytes")

    # Final recommendations
    if missing_methods:
        print(f"\n{'=' * 70}")
        print("⚠️  RECOMMENDATIONS:")
        print(f"{'=' * 70}")

        if 'handle_cookie_banner' in missing_methods:
            print("\n1. Add the handle_cookie_banner method:")
            print("   This method handles cookie consent banners for all marketplaces")
            print("   - Italy: button[@aria-label='Rifiuta']")
            print("   - ES/NL/FR: button[@id='sp-cc-rejectall-link']")

        if any('save_country' in m for m in missing_methods):
            print("\n2. Add country-specific saving methods:")
            print("   These methods save results in separate folders for each country")
            print("   - save_country_results()")
            print("   - save_country_detailed_results()")
            print("   - save_country_brand_summary()")
            print("   - save_country_brand_analysis()")

        if 'save_overall_summary' in missing_methods:
            print("\n3. Add the save_overall_summary method:")
            print("   This creates cross-country comparison files")

except ImportError as e:
    print(f"✗ Failed to import EnergyLabelScraper: {e}")
    sys.exit(1)
except Exception as e:
    print(f"✗ Unexpected error: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)