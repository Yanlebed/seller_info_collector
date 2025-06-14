#!/usr/bin/env python3
"""
Test script for Energy Label Scraper
Tests the scraper on a single Amazon.it URL for domestic ovens
"""

import asyncio
import logging
import os
import json
from datetime import datetime
from typing import List, Dict

# Import required components
from energy_label_scraper import EnergyLabelScraper, ProductInfo, DATA_DIR
from camoufox.async_api import AsyncCamoufox
from playwright.async_api import Page
from proxy_manager import ProxyManager, ProxyStats
from captcha_solver import CaptchaSolver

# Configure logging for test
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('test_energy_scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def collect_product_links(page: Page, scraper: EnergyLabelScraper, max_products: int = 10) -> List[Dict]:
    """
    Collect product links and ASINs from search results page

    Returns list of dicts with: asin, url, has_formal_label, has_energy_text
    """
    logger.info("Collecting product information from search results...")

    # Wait for search results
    await page.wait_for_selector('xpath=//span[@data-component-type="s-search-results"]', timeout=15000)
    logger.info("Search results loaded")

    # Find all products on the page
    product_selector = "xpath=//div[contains(@class, 's-main-slot')]//div[@data-component-type='s-search-result']"
    product_elements = await page.query_selector_all(product_selector)

    logger.info(f"Found {len(product_elements)} products on the page")

    # Collect product data
    products_data = []

    for i, product_element in enumerate(product_elements[:max_products]):
        try:
            # Extract ASIN
            asin = await product_element.get_attribute("data-asin")
            if not asin:
                logger.warning(f"Product {i + 1}: No ASIN found, skipping")
                continue

            # Check for energy label in search results
            has_formal_label, has_energy_text = await scraper.check_for_energy_label(product_element)

            # Skip products with formal energy label
            if has_formal_label:
                logger.info(f"Product {i + 1} (ASIN: {asin}) - SKIPPING: Has formal energy label")
                continue

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
            domain = page.url.split('/')[2]
            if not href.startswith("http"):
                product_url = f"https://{domain}{href}"
            else:
                product_url = href

            products_data.append({
                'asin': asin,
                'url': product_url,
                'has_formal_label': has_formal_label,
                'has_energy_text': has_energy_text
            })

            logger.info(f"Product {i + 1} (ASIN: {asin}) - Collected (has energy text: {has_energy_text})")

        except Exception as e:
            logger.error(f"Error collecting product {i + 1}: {str(e)}")

    logger.info(f"Collected {len(products_data)} products without formal energy labels")
    return products_data


async def test_single_url(scraper: EnergyLabelScraper, test_url: str,
                          domain: str = "amazon.it", category: str = "Domestic Ovens Test",
                          max_products: int = 10) -> List[ProductInfo]:
    """
    Test the scraper on a single URL

    Args:
        scraper: EnergyLabelScraper instance
        test_url: The URL to test
        domain: Amazon domain
        category: Category name for logging
        max_products: Maximum number of products to process

    Returns:
        List of ProductInfo objects
    """
    logger.info(f"Starting test scrape of {test_url}")
    logger.info(f"Will process up to {max_products} products")
    product_selector = "xpath=//div[contains(@class, 's-main-slot')]//div[@data-component-type='s-search-result']"
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

        # Setup browser with Italian locale
        camoufox_config = {
            "headless": scraper.headless,
            "os": ["windows", "macos"],
            "locale": "it-IT",
            "geoip": True,
            "block_webrtc": True,
            "humanize": True,
        }

        if proxy:
            camoufox_config["proxy"] = {"server": proxy}

        camoufox = AsyncCamoufox(**camoufox_config)

        async with camoufox as browser:
            page = await browser.new_page()

            # Navigate directly to the test URL
            logger.info(f"Navigating to test URL: {test_url}")
            await page.goto(test_url, wait_until="domcontentloaded")
            await page.wait_for_selector('span[data-component-type="s-search-results"]')

            # Handle intermediate page if present (for Amazon.it)
            try:
                await scraper.handle_intermediate_page(page, domain)
            except AttributeError:
                logger.warning("handle_intermediate_page method not found, skipping")

            # double check if we are on the right page
            try:
                await scraper.handle_intermediate_page(page, domain)
            except AttributeError:
                logger.warning("handle_intermediate_page method not found, skipping")

            # Handle cookie banner
            try:
                await scraper.handle_cookie_banner(page)
            except AttributeError:
                logger.warning("handle_cookie_banner method not found, skipping")

            try:
                await scraper.random_delay()
            except AttributeError:
                # Fallback delay
                await asyncio.sleep(2.0)

            # Collect product links first
            products_data = await collect_product_links(page, scraper, max_products)

            # Process statistics
            products_with_formal_label = 0  # Already filtered out
            products_with_energy_text = sum(1 for p in products_data if p['has_energy_text'])
            products_without_any_info = sum(1 for p in products_data if not p['has_energy_text'])

            # Now process each product
            for i, product_data in enumerate(products_data):
                try:
                    asin = product_data['asin']
                    product_url = product_data['url']
                    has_energy_text = product_data['has_energy_text']

                    logger.info(f"\n{'=' * 60}")
                    logger.info(f"Processing product {i + 1}/{len(products_data)}: ASIN {asin}")
                    logger.info(f"Product URL: {product_url}")
                    logger.info(f"Has energy text: {has_energy_text}")

                    # Navigate to product page
                    logger.info(f"Navigating to product page...")
                    await page.goto(product_url, wait_until="domcontentloaded")

                    # Wait for product title
                    await page.wait_for_selector("xpath=//span[@id='productTitle']", timeout=10000)
                    try:
                        await scraper.random_delay()
                    except AttributeError:
                        await asyncio.sleep(1.0)

                    # Extract product information
                    try:
                        product_info = await scraper.extract_product_info(
                            page, asin, has_energy_text, category, domain
                        )
                    except AttributeError:
                        logger.error("extract_product_info method not found!")
                        # Create a basic product info manually
                        from energy_label_scraper import ProductInfo

                        # Extract basic info manually
                        product_name = "Unknown"
                        title_element = await page.query_selector('xpath=//span[@id="productTitle"]')
                        if title_element:
                            product_name = await title_element.text_content()
                            product_name = product_name.strip() if product_name else "Unknown"

                        product_info = ProductInfo(
                            amazon_host=f"www.{domain}",
                            brand="Unknown",
                            product_name=product_name,
                            product_url=page.url,
                            seller_name="Unknown",
                            seller_url="",
                            has_energy_text=has_energy_text,
                            category=category,
                            asin=asin
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

                except Exception as e:
                    logger.error(f"Error processing product {i + 1}: {str(e)}")

            # Print test summary
            print(f"\n{'=' * 60}")
            print("TEST SUMMARY")
            print(f"{'=' * 60}")
            print(f"Total products found on page: {len(await page.query_selector_all(product_selector))}")
            print(f"Products without formal label: {len(products_data)}")
            print(f"Products processed: {len(products)}")
            print(f"Products with energy text only: {products_with_energy_text}")
            print(f"Products without any energy info: {products_without_any_info}")
            print(f"{'=' * 60}")

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

    # Create test subdirectory with country
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
    print("Energy Label Scraper Test")
    print("========================")
    print(f"Test URL: https://www.amazon.it/s?k=forni+domestici")
    print(f"This will test the scraper on Italian domestic ovens category")
    print(f"Results will be saved to: {DATA_DIR}/test_italy_YYYYMMDD_HHMMSS/")
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

    try:
        # Run the test
        test_url = "https://www.amazon.it/s?k=forni+domestici&crid=1CBWYOTDQUB53&sprefix=forni+domestici%2Caps%2C85&ref=nb_sb_noss"
        products = await test_single_url(
            scraper=scraper,
            test_url=test_url,
            domain="amazon.it",
            category="Domestic Ovens",
            max_products=10  # Process first 10 products for testing
        )

        # Save test results
        if products:
            save_test_results(products, "amazon_it_ovens", "italy")

            # Print some sample results
            print("\nSample Results:")
            print("===============")
            for i, product in enumerate(products[:5]):
                print(f"\n{i + 1}. {product.brand} - {product.product_name[:60]}...")
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