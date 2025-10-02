#!/usr/bin/env python3
"""
Test Runner for Energy Label Scraper Modules

This script provides an easy way to run tests for both modules.
"""

import subprocess
import sys
import os
import time
from datetime import datetime


def print_header(text):
    """Print a formatted header"""
    print()
    print("=" * 60)
    print(f" {text}")
    print("=" * 60)
    print()


def run_command(command, description):
    """Run a command and show output"""
    print(f"Running: {description}")
    print(f"Command: {command}")
    print("-" * 60)

    start_time = time.time()

    try:
        # Run the command
        result = subprocess.run(
            command,
            shell=True,
            capture_output=False,  # Show output in real-time
            text=True
        )

        elapsed_time = time.time() - start_time

        if result.returncode == 0:
            print(f"\n✓ {description} completed successfully!")
        else:
            print(f"\n✗ {description} failed with exit code {result.returncode}")

        print(f"Time elapsed: {elapsed_time:.2f} seconds")

        return result.returncode == 0

    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        return False
    except Exception as e:
        print(f"\nError running command: {str(e)}")
        return False


def main():
    """Main test runner"""
    print_header("Energy Label Scraper - Test Runner")

    # Create test results directory
    os.makedirs("test_results", exist_ok=True)

    # Get Python executable
    python_cmd = sys.executable

    # Test options
    print("Select test to run:")
    print("1. Test Link Collector (Module 1)")
    print("2. Test Data Extractor (Module 2)")
    print("3. Run both tests")
    print("4. Quick test (Module 1 with 5 products + Module 2 single product)")
    print()

    choice = input("Enter your choice (1-4): ").strip()

    if choice == "1":
        # Test Module 1
        print_header("Testing Module 1: Link Collector")
        run_command(
            f"{python_cmd} test_link_collector.py",
            "Link Collector Test"
        )

    elif choice == "2":
        # Test Module 2
        print_header("Testing Module 2: Data Extractor")
        run_command(
            f"{python_cmd} test_data_extractor.py",
            "Data Extractor Test"
        )

    elif choice == "3":
        # Run both tests
        print_header("Running Complete Test Suite")

        # First test link collector
        success1 = run_command(
            f"{python_cmd} test_link_collector.py",
            "Link Collector Test"
        )

        if success1:
            print("\nWaiting 5 seconds before next test...")
            time.sleep(5)

            # Then test data extractor
            run_command(
                f"{python_cmd} test_data_extractor.py",
                "Data Extractor Test"
            )
        else:
            print("\nSkipping Data Extractor test due to Link Collector failure")

    elif choice == "4":
        # Quick test
        print_header("Running Quick Test")

        # Create a temporary test script for quick testing
        quick_test_script = """
import asyncio
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def quick_test():
    # Test link collector with just 5 products
    print("\\n1. Testing Link Collector with 5 products...")
    from test_link_collector import TestLinkCollector, TEST_URL, TEST_COUNTRY, TEST_CATEGORY

    collector = TestLinkCollector(headless=False)
    links = await collector.test_specific_url(
        test_url=TEST_URL,
        country_key=TEST_COUNTRY,
        category_name=TEST_CATEGORY,
        max_products=5
    )

    if links:
        collector.save_test_results(links)
        print(f"✓ Collected {len(links)} links")
    else:
        print("✗ No links collected")
        return

    # Wait a bit
    await asyncio.sleep(3)

    # Test data extractor with single product
    print("\\n2. Testing Data Extractor with single product...")
    from test_data_extractor import TestDataExtractor, TEST_PRODUCT_URL, TEST_ASIN, TEST_COUNTRY

    extractor = TestDataExtractor(headless=False)
    product_info = await extractor.test_single_product(
        product_url=TEST_PRODUCT_URL,
        asin=TEST_ASIN,
        country_key=TEST_COUNTRY
    )

    if product_info:
        extractor.save_test_results(product_info)
        print("✓ Extracted product data")
    else:
        print("✗ Failed to extract data")

asyncio.run(quick_test())
"""

        # Save and run quick test script
        with open("quick_test_temp.py", "w") as f:
            f.write(quick_test_script)

        try:
            run_command(
                f"{python_cmd} quick_test_temp.py",
                "Quick Test"
            )
        finally:
            # Clean up
            if os.path.exists("quick_test_temp.py"):
                os.remove("quick_test_temp.py")

    else:
        print("Invalid choice. Please run the script again.")
        return

    # Show results location
    print()
    print_header("Test Complete")
    print("Test results saved in:")
    print(f"  • test_results/")
    print(f"  • energy_label_data/product_links/ (for collected links)")
    print(f"  • energy_label_data/extracted_data/ (for extracted data)")
    print()
    print("Check the following log files for details:")
    print(f"  • test_link_collector.log")
    print(f"  • test_data_extractor.log")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest runner interrupted by user")
    except Exception as e:
        print(f"\nError: {str(e)}")
        import traceback

        traceback.print_exc()