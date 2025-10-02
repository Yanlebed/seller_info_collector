#!/usr/bin/env python3
"""
Test script for Energy Label Link Collector - Module 1

This test:
1. Tests link collection for Spain refrigerators
2. Uses the provided search URL
3. Collects links from the first page only (for quick testing)
4. Saves results to a test directory
"""

import asyncio
import logging
import os
import json
from datetime import datetime
from typing import List

# Import the link collector module
from energy_label_link_collector import (
    EnergyLabelLinkCollector,
    ProductLink,
    COUNTRY_CONFIGS
)
from proxy_manager import ProxyManager
from captcha_solver import CaptchaSolver

# Configure logging for test
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('test_link_collector.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Test configuration
TEST_URL = "https://www.amazon.es/s?k=refrigerador&__mk_es_ES=%C3%85M%C3%85%C5%BD%C3%95%C3%91&crid=2V1P8PHQX1LFV&sprefix=refrigerador%2Caps%2C99&ref=nb_sb_noss_1"
TEST_COUNTRY = "spain"
TEST_CATEGORY = "Refrigerators"
MAX_PRODUCTS_TO_TEST = 10  # Limit for quick testing

# Test output directory
TEST_DIR = "test_results"
os.makedirs(TEST_DIR, exist_ok=True)


class TestLinkCollector(EnergyLabelLinkCollector):
    """Extended collector for testing with specific URL"""

    async def test_specific_url(self, test_url: str, country_key: str,
                                category_name: str, max_products: int = 10) -> List[ProductLink]:
        """Test link collection with a specific URL"""

        country_config = COUNTRY_CONFIGS[country_key]
        domain = country_config["domain"]
        locale = country_config["locale"]
        use_postcode = country_config.get("use_postcode", False)
        postcode = country_config.get("postcode", "")

        logger.info(f"Testing link collection for {country_key}")
        logger.info(f"URL: {test_url}")
        logger.info(f"Category: {category_name}")
        logger.info(f"Max products to collect: {max_products}")

        links = []

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

                # Navigate directly to the test URL
                logger.info(f"Navigating to test URL...")
                test_url_with_lang = self.add_language_param(test_url)
                await page.goto(test_url_with_lang, wait_until="domcontentloaded")

                # Handle intermediate page if present
                if await self.handle_intermediate_page(page, domain):
                    logger.info("Handled intermediate page after navigation")
                    # May need to navigate to the URL again after intermediate page
                    await page.goto(test_url_with_lang, wait_until="domcontentloaded")

                # Handle cookie banner
                await self.handle_cookie_banner(page)
                await self.random_delay()

                # Wait for search results
                try:
                    await page.wait_for_selector('xpath=//span[@data-component-type="s-search-results"]', timeout=15000)
                    logger.info("Search results loaded successfully")
                except:
                    logger.error("Failed to load search results")
                    # Take screenshot for debugging
                    screenshot_path = os.path.join(TEST_DIR, f"error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                    await page.screenshot(path=screenshot_path)
                    logger.info(f"Screenshot saved to: {screenshot_path}")
                    return []

                # Find all products on the page
                product_selector = "xpath=//div[contains(@class, 's-main-slot')]//div[@data-component-type='s-search-result']"
                product_elements = await page.query_selector_all(product_selector)

                logger.info(f"Found {len(product_elements)} products on the page")

                # Statistics
                products_with_formal_label = 0
                products_without_formal_label = 0
                products_with_energy_text = 0

                # Process products (limited by max_products)
                for i, product_element in enumerate(product_elements[:max_products]):
                    try:
                        # Extract ASIN
                        asin = await product_element.get_attribute("data-asin")
                        if not asin:
                            logger.warning(f"Product {i + 1}: No ASIN found")
                            continue

                        # Check for energy label
                        has_formal_label, has_energy_text = await self.check_for_energy_label(product_element)

                        if has_formal_label:
                            products_with_formal_label += 1
                            logger.info(f"Product {i + 1} (ASIN: {asin}) - Has formal energy label (skipping)")
                            continue
                        else:
                            products_without_formal_label += 1
                            if has_energy_text:
                                products_with_energy_text += 1
                            logger.info(
                                f"Product {i + 1} (ASIN: {asin}) - No formal label (energy text: {has_energy_text})")

                        # Find product link
                        link_element = await product_element.query_selector('h2 a')
                        if not link_element:
                            link_element = await product_element.query_selector('a.a-link-normal')

                        if not link_element:
                            logger.warning(f"No link found for ASIN {asin}")
                            continue

                        href = await link_element.get_attribute("href")
                        if not href:
                            continue

                        # Construct full URL
                        if not href.startswith("http"):
                            product_url = f"https://www.{domain}{href}"
                        else:
                            product_url = href

                        # Add language parameter
                        product_url = self.add_language_param(product_url)

                        # Create ProductLink
                        product_link = ProductLink(
                            asin=asin,
                            url=product_url,
                            has_energy_text=has_energy_text,
                            category=category_name,
                            category_key="test_category",
                            country=country_key,
                            domain=domain
                        )

                        links.append(product_link)
                        logger.info(f"✓ Collected link for {asin}")

                    except Exception as e:
                        logger.error(f"Error processing product {i + 1}: {str(e)}")

                # Print test statistics
                print(f"\nTest Statistics:")
                print(f"{'=' * 40}")
                print(f"Total products checked: {min(max_products, len(product_elements))}")
                print(f"Products with formal energy label: {products_with_formal_label}")
                print(f"Products without formal label: {products_without_formal_label}")
                print(f"  - With energy text: {products_with_energy_text}")
                print(f"  - Without any energy info: {products_without_formal_label - products_with_energy_text}")
                print(f"Links collected: {len(links)}")
                print(f"{'=' * 40}")

        except Exception as e:
            logger.error(f"Error during test: {str(e)}")
            import traceback
            traceback.print_exc()

        return links

    def save_test_results(self, links: List[ProductLink]):
        """Save test results to file"""
        if not links:
            logger.warning("No links to save")
            return

        # Create test output file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(TEST_DIR, f"test_links_{TEST_COUNTRY}_{timestamp}.json")

        # Convert to dictionaries
        links_data = [link.to_dict() for link in links]

        # Save to file
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({
                "test_info": {
                    "test_url": TEST_URL,
                    "country": TEST_COUNTRY,
                    "category": TEST_CATEGORY,
                    "test_timestamp": datetime.now().isoformat(),
                    "max_products_tested": MAX_PRODUCTS_TO_TEST
                },
                "results": {
                    "total_links": len(links_data),
                    "with_energy_text": sum(1 for link in links_data if link['has_energy_text']),
                    "without_energy_info": sum(1 for link in links_data if not link['has_energy_text'])
                },
                "links": links_data
            }, f, indent=2, ensure_ascii=False)

        print(f"\nTest results saved to: {filename}")

        # Also print sample links
        print(f"\nSample collected links:")
        print(f"{'=' * 60}")
        for i, link in enumerate(links[:3]):
            print(f"\n{i + 1}. ASIN: {link.asin}")
            print(f"   Energy text: {link.has_energy_text}")
            print(f"   URL: {link.url[:100]}...")


async def run_test():
    """Run the link collector test"""
    print("Energy Label Link Collector - Test Script")
    print("=" * 60)
    print(f"Test URL: {TEST_URL}")
    print(f"Country: {TEST_COUNTRY}")
    print(f"Category: {TEST_CATEGORY}")
    print(f"Max products: {MAX_PRODUCTS_TO_TEST}")
    print()

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

    # Initialize test collector
    collector = TestLinkCollector(
        proxy_manager=proxy_manager,
        captcha_solver=captcha_solver,
        headless=False  # Show browser for testing
    )

    try:
        # Run the test
        links = await collector.test_specific_url(
            test_url=TEST_URL,
            country_key=TEST_COUNTRY,
            category_name=TEST_CATEGORY,
            max_products=MAX_PRODUCTS_TO_TEST
        )

        # Save results
        if links:
            collector.save_test_results(links)
            print(f"\n✓ Test completed successfully!")
            print(f"  Collected {len(links)} product links")
        else:
            print(f"\n✗ Test completed but no links were collected")
            print(f"  Check the logs for errors")

    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    except Exception as e:
        logger.error(f"Test failed: {str(e)}")
        import traceback
        traceback.print_exc()


async def main():
    """Main entry point"""
    await run_test()


if __name__ == "__main__":
    asyncio.run(main())