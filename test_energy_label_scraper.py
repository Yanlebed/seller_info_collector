#!/usr/bin/env python3
"""
Updated Test Script for Energy Label Scraper with Location Settings
Tests the scraper on a single Amazon URL with postcode functionality
"""

import asyncio
import logging
import os
import json
from datetime import datetime
from typing import List, Dict

# Import required components
from energy_label_scraper import EnergyLabelScraper, ProductInfo, DATA_DIR, COUNTRY_CONFIGS
from camoufox.async_api import AsyncCamoufox
from playwright.async_api import Page
from proxy_manager import ProxyManager
from captcha_solver import CaptchaSolver

# Configure logging for test
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('test_energy_scraper_single.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def test_single_url_with_location(scraper: EnergyLabelScraper, test_url: str,
                                        country_key: str = "italy",
                                        category: str = "Domestic Ovens",
                                        max_products: int = 10) -> List[ProductInfo]:
    """
    Test the scraper on a single URL with location settings

    Args:
        scraper: EnergyLabelScraper instance
        test_url: The URL to test
        country_key: Country key from COUNTRY_CONFIGS
        category: Category name for logging
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

    logger.info(f"Starting test scrape of {test_url}")
    logger.info(f"Country: {country_key} ({domain})")
    logger.info(f"Category: {category}")
    if use_postcode:
        logger.info(f"Will set location to postcode: {postcode}")
    else:
        logger.info(f"Will use automatic location")
    logger.info(f"Will process up to {max_products} products")

    products = []

    try:
        # Get proxy if available
        proxy = None
        if scraper.proxy_manager:
            proxy = await scraper.proxy_manager.get_next_proxy()
            if proxy:
                logger.info(f"Using proxy: {proxy}")
            else:
                logger.info("No proxy available, proceeding without proxy")

        # Setup browser
        camoufox = await scraper.setup_camoufox(domain, locale, proxy)

        async with camoufox as browser:
            page = await browser.new_page()

            # Navigate to homepage first with English language
            homepage_url = f"https://www.{domain}?language=en_GB"
            logger.info(f"Navigating to homepage: {homepage_url}")
            await page.goto(homepage_url, wait_until="networkidle")

            # Handle intermediate page if present
            intermediate_handled = await scraper.handle_intermediate_page(page, domain)
            if intermediate_handled:
                logger.info("Handled intermediate page")

            # Handle cookie banner
            await scraper.handle_cookie_banner(page)
            await scraper.random_delay()

            # Set location if postcode is configured
            if use_postcode and postcode:
                logger.info(f"Setting location to postcode: {postcode}")
                location_set = await scraper.set_location_by_postcode(page, postcode)
                if location_set:
                    logger.info(f"✓ Successfully set location to {postcode}")

                    # Verify location was set
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
                                location_text += text + " "

                    location_text = location_text.strip()
                    logger.info(f"Current location shows: {location_text}")
                else:
                    logger.warning(f"✗ Could not set location to {postcode}")

                await scraper.random_delay(1.0, 2.0)

            # Navigate to test URL
            logger.info(f"Navigating to test URL: {test_url}")
            await page.goto(test_url, wait_until="domcontentloaded")

            # Handle intermediate page again if it appears
            if await scraper.handle_intermediate_page(page, domain):
                logger.info("Handled intermediate page after navigation")

            # Wait for search results
            await page.wait_for_selector('xpath=//span[@data-component-type="s-search-results"]', timeout=15000)
            logger.info("Search results loaded")

            # Find all products on the page
            product_selector = "xpath=//div[contains(@class, 's-main-slot')]//div[@data-component-type='s-search-result']"
            product_elements = await page.query_selector_all(product_selector)

            logger.info(f"Found {len(product_elements)} products on the page")

            # Statistics
            products_with_formal_label = 0
            products_with_energy_text = 0
            products_without_any_info = 0

            # Process each product
            for i, product_element in enumerate(product_elements[:max_products]):
                try:
                    # Extract ASIN
                    asin = await product_element.get_attribute("data-asin")
                    if not asin:
                        logger.warning(f"Product {i+1}: No ASIN found, skipping")
                        continue

                    # Check for energy label in search results
                    has_formal_label, has_energy_text = await scraper.check_for_energy_label(product_element)

                    # Update statistics
                    if has_formal_label:
                        products_with_formal_label += 1
                        logger.info(f"Product {i+1} (ASIN: {asin}) - SKIPPING: Has formal energy label")
                        continue
                    elif has_energy_text:
                        products_with_energy_text += 1
                    else:
                        products_without_any_info += 1

                    logger.info(f"Product {i+1} (ASIN: {asin}) - Processing (has energy text: {has_energy_text})")

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
                    await page.wait_for_selector("xpath=//span[@id='productTitle']", timeout=10000)
                    await scraper.random_delay()

                    # Extract product information
                    product_info = await scraper.extract_product_info(
                        page, asin, has_energy_text, category, domain
                    )

                    if product_info:
                        products.append(product_info)
                        scraper.processed_products.add(asin)

                        # Track brands
                        if domain not in scraper.brands_found:
                            scraper.brands_found[domain] = set()
                        scraper.brands_found[domain].add(product_info.brand)

                        logger.info(f"Successfully extracted product info:")
                        logger.info(f"  - Brand: {product_info.brand}")
                        logger.info(f"  - Product: {product_info.product_name[:80]}...")
                        logger.info(f"  - Seller: {product_info.seller_name}")
                        logger.info(f"  - Has energy text: {product_info.has_energy_text}")
                    else:
                        logger.warning(f"Failed to extract product info for ASIN {asin}")

                    # Navigate back to search results
                    await page.go_back(wait_until="domcontentloaded")

                    # Check if we landed on an intermediate page
                    if await scraper.handle_intermediate_page(page, domain):
                        logger.warning("Intermediate page appeared when going back")

                    await scraper.random_delay(1.0, 2.0)

                except Exception as e:
                    logger.error(f"Error processing product {i+1}: {str(e)}")
                    # Try to return to search results
                    try:
                        await page.go_back(wait_until="domcontentloaded")
                        await scraper.handle_intermediate_page(page, domain)
                    except:
                        pass

            # Print test summary
            print(f"\n{'='*60}")
            print("TEST SUMMARY")
            print(f"{'='*60}")
            print(f"Country: {country_key} ({domain})")
            print(f"Postcode: {postcode if use_postcode else 'Automatic'}")
            print(f"Total products found on page: {len(product_elements)}")
            print(f"Products analyzed: {min(max_products, len(product_elements))}")
            print(f"Products with formal label (skipped): {products_with_formal_label}")
            print(f"Products without formal label: {len(products)}")
            print(f"  - With energy text only: {products_with_energy_text}")
            print(f"  - Without any energy info: {products_without_any_info}")
            print(f"{'='*60}")

    except Exception as e:
        logger.error(f"Error during test scrape: {str(e)}")
        import traceback
        traceback.print_exc()

    return products


def save_test_results(products: List[ProductInfo], test_name: str = "test", country_key: str = "italy"):
    """Save test results to files"""
    if not products:
        logger.warning("No products to save")
        return

    # Create test subdirectory with country and timestamp
    test_dir = os.path.join(DATA_DIR, f"test_{country_key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(test_dir, exist_ok=True)

    # Save as JSON for easy inspection
    json_file = os.path.join(test_dir, f"{test_name}_results.json")
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump([p.to_dict() for p in products], f, indent=2, ensure_ascii=False)
    logger.info(f"Saved test results to {json_file}")

    # Try to save as Excel too
    try:
        import pandas as pd
        df = pd.DataFrame([p.to_dict() for p in products])

        # Add energy status column
        df['energy_status'] = df['has_energy_text'].apply(
            lambda x: 'Energy text only' if x else 'No energy info'
        )

        excel_file = os.path.join(test_dir, f"{test_name}_results.xlsx")
        df.to_excel(excel_file, index=False)
        logger.info(f"Saved test results to {excel_file}")

        # Create a simple brand summary
        brands = df['brand'].unique()
        brand_summary = {
            'total_products': len(df),
            'unique_brands': len(brands),
            'brands': sorted(brands),
            'products_with_energy_text': len(df[df['has_energy_text'] == True]),
            'products_without_any_info': len(df[df['has_energy_text'] == False])
        }

        summary_file = os.path.join(test_dir, f"{test_name}_brand_summary.json")
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(brand_summary, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved brand summary to {summary_file}")

    except ImportError:
        logger.warning("pandas not installed, skipping Excel export")


async def main():
    """Run the test"""
    import argparse

    parser = argparse.ArgumentParser(description='Test Energy Label Scraper with Location Settings')
    parser.add_argument('--url', type=str,
                       default="https://www.amazon.it/s?k=forni+domestici",
                       help='Amazon search URL to test')
    parser.add_argument('--country', type=str, default='italy',
                       help='Country key (italy, france, spain, sweden, netherlands)')
    parser.add_argument('--category', type=str, default='Domestic Ovens',
                       help='Category name for the test')
    parser.add_argument('--max-products', type=int, default=10,
                       help='Maximum products to process (default: 10)')
    parser.add_argument('--no-headless', action='store_true',
                       help='Show browser window during test')

    args = parser.parse_args()

    print("Energy Label Scraper Test with Location Settings")
    print("=" * 60)
    print(f"Test URL: {args.url}")
    print(f"Country: {args.country}")
    print(f"Category: {args.category}")
    print(f"Max products: {args.max_products}")
    print(f"Browser mode: {'Visible' if args.no_headless else 'Headless'}")

    # Get country config
    country_config = COUNTRY_CONFIGS.get(args.country)
    if country_config:
        if country_config.get("use_postcode", False):
            print(f"Location: Will set postcode to {country_config.get('postcode')}")
        else:
            print(f"Location: Automatic")
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
        headless=not args.no_headless
    )

    try:
        # Run the test
        products = await test_single_url_with_location(
            scraper=scraper,
            test_url=args.url,
            country_key=args.country,
            category=args.category,
            max_products=args.max_products
        )

        # Save test results
        if products:
            save_test_results(products, f"{args.country}_{args.category.replace(' ', '_')}", args.country)

            # Print some sample results
            print("\nSample Results:")
            print("===============")
            for i, product in enumerate(products[:5]):
                print(f"\n{i+1}. {product.brand} - {product.product_name[:60]}...")
                print(f"   Seller: {product.seller_name}")
                print(f"   Has energy text: {product.has_energy_text}")
        else:
            print("\nNo products were processed. Check the logs for errors.")

    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    except Exception as e:
        logger.error(f"Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())