#!/usr/bin/env python3
"""
Multi-Country Test Script for Energy Label Scraper
Tests the scraper on multiple Amazon marketplaces with location settings

Test URLs provided:
- France: Refrigerators (réfrigérateur) - Postcode: 75017
- Sweden: Refrigerators (kylskåp) - Postcode: 112 19
- Netherlands: Light Sources (lichtbronnen) - Automatic location
- Italy: Refrigerators (frigo) - Postcode: 00195
- Spain: Refrigerators (refrigerador) - Postcode: 28055

Usage:
    python test_energy_multi_country.py              # Test all countries
    python test_energy_multi_country.py --country italy    # Test specific country
    python test_energy_multi_country.py --max-products 10  # Test more products
"""

import asyncio
import logging
import os
import json
from datetime import datetime
from typing import List, Dict, Optional

# Import required components
from energy_label_scraper import EnergyLabelScraper, ProductInfo, DATA_DIR, COUNTRY_CONFIGS
from camoufox.async_api import AsyncCamoufox
from playwright.async_api import Page
from proxy_manager import ProxyManager, ProxyStats
from captcha_solver import CaptchaSolver

# Configure logging for test
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('test_energy_multi_country.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Test configurations with URLs for each country
TEST_CONFIGS = {
    # "france": {
    #     "url": "https://www.amazon.fr/s?k=r%C3%A9frig%C3%A9rateur&crid=102GQX4W8QOAN&sprefix=r%C3%A9frig%C3%A9rateur%2Caps%2C102&ref=nb_sb_ss_ts-doa-p_1_13&language=en_GB",
    #     "category": "Refrigerators",
    #     "expected_postcode": "75017"
    # },
    # "sweden": {
    #     "url": "https://www.amazon.se/s?k=kylsk%C3%A5p&crid=2PYILCIQ09JIY&sprefix=kylsk%C3%A5p%2Caps%2C88&ref=nb_sb_noss_1&language=en_GB",
    #     "category": "Refrigerators",
    #     "expected_postcode": "112 19"
    # },
    # "netherlands": {
    #     "url": "https://www.amazon.nl/s?k=lichtbronnen&ref=nav_bb_sb&language=en_GB",
    #     "category": "Light Sources",
    #     "expected_postcode": None  # Automatic location
    # },
    # "italy": {
    #     "url": "https://www.amazon.it/s?k=frigo&crid=2323QILJ875F6&sprefix=frigo%2Caps%2C102&ref=nb_sb_noss_1&language=en_GB",
    #     "category": "Refrigerators",
    #     "expected_postcode": "00195"
    # },
    "spain": {
        "url": "https://www.amazon.es/s?k=refrigerador&__mk_es_ES=%C3%85M%C3%85%C5%BD%C3%95%C3%91&crid=2V1P8PHQX1LFV&sprefix=refrigerador%2Caps%2C99&ref=nb_sb_noss_1&language=en_GB",
        "category": "Refrigerators",
        "expected_postcode": "28055"
    }
}


async def test_country_with_url(scraper: EnergyLabelScraper, country_key: str, test_config: Dict,
                                max_products: int = 5) -> List[ProductInfo]:
    """
    Test the scraper on a specific country with a given URL

    Args:
        scraper: EnergyLabelScraper instance
        country_key: Country key (e.g., 'france', 'italy')
        test_config: Test configuration with URL and category
        max_products: Maximum number of products to process

    Returns:
        List of ProductInfo objects
    """
    # Get country configuration
    country_config = COUNTRY_CONFIGS.get(country_key)
    if not country_config:
        logger.error(f"Country {country_key} not found in COUNTRY_CONFIGS")
        return []

    domain = country_config["domain"]
    locale = country_config["locale"]
    use_postcode = country_config.get("use_postcode", False)
    postcode = country_config.get("postcode", "")
    test_url = test_config["url"]
    category = test_config["category"]

    logger.info(f"\n{'=' * 60}")
    logger.info(f"Testing {country_key.upper()} - {domain}")
    logger.info(f"Category: {category}")
    logger.info(f"URL: {test_url}")
    if use_postcode:
        logger.info(f"Will set location to postcode: {postcode}")
    else:
        logger.info(f"Will use automatic location")
    logger.info(f"{'=' * 60}")

    products = []
    initial_product_count = 0
    product_index = 0
    products_with_formal_label = 0
    products_with_energy_text = 0
    products_without_any_info = 0

    try:
        # Get proxy if available
        proxy = None
        if scraper.proxy_manager:
            proxy = await scraper.proxy_manager.get_next_proxy()
            if proxy:
                logger.info(f"Using proxy: {proxy}")

        # Setup browser
        camoufox = await scraper.setup_camoufox(domain, locale, proxy)

        async with camoufox as browser:
            page = await browser.new_page()

            # Navigate to homepage first with English language
            homepage_url = f"https://www.{domain}?language=en_GB"
            logger.info(f"Navigating to homepage: {homepage_url}")
            await page.goto(homepage_url, wait_until="networkidle")

            # Handle intermediate page if present
            if await scraper.handle_intermediate_page(page, domain):
                logger.info("Handled intermediate page")

            # Handle cookie banner
            if await scraper.handle_cookie_banner(page):
                logger.info("Handled cookie banner")

            await scraper.random_delay()

            # Set location if postcode is configured
            if use_postcode and postcode:
                logger.info(f"Setting location to postcode: {postcode}")
                location_set = await scraper.set_location_by_postcode(page, postcode)
                if location_set:
                    logger.info(f"✓ Successfully set location to {postcode}")

                    # Verify location was set correctly
                    await scraper.random_delay(1.0, 2.0)
                    location_text = ""
                    location_elements = [
                        "xpath=//div[@id='glow-ingress-block']",
                        "xpath=//span[@id='glow-ingress-line2']"
                    ]

                    for selector in location_elements:
                        element = await page.query_selector(selector)
                        if element:
                            text = await element.text_content()
                            if text:
                                location_text += text.strip() + " "

                    location_text = location_text.strip()
                    logger.info(f"Current location shows: {location_text}")

                    # Check if location seems correct
                    if country_key == "spain" and "Spain" not in location_text and "España" not in location_text:
                        logger.warning(f"Location might not be set correctly. Shows: {location_text}")
                    elif country_key == "france" and "France" not in location_text:
                        logger.warning(f"Location might not be set correctly. Shows: {location_text}")
                    elif country_key == "italy" and "Italy" not in location_text and "Italia" not in location_text:
                        logger.warning(f"Location might not be set correctly. Shows: {location_text}")
                    elif country_key == "sweden" and "Sweden" not in location_text and "Sverige" not in location_text:
                        logger.warning(f"Location might not be set correctly. Shows: {location_text}")
                else:
                    logger.warning(f"✗ Could not set location to {postcode}")
                await scraper.random_delay(1.0, 2.0)

            # Navigate to test URL
            logger.info(f"Navigating to test URL...")
            await page.goto(test_url, wait_until="domcontentloaded")

            # Handle intermediate page again if it appears
            if await scraper.handle_intermediate_page(page, domain):
                logger.info("Handled intermediate page after navigation")

            # Wait for search results
            try:
                await page.wait_for_selector('xpath=//span[@data-component-type="s-search-results"]', timeout=15000)
                logger.info("Search results loaded")
            except:
                logger.error("Failed to load search results")
                # Take screenshot for debugging
                screenshot_path = os.path.join("screenshots_energy",
                                               f"error_{country_key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                await page.screenshot(path=screenshot_path)
                return []

            # Find all products on the page
            product_selector = "xpath=//div[contains(@class, 's-main-slot')]//div[@data-component-type='s-search-result']"
            product_elements = await page.query_selector_all(product_selector)

            logger.info(f"Found {len(product_elements)} products on the page")

            # Statistics
            products_with_formal_label = 0
            products_with_energy_text = 0
            products_without_any_info = 0

            # Process each product (limited by max_products)
            for i, product_element in enumerate(product_elements[:max_products]):
                try:
                    # Extract ASIN
                    asin = await product_element.get_attribute("data-asin")
                    if not asin:
                        logger.warning(f"Product {i + 1}: No ASIN found, skipping")
                        continue

                    # Check for energy label in search results
                    has_formal_label, has_energy_text = await scraper.check_for_energy_label(product_element)

                    # Update statistics
                    if has_formal_label:
                        products_with_formal_label += 1
                        logger.info(f"Product {i + 1} (ASIN: {asin}) - SKIPPING: Has formal energy label")
                        continue
                    elif has_energy_text:
                        products_with_energy_text += 1
                    else:
                        products_without_any_info += 1

                    logger.info(f"Product {i + 1} (ASIN: {asin}) - Processing (has energy text: {has_energy_text})")

                    # Find product link
                    link_element = await product_element.query_selector('h2 a')
                    if not link_element:
                        link_element = await product_element.query_selector('a.a-link-normal')

                    if not link_element:
                        logger.warning(f"No product link found for ASIN {asin}")
                        continue

                    href = await link_element.get_attribute("href")
                    if not href:
                        logger.warning(f"No href found for ASIN {asin}")
                        continue

                    # Construct full URL
                    if not href.startswith("http"):
                        product_url = f"https://www.{domain}{href}"
                    else:
                        product_url = href

                    # Navigate to product page
                    logger.info(f"Navigating to product page...")
                    await page.goto(product_url, wait_until="domcontentloaded")

                    # Wait for product title
                    try:
                        await page.wait_for_selector("xpath=//span[@id='productTitle']", timeout=10000)
                    except:
                        logger.warning(f"Product page didn't load properly for ASIN {asin}")
                        await page.go_back(wait_until="domcontentloaded")
                        continue

                    await scraper.random_delay()

                    # Extract product information
                    product_info = await scraper.extract_product_info(
                        page, asin, has_energy_text, category, domain
                    )

                    if product_info:
                        products.append(product_info)
                        logger.info(f"✓ Extracted: {product_info.brand} - {product_info.product_name[:50]}...")
                    else:
                        logger.warning(f"✗ Failed to extract product info for ASIN {asin}")

                    # Navigate back to search results
                    await page.go_back(wait_until="domcontentloaded")

                    # Check if we landed on an intermediate page
                    if await scraper.handle_intermediate_page(page, domain):
                        logger.warning("Intermediate page appeared when going back")

                    await scraper.random_delay(1.0, 2.0)

                except Exception as e:
                    logger.error(f"Error processing product {i + 1}: {str(e)}")
                    # Try to return to search results
                    try:
                        await page.go_back(wait_until="domcontentloaded")
                    except:
                        pass

    except Exception as e:
        logger.error(f"Error during test for {country_key}: {str(e)}")
        import traceback
        traceback.print_exc()

    finally:
        # Print test summary for this country
        print(f"\n{'=' * 60}")
        print(f"TEST SUMMARY - {country_key.upper()}")
        print(f"{'=' * 60}")
        print(f"Total products found on page: {initial_product_count}")
        print(f"Products checked: {initial_product_count}")  # We check all products in first pass
        print(f"Products with formal energy label (skipped): {products_with_formal_label}")
        print(f"Products without formal label (found): {product_index}")
        print(f"Products without formal label (processed): {len(products)}")
        print(f"  - With energy text only: {sum(1 for p in products if p.has_energy_text)}")
        print(f"  - Without any energy info: {sum(1 for p in products if not p.has_energy_text)}")
        print(f"Location: Expected {test_config['expected_postcode'] or 'Automatic'}")
        print(f"{'=' * 60}")

    return products


def save_test_results_by_country(country_key: str, products: List[ProductInfo]):
    """Save test results for a specific country"""
    if not products:
        logger.warning(f"No products to save for {country_key}")
        return

    # Create test directory
    test_dir = os.path.join(DATA_DIR, f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(test_dir, exist_ok=True)

    # Save as JSON for easy inspection
    json_file = os.path.join(test_dir, f"{country_key}_test_results.json")
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump([p.to_dict() for p in products], f, indent=2, ensure_ascii=False)
    logger.info(f"Saved {country_key} test results to {json_file}")

    # Try to save as Excel too
    try:
        import pandas as pd
        df = pd.DataFrame([p.to_dict() for p in products])

        # Add energy status column
        df['energy_status'] = df['has_energy_text'].apply(
            lambda x: 'Energy text only' if x else 'No energy info'
        )

        excel_file = os.path.join(test_dir, f"{country_key}_test_results.xlsx")
        df.to_excel(excel_file, index=False)
        logger.info(f"Saved {country_key} test results to {excel_file}")

    except ImportError:
        logger.warning("pandas not installed, skipping Excel export")


async def run_multi_country_test(countries_to_test: Optional[List[str]] = None, max_products_per_country: int = 5):
    """
    Run tests on multiple countries

    Args:
        countries_to_test: List of country keys to test (None = all)
        max_products_per_country: Maximum products to test per country
    """
    print("\nMulti-Country Energy Label Scraper Test")
    print("=" * 60)
    print("This test will:")
    print("1. Test location setting for each country")
    print("2. Navigate to specific product search pages")
    print("3. Process products without formal energy labels")
    print("4. Save results for analysis")
    print()

    # Set up proxy manager if proxies.txt exists
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

    # Initialize scraper
    scraper = EnergyLabelScraper(
        proxy_manager=proxy_manager,
        captcha_solver=captcha_solver,
        headless=False  # Show browser for testing
    )

    # Determine which countries to test
    if countries_to_test is None:
        countries_to_test = list(TEST_CONFIGS.keys())

    all_results = {}

    # Test each country
    for country_key in countries_to_test:
        if country_key not in TEST_CONFIGS:
            logger.warning(f"No test configuration for {country_key}, skipping")
            continue

        test_config = TEST_CONFIGS[country_key]

        try:
            # Test the country
            products = await test_country_with_url(
                scraper=scraper,
                country_key=country_key,
                test_config=test_config,
                max_products=max_products_per_country
            )

            # Save results
            all_results[country_key] = products
            save_test_results_by_country(country_key, products)

            # Add delay between countries
            await asyncio.sleep(5.0)

        except Exception as e:
            logger.error(f"Failed to test {country_key}: {str(e)}")

    # Print overall summary
    print("\n" + "=" * 60)
    print("OVERALL TEST SUMMARY")
    print("=" * 60)

    total_products = 0
    total_with_text = 0
    total_without_info = 0

    for country_key, products in all_results.items():
        products_with_text = sum(1 for p in products if p.has_energy_text)
        products_without_info = len(products) - products_with_text

        total_products += len(products)
        total_with_text += products_with_text
        total_without_info += products_without_info

        print(f"\n{country_key.upper()}:")
        print(f"  Total products processed: {len(products)}")
        print(f"  With energy text only: {products_with_text}")
        print(f"  Without any energy info: {products_without_info}")

        if products:
            brands = set(p.brand for p in products)
            print(f"  Unique brands: {len(brands)}")
            print(f"  Brands: {', '.join(sorted(brands)[:5])}{'...' if len(brands) > 5 else ''}")

    print(f"\nGRAND TOTAL:")
    print(f"  Countries tested: {len(all_results)}")
    print(f"  Total products: {total_products}")
    print(f"  With energy text: {total_with_text}")
    print(f"  Without any info: {total_without_info}")
    print("=" * 60)


async def main():
    """Run the multi-country test"""
    import argparse

    parser = argparse.ArgumentParser(description='Test Energy Label Scraper on multiple countries')
    parser.add_argument('--country', type=str, help='Specific country to test (e.g., italy, france)')
    parser.add_argument('--max-products', type=int, default=5,
                        help='Maximum products to test per country (default: 5)')
    parser.add_argument('--all', action='store_true',
                        help='Test all countries (default if no country specified)')

    args = parser.parse_args()

    # Determine which countries to test
    if args.country:
        countries_to_test = [args.country.lower()]
        print(f"\nTesting specific country: {args.country}")
    else:
        countries_to_test = None  # Test all countries
        print("\nTesting all countries")

    print(f"Maximum products per country: {args.max_products}")

    try:
        await run_multi_country_test(
            countries_to_test=countries_to_test,
            max_products_per_country=args.max_products
        )
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    except Exception as e:
        logger.error(f"Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())