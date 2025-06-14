#!/usr/bin/env python3
"""
Test script for Energy Label Data Extractor - Module 2

This test:
1. Creates a mock link file with the provided product URL
2. Tests data extraction for that specific product
3. Shows the extracted information
4. Saves results to a test directory
"""

import asyncio
import logging
import os
import json
from datetime import datetime
from typing import Optional

# Import the data extractor module
from energy_label_data_extractor import (
    EnergyLabelDataExtractor,
    ProductInfo,
    COUNTRY_CONFIGS,
    LINKS_DIR
)
from proxy_manager import ProxyManager
from captcha_solver import CaptchaSolver

# Configure logging for test
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('test_data_extractor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Test configuration
TEST_PRODUCT_URL = "https://www.amazon.es/-/en/Edesa-EFT-1411WH-Refrigerator-Doors-Height/dp/B0D2DW6TZS/ref=sr_1_22?__mk_es_ES=%C3%85M%C3%85%C5%BD%C3%95%C3%91&crid=2V1P8PHQX1LFV&dib=eyJ2IjoiMSJ9.4XZ-8irZ_0_wE9UqJUNJfQ2vGrWNN1tpu0KDOCYActn1tFPHD-RKCV3LQhu7Sd6eAJwbhPVejOxEfqXH2DZqhnrdlZbJB_MxKmHx3Y91vWop3ICB7fj5CgGuH3ITLUQvuABYAkKO7duflbGA_IakYBlij2n9d93hZvOcQdglSLke3EP53lubn6p6hyLydIB1YKdbuGjQne-K3uhzgumMM19yanEAslRD5QyQCdvZC1wGysmbSZjZvV0xDb0rCZJhIHYKgbNpHEO4fBeVN1hDjP-77eKBgpi3f8SzIST2PT8.5w-WRB2Xnkp5FDa49nim_yBztzy1HkRkAY5x4JtaX50&dib_tag=se&keywords=refrigerador&qid=1749895572&sprefix=refrigerador%2Caps%2C99&sr=8-22"
TEST_COUNTRY = "spain"
TEST_ASIN = "B0D2DW6TZS"  # Extracted from URL

# Test output directory
TEST_DIR = "test_results"
os.makedirs(TEST_DIR, exist_ok=True)


def create_test_link_file():
    """Create a mock link file for testing"""
    # Ensure links directory exists
    os.makedirs(LINKS_DIR, exist_ok=True)

    # Create test link data
    test_links = {
        "country": TEST_COUNTRY,
        "collection_timestamp": datetime.now().isoformat(),
        "total_links": 1,
        "links": [
            {
                "asin": TEST_ASIN,
                "url": TEST_PRODUCT_URL,
                "has_energy_text": False,  # We'll find out during extraction
                "category": "Refrigerators",
                "category_key": "fridges_freezers",
                "country": TEST_COUNTRY,
                "domain": "amazon.es",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        ]
    }

    # Save to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(LINKS_DIR, f"{TEST_COUNTRY}_product_links_{timestamp}.json")

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(test_links, f, indent=2, ensure_ascii=False)

    logger.info(f"Created test link file: {filename}")
    return filename


class TestDataExtractor(EnergyLabelDataExtractor):
    """Extended extractor for testing with specific product"""

    async def test_single_product(self, product_url: str, asin: str,
                                  country_key: str) -> Optional[ProductInfo]:
        """Test extraction of a single product"""

        country_config = COUNTRY_CONFIGS.get(country_key, {})
        if not country_config:
            logger.error(f"No configuration found for {country_key}")
            return None

        domain = country_config["domain"]
        locale = country_config["locale"]

        logger.info(f"Testing data extraction for single product")
        logger.info(f"ASIN: {asin}")
        logger.info(f"URL: {product_url}")
        logger.info(f"Country: {country_key}")

        product_info = None

        try:
            # Get proxy if available
            proxy = None
            if self.proxy_manager:
                proxy = await self.proxy_manager.get_next_proxy()
                if proxy:
                    logger.info(f"Using proxy: {proxy}")

            # Setup browser
            camoufox = await self.setup_camoufox(domain, locale, proxy)

            async with camoufox as browser:
                page = await browser.new_page()

                # Navigate to product page
                logger.info("Navigating to product page...")
                await page.goto(product_url, wait_until="domcontentloaded", timeout=30000)

                # Handle intermediate page if it appears
                if hasattr(self, 'handle_intermediate_page'):
                    # Check if extractor has intermediate page handler
                    domain_parts = product_url.split('/')
                    if len(domain_parts) > 2:
                        domain = domain_parts[2].replace('www.', '')
                        if await self.handle_intermediate_page(page, domain):
                            logger.info("Handled intermediate page, navigating to product again")
                            await page.goto(product_url, wait_until="domcontentloaded", timeout=30000)

                # Wait for product title
                try:
                    await page.wait_for_selector("xpath=//span[@id='productTitle']", timeout=10000)
                    logger.info("Product page loaded successfully")
                except:
                    logger.error("Failed to load product page")
                    # Take screenshot
                    screenshot_path = os.path.join(TEST_DIR,
                                                   f"error_{asin}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                    await page.screenshot(path=screenshot_path)
                    logger.info(f"Screenshot saved to: {screenshot_path}")
                    return None

                await self.random_delay()

                # Create link data for extraction
                link_data = {
                    'asin': asin,
                    'url': product_url,
                    'has_energy_text': False,  # Will be determined
                    'category': 'Refrigerators',
                    'domain': domain
                }

                # Extract product information
                product_info = await self.extract_product_info(page, link_data)

                if product_info:
                    logger.info("✓ Successfully extracted product information")

                    # Print extracted information
                    print(f"\nExtracted Product Information:")
                    print(f"{'=' * 60}")
                    print(f"ASIN: {product_info.asin}")
                    print(f"Product Name: {product_info.product_name}")
                    print(f"Brand: {product_info.brand}")
                    print(f"Seller: {product_info.seller_name}")
                    print(f"Seller URL: {product_info.seller_url}")
                    print(f"Category: {product_info.category}")
                    print(f"Has Energy Text: {product_info.has_energy_text}")
                    print(f"Amazon Host: {product_info.amazon_host}")
                    print(f"{'=' * 60}")

                    # Take screenshot of the product page
                    screenshot_path = os.path.join(TEST_DIR,
                                                   f"product_{asin}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                    await page.screenshot(path=screenshot_path, full_page=True)
                    logger.info(f"Product page screenshot saved to: {screenshot_path}")

                else:
                    logger.error("✗ Failed to extract product information")

        except Exception as e:
            logger.error(f"Error during test: {str(e)}")
            import traceback
            traceback.print_exc()

        return product_info

    def save_test_results(self, product_info: Optional[ProductInfo]):
        """Save test results"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if product_info:
            # Save successful extraction
            filename = os.path.join(TEST_DIR, f"test_extraction_success_{timestamp}.json")
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump({
                    "test_info": {
                        "test_url": TEST_PRODUCT_URL,
                        "test_asin": TEST_ASIN,
                        "country": TEST_COUNTRY,
                        "test_timestamp": datetime.now().isoformat()
                    },
                    "extracted_data": product_info.to_dict()
                }, f, indent=2, ensure_ascii=False)

            print(f"\nTest results saved to: {filename}")

            # Try to save as Excel too
            try:
                import pandas as pd
                df = pd.DataFrame([product_info.to_dict()])
                excel_file = os.path.join(TEST_DIR, f"test_extraction_success_{timestamp}.xlsx")
                df.to_excel(excel_file, index=False)
                print(f"Excel file saved to: {excel_file}")
            except ImportError:
                logger.warning("pandas not installed, skipping Excel export")

        else:
            # Save failure info
            filename = os.path.join(TEST_DIR, f"test_extraction_failed_{timestamp}.json")
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump({
                    "test_info": {
                        "test_url": TEST_PRODUCT_URL,
                        "test_asin": TEST_ASIN,
                        "country": TEST_COUNTRY,
                        "test_timestamp": datetime.now().isoformat()
                    },
                    "result": "extraction_failed"
                }, f, indent=2)

            print(f"\nTest failure info saved to: {filename}")


async def test_full_workflow():
    """Test the full extraction workflow with link file"""
    print("\nTest 1: Full Workflow (with link file)")
    print("=" * 60)

    # Create test link file
    link_file = create_test_link_file()
    print(f"Created test link file: {link_file}")

    # Initialize extractor
    extractor = EnergyLabelDataExtractor(
        headless=False,
        batch_size=1  # Single product
    )

    try:
        # Process the country (which will read our test link file)
        await extractor.process_country(TEST_COUNTRY)

        # Print results
        if extractor.products_data:
            print(f"\n✓ Full workflow test completed successfully!")
            print(f"  Extracted {len(extractor.products_data)} products")

            # Show extracted data
            for product in extractor.products_data:
                print(f"\nExtracted Product:")
                print(f"  Brand: {product.brand}")
                print(f"  Product: {product.product_name[:60]}...")
                print(f"  Seller: {product.seller_name}")
        else:
            print(f"\n✗ Full workflow test completed but no data extracted")

    except Exception as e:
        logger.error(f"Full workflow test failed: {str(e)}")
        import traceback
        traceback.print_exc()


async def test_single_product():
    """Test extraction of a single product directly"""
    print("\nTest 2: Single Product Extraction (direct)")
    print("=" * 60)

    # Set up proxy manager if available
    proxy_manager = None
    if os.path.exists("proxies.txt"):
        proxy_manager = ProxyManager("proxies.txt")
        await proxy_manager.load_proxies()
        logger.info(f"Loaded {len(proxy_manager.proxies)} proxies")

    # Set up CAPTCHA solver
    captcha_solver = None
    captcha_api_key = os.getenv("CAPTCHA_API_KEY",
                                "CAP-956BF088AFEBDE1D55D75C975171507466CFFDF3C9657C7412145974FF602B9A")
    if captcha_api_key:
        captcha_solver = CaptchaSolver(captcha_api_key)
        logger.info("CAPTCHA solver initialized")

    # Initialize test extractor
    extractor = TestDataExtractor(
        proxy_manager=proxy_manager,
        captcha_solver=captcha_solver,
        headless=False  # Show browser for testing
    )

    try:
        # Test single product extraction
        product_info = await extractor.test_single_product(
            product_url=TEST_PRODUCT_URL,
            asin=TEST_ASIN,
            country_key=TEST_COUNTRY
        )

        # Save results
        extractor.save_test_results(product_info)

        if product_info:
            print(f"\n✓ Single product test completed successfully!")
        else:
            print(f"\n✗ Single product test failed to extract data")

    except Exception as e:
        logger.error(f"Single product test failed: {str(e)}")
        import traceback
        traceback.print_exc()


async def run_all_tests():
    """Run all tests"""
    print("Energy Label Data Extractor - Test Script")
    print("=" * 60)
    print(f"Test Product URL: {TEST_PRODUCT_URL}")
    print(f"Test ASIN: {TEST_ASIN}")
    print(f"Country: {TEST_COUNTRY}")
    print()

    # Run tests
    print("Running tests...")

    # Test 1: Full workflow with link file
    await test_full_workflow()

    print("\n" + "-" * 60 + "\n")

    # Test 2: Direct single product extraction
    await test_single_product()

    print("\n" + "=" * 60)
    print("All tests completed!")
    print(f"Check {TEST_DIR}/ for results and screenshots")


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Test Energy Label Data Extractor')
    parser.add_argument('--test', choices=['full', 'single', 'all'],
                        default='all',
                        help='Which test to run (default: all)')
    args = parser.parse_args()

    if args.test == 'full':
        await test_full_workflow()
    elif args.test == 'single':
        await test_single_product()
    else:
        await run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())