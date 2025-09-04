"""
Energy Label Data Extractor - Module 2

This module handles:
1. Reading product links from JSON files created by Module 1
2. Visiting each product page
3. Extracting detailed product information (brand, seller, etc.)
4. Saving the final data to Excel/JSON files

Input: JSON files with product links from Module 1
Output: Excel files with detailed product and brand information
"""

import asyncio
import logging
import random
import json
import os
import re
import glob
from datetime import datetime
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field

from camoufox.async_api import AsyncCamoufox
from playwright.async_api import Page

from proxy_manager import ProxyManager
from captcha_solver import CaptchaSolver
from amazon_utils import (
    handle_cookie_banner as util_handle_cookie_banner,
    handle_intermediate_page as util_handle_intermediate_page,
    navigate_with_handling,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('energy_label_data_extractor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Directories
DATA_DIR = "energy_label_data"
LINKS_DIR = os.path.join(DATA_DIR, "product_links")
RESULTS_DIR = os.path.join(DATA_DIR, "extracted_data")
os.makedirs(RESULTS_DIR, exist_ok=True)

# Import shared models and configurations
from models import ProductInfo
from amazon_config import COUNTRY_CONFIGS

class EnergyLabelDataExtractor:
    """Extractor for detailed product information from collected links"""

    def __init__(self,
                 proxy_manager: Optional[ProxyManager] = None,
                 captcha_solver: Optional[CaptchaSolver] = None,
                 delay_range: tuple = (2.0, 5.0),
                 headless: bool = True,
                 batch_size: int = 50):
        self.delay_range = delay_range
        self.proxy_manager = proxy_manager
        self.captcha_solver = captcha_solver
        self.headless = headless
        self.batch_size = batch_size  # Process in batches to save progress
        self.products_data: List[ProductInfo] = []
        self.processed_asins: Set[str] = set()
        self.brands_found: Dict[str, Set[str]] = {}  # domain -> brands
        self.failed_products: List[dict] = []  # Track failed extractions

    async def random_delay(self, min_factor=1.0, max_factor=1.0):
        """Add a random delay to simulate human behavior"""
        min_delay, max_delay = self.delay_range
        min_delay *= 0.7
        max_delay *= 0.5
        factor = random.uniform(min_factor, max_factor)
        extra_ms = random.randint(0, 300) / 1000
        delay = random.uniform(min_delay, max_delay) * factor + extra_ms
        await asyncio.sleep(delay)

    async def setup_camoufox(self, domain: str, locale: str, proxy: Optional[str] = None):
        """Initialize Camoufox with appropriate configuration"""
        camoufox_config = {
            "headless": self.headless,
            "os": ["windows", "macos"],
            "locale": locale,
            "geoip": True,
            "block_webrtc": True,
            "humanize": True,
        }

        if proxy:
            camoufox_config["proxy"] = {"server": proxy}

        return AsyncCamoufox(**camoufox_config)

    async def handle_intermediate_page(self, page: Page, domain: str) -> bool:
        """Delegate to shared intermediate-page handler."""
        return await util_handle_intermediate_page(page, domain)

    def load_links_from_file(self, filepath: str) -> List[dict]:
        """Load product links from a JSON file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('links', [])
        except Exception as e:
            logger.error(f"Error loading links from {filepath}: {str(e)}")
            return []

    def get_latest_links_file(self, country: str) -> Optional[str]:
        """Get the most recent links file for a country"""
        pattern = os.path.join(LINKS_DIR, f"{country}_product_links_*.json")
        files = glob.glob(pattern)

        if not files:
            return None

        # Sort by modification time and get the latest
        latest_file = max(files, key=os.path.getmtime)
        return latest_file

    def load_progress(self, country: str) -> Set[str]:
        """Load ASINs that have already been processed"""
        progress_file = os.path.join(RESULTS_DIR, f"{country}_progress.json")

        if os.path.exists(progress_file):
            try:
                with open(progress_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return set(data.get('processed_asins', []))
            except Exception as e:
                logger.error(f"Error loading progress: {str(e)}")

        return set()

    def save_progress(self, country: str):
        """Save processing progress"""
        progress_file = os.path.join(RESULTS_DIR, f"{country}_progress.json")

        try:
            with open(progress_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'processed_asins': list(self.processed_asins),
                    'last_update': datetime.now().isoformat(),
                    'total_processed': len(self.processed_asins)
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving progress: {str(e)}")

    async def extract_brand_from_product_page(self, page: Page) -> str:
        """Extract brand from product details table"""
        try:
            # Multiple selectors for brand
            brand_selectors = [
                'xpath=//table[@class="a-keyvalue prodDetTable"]/tbody/tr[th[contains(text(), "Brand")]]/td',
                'xpath=//table[@class="a-keyvalue prodDetTable"]//tr[th[contains(text(), "Marque")]]/td',  # French
                'xpath=//table[@class="a-keyvalue prodDetTable"]//tr[th[contains(text(), "Marca")]]/td',   # Spanish/Italian
                'xpath=//table[@class="a-keyvalue prodDetTable"]//tr[th[contains(text(), "Merk")]]/td',    # Dutch
                'xpath=//table[@class="a-keyvalue prodDetTable"]//tr[th[contains(text(), "Märke")]]/td',   # Swedish
                'xpath=//div[@id="bylineInfo"]/span[contains(@class, "author")]/a',
                'xpath=//a[@id="bylineInfo"]'
            ]

            for selector in brand_selectors:
                brand_element = await page.query_selector(selector)
                if brand_element:
                    brand_text = await brand_element.text_content()
                    if brand_text:
                        return brand_text.strip()

            return "Unknown"
        except Exception as e:
            logger.error(f"Error extracting brand: {str(e)}")
            return "Unknown"

    async def extract_product_info(self, page: Page, link_data: dict) -> Optional[ProductInfo]:
        """Extract product information from product page"""
        try:
            # Extract product name
            product_name = "Unknown"
            title_element = await page.query_selector('xpath=//span[@id="productTitle"]')
            if title_element:
                product_name = await title_element.text_content()
                product_name = product_name.strip() if product_name else "Unknown"

            # Extract brand
            brand = await self.extract_brand_from_product_page(page)

            # Extract seller information
            seller_name = "Unknown"
            seller_url = ""

            seller_selectors = [
                "xpath=//a[@id='sellerProfileTriggerId']",
                "xpath=//div[@id='merchant-info']//a[contains(@href, '/sp?seller=')]",
                "xpath=//div[@data-csa-c-slot-id='odf-feature-text-desktop-merchant-info']//a[contains(@href, '/sp?seller=')]",
                "xpath=//span[contains(text(), 'Sold by')]/../a",
                "xpath=//span[contains(text(), 'Vendu par')]/../a",
                "xpath=//span[contains(text(), 'Venduto da')]/../a",
                "xpath=//span[contains(text(), 'Vendido por')]/../a",
                "xpath=//span[contains(text(), 'Verkocht door')]/../a",
                "xpath=//span[contains(text(), 'Såld av')]/../a"
            ]

            seller_found = False
            for selector in seller_selectors:
                seller_element = await page.query_selector(selector)
                if seller_element:
                    seller_text = await seller_element.text_content()
                    if seller_text:
                        seller_name = seller_text.strip()

                    href = await seller_element.get_attribute("href")
                    if href:
                        if not href.startswith("http"):
                            seller_url = f"https://www.{link_data['domain']}{href}"
                        else:
                            seller_url = href

                        # Extract seller ID and construct proper URL
                        seller_id_match = re.search(r'seller=([A-Z0-9]+)', href)
                        if seller_id_match:
                            seller_id = seller_id_match.group(1)
                            if not seller_url or "/gp/" in seller_url:
                                seller_url = f"https://www.{link_data['domain']}/sp?seller={seller_id}"

                        seller_found = True
                        logger.debug(f"Found seller: {seller_name}")
                        break

            # Check for Amazon as seller
            if not seller_found:
                amazon_selectors = [
                    "xpath=//div[@id='merchant-info'][contains(text(), 'Amazon')]",
                    "xpath=//span[contains(text(), 'Ships from and sold by Amazon')]",
                    "xpath=//span[contains(text(), 'Expédié et vendu par Amazon')]",
                    "xpath=//span[contains(text(), 'Spedito e venduto da Amazon')]",
                    "xpath=//span[contains(text(), 'Enviado y vendido por Amazon')]",
                    "xpath=//span[contains(text(), 'Verzonden en verkocht door Amazon')]",
                    "xpath=//span[contains(text(), 'Skickas från och säljs av Amazon')]"
                ]

                for selector in amazon_selectors:
                    amazon_element = await page.query_selector(selector)
                    if amazon_element:
                        seller_name = "Amazon"
                        seller_url = f"https://www.{link_data['domain']}"
                        break

            # Create ProductInfo object
            product_info = ProductInfo(
                amazon_host=f"www.{link_data['domain']}",
                brand=brand,
                product_name=product_name,
                product_url=link_data['url'],
                seller_name=seller_name,
                seller_url=seller_url,
                has_energy_text=link_data['has_energy_text'],
                category=link_data['category'],
                asin=link_data['asin']
            )

            return product_info

        except Exception as e:
            logger.error(f"Error extracting product info for ASIN {link_data['asin']}: {str(e)}")
            return None

    async def process_product_batch(self, links: List[dict], country_config: dict) -> List[ProductInfo]:
        """Process a batch of product links"""
        domain = country_config["domain"]
        locale = country_config["locale"]
        batch_products = []

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

                # Process each link
                for i, link_data in enumerate(links):
                    asin = link_data['asin']

                    # Skip if already processed
                    if asin in self.processed_asins:
                        logger.debug(f"Skipping already processed ASIN: {asin}")
                        continue

                    logger.info(f"Processing product {i+1}/{len(links)}: {asin}")

                    try:
                        # Navigate to product page with intermediate/cookie handling
                        await navigate_with_handling(
                            page,
                            link_data['url'],
                            domain,
                            wait_until="domcontentloaded",
                            timeout_ms=30000,
                        )

                        # Wait for product title
                        await page.wait_for_selector("xpath=//span[@id='productTitle']", timeout=10000)
                        await self.random_delay()

                        # Extract product information
                        product_info = await self.extract_product_info(page, link_data)

                        if product_info:
                            batch_products.append(product_info)
                            self.processed_asins.add(asin)

                            # Track brands
                            if domain not in self.brands_found:
                                self.brands_found[domain] = set()
                            self.brands_found[domain].add(product_info.brand)

                            logger.info(f"✓ Extracted: {product_info.brand} - {product_info.product_name[:50]}...")
                        else:
                            logger.warning(f"✗ Failed to extract info for ASIN {asin}")
                            self.failed_products.append(link_data)

                    except Exception as e:
                        logger.error(f"Error processing product {asin}: {str(e)}")
                        self.failed_products.append(link_data)

                    # Add delay between products
                    await self.random_delay(1.0, 2.0)

        except Exception as e:
            logger.error(f"Error processing batch: {str(e)}")

        return batch_products

    async def process_country(self, country_key: str):
        """Process all products for a specific country"""
        # Get latest links file
        links_file = self.get_latest_links_file(country_key)
        if not links_file:
            logger.warning(f"No links file found for {country_key}")
            return

        logger.info(f"Loading links from: {links_file}")

        # Load links
        all_links = self.load_links_from_file(links_file)
        if not all_links:
            logger.warning(f"No links found in file for {country_key}")
            return

        logger.info(f"Found {len(all_links)} links for {country_key}")

        # Load progress (previously processed ASINs)
        self.processed_asins = self.load_progress(country_key)
        logger.info(f"Previously processed: {len(self.processed_asins)} products")

        # Filter out already processed products
        remaining_links = [link for link in all_links if link['asin'] not in self.processed_asins]
        logger.info(f"Remaining to process: {len(remaining_links)} products")

        if not remaining_links:
            logger.info(f"All products already processed for {country_key}")
            return

        # Get country config
        country_config = COUNTRY_CONFIGS.get(country_key, {})
        if not country_config:
            logger.error(f"No configuration found for {country_key}")
            return

        # Process in batches
        country_products = []
        total_batches = (len(remaining_links) + self.batch_size - 1) // self.batch_size

        for batch_num in range(total_batches):
            start_idx = batch_num * self.batch_size
            end_idx = min(start_idx + self.batch_size, len(remaining_links))
            batch_links = remaining_links[start_idx:end_idx]

            logger.info(f"Processing batch {batch_num + 1}/{total_batches} ({len(batch_links)} products)")

            # Process batch
            batch_products = await self.process_product_batch(batch_links, country_config)
            country_products.extend(batch_products)

            # Save progress after each batch
            self.save_progress(country_key)
            self.save_intermediate_results(country_key, country_products)

            logger.info(f"Batch complete. Total extracted so far: {len(country_products)}")

            # Delay between batches
            if batch_num < total_batches - 1:
                await asyncio.sleep(5.0)

        # Save final results for this country
        self.save_country_results(country_key, country_products)

        # Add to overall products
        self.products_data.extend(country_products)

        logger.info(f"Completed {country_key}: Extracted {len(country_products)} products")

    def save_intermediate_results(self, country_key: str, products: List[ProductInfo]):
        """Save intermediate results during processing"""
        if not products:
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(RESULTS_DIR, f"{country_key}_intermediate_{timestamp}.json")

        data = [product.to_dict() for product in products]
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.debug(f"Saved intermediate results to {filename}")

    def save_country_results(self, country_key: str, products: List[ProductInfo]):
        """Save final results for a country"""
        if not products:
            logger.warning(f"No products to save for {country_key}")
            return

        # Create country subdirectory
        country_dir = os.path.join(RESULTS_DIR, country_key)
        os.makedirs(country_dir, exist_ok=True)

        # Save detailed product data
        try:
            import pandas as pd

            # Convert to DataFrame
            data = [product.to_dict() for product in products]
            df = pd.DataFrame(data)

            # Add energy status column
            df['energy_status'] = df['has_energy_text'].apply(
                lambda x: 'Energy text only' if x else 'No energy info'
            )

            # Save to Excel
            filename = os.path.join(country_dir, f"{country_key}_products_extracted.xlsx")
            df.to_excel(filename, index=False)
            logger.info(f"Saved {len(data)} products to {filename}")

            # Create brand summary
            brands = df['brand'].value_counts()
            brand_summary = pd.DataFrame({
                'brand': brands.index,
                'product_count': brands.values
            })

            summary_file = os.path.join(country_dir, f"{country_key}_brand_summary.xlsx")
            brand_summary.to_excel(summary_file, index=False)
            logger.info(f"Saved brand summary to {summary_file}")

        except ImportError:
            logger.error("pandas not installed, saving as JSON")
            filename = os.path.join(country_dir, f"{country_key}_products_extracted.json")
            data = [product.to_dict() for product in products]
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        # Save failed products if any
        if self.failed_products:
            failed_file = os.path.join(country_dir, f"{country_key}_failed_products.json")
            with open(failed_file, 'w', encoding='utf-8') as f:
                json.dump(self.failed_products, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(self.failed_products)} failed products to {failed_file}")

    def save_overall_results(self):
        """Save overall results across all countries"""
        if not self.products_data:
            logger.warning("No products to save")
            return

        try:
            import pandas as pd

            # Convert all products to DataFrame
            data = [product.to_dict() for product in self.products_data]
            df = pd.DataFrame(data)

            # Add energy status column
            df['energy_status'] = df['has_energy_text'].apply(
                lambda x: 'Energy text only' if x else 'No energy info'
            )

            # Save overall detailed results
            filename = os.path.join(RESULTS_DIR, "all_products_extracted.xlsx")
            df.to_excel(filename, index=False)
            logger.info(f"Saved {len(data)} total products to {filename}")

            # Create overall brand analysis
            brand_analysis = []
            for product in self.products_data:
                brand_key = f"{product.amazon_host}_{product.brand}"
                existing = next((b for b in brand_analysis if
                               b['amazon_host'] == product.amazon_host and b['brand'] == product.brand), None)

                if existing:
                    existing['total_products'] += 1
                    if product.has_energy_text:
                        existing['products_with_energy_text'] += 1
                    else:
                        existing['products_without_any_energy_info'] += 1
                else:
                    brand_analysis.append({
                        'amazon_host': product.amazon_host,
                        'brand': product.brand,
                        'total_products': 1,
                        'products_with_energy_text': 1 if product.has_energy_text else 0,
                        'products_without_any_energy_info': 0 if product.has_energy_text else 1
                    })

            # Save brand analysis
            if brand_analysis:
                df_analysis = pd.DataFrame(brand_analysis)
                df_analysis = df_analysis.sort_values(['amazon_host', 'brand'])

                analysis_file = os.path.join(RESULTS_DIR, "all_brands_analysis_extracted.xlsx")
                df_analysis.to_excel(analysis_file, index=False)
                logger.info(f"Saved brand analysis to {analysis_file}")

        except ImportError:
            logger.error("pandas not installed, saving as JSON")
            filename = os.path.join(RESULTS_DIR, "all_products_extracted.json")
            data = [product.to_dict() for product in self.products_data]
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

    def print_summary(self):
        """Print extraction summary"""
        print("\n" + "=" * 60)
        print("DATA EXTRACTION SUMMARY")
        print("=" * 60)

        total_products = len(self.products_data)
        products_with_text = sum(1 for p in self.products_data if p.has_energy_text)
        products_without_info = total_products - products_with_text

        print(f"Total products extracted: {total_products}")
        print(f"Products with energy text: {products_with_text} ({products_with_text/max(1,total_products)*100:.1f}%)")
        print(f"Products without energy info: {products_without_info} ({products_without_info/max(1,total_products)*100:.1f}%)")
        print(f"Failed extractions: {len(self.failed_products)}")
        print("-" * 60)

        # By country breakdown
        by_country = {}
        for product in self.products_data:
            host = product.amazon_host
            if host not in by_country:
                by_country[host] = {"total": 0, "brands": set()}
            by_country[host]["total"] += 1
            by_country[host]["brands"].add(product.brand)

        for host, stats in by_country.items():
            print(f"\n{host}:")
            print(f"  Total products: {stats['total']}")
            print(f"  Unique brands: {len(stats['brands'])}")

        print("\n" + "=" * 60)
        print(f"Results saved to: {RESULTS_DIR}")
        print("=" * 60)

    async def process_all_countries(self, countries: Optional[List[str]] = None):
        """Process all or specified countries"""
        # Determine which countries to process
        if countries:
            target_countries = countries
        else:
            # Find all countries with link files
            pattern = os.path.join(LINKS_DIR, "*_product_links_*.json")
            files = glob.glob(pattern)
            target_countries = list(set(f.split('_product_links_')[0].split('/')[-1] for f in files))

        if not target_countries:
            logger.warning("No link files found to process")
            return

        logger.info(f"Will process {len(target_countries)} countries: {', '.join(target_countries)}")

        # Process each country
        for country_key in target_countries:
            try:
                await self.process_country(country_key)

                # Delay between countries
                if country_key != target_countries[-1]:
                    await asyncio.sleep(5.0)

            except Exception as e:
                logger.error(f"Error processing {country_key}: {str(e)}")

        # Save overall results
        self.save_overall_results()


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Energy Label Data Extractor - Module 2')
    parser.add_argument('--countries', type=str,
                       help='Comma-separated country codes (e.g., italy,france)')
    parser.add_argument('--no-headless', action='store_true',
                       help='Show browser window')
    parser.add_argument('--batch-size', type=int, default=50,
                       help='Batch size for processing (default: 50)')
    parser.add_argument('--proxy', type=str,
                       help='Single proxy to use')
    args = parser.parse_args()

    # Parse countries
    countries = None
    if args.countries:
        countries = [c.strip().lower() for c in args.countries.split(',')]

    # Set up proxy manager
    proxy_manager = None
    if os.path.exists("proxies.txt") or args.proxy:
        proxy_manager = ProxyManager("proxies.txt")
        if os.path.exists("proxies.txt"):
            await proxy_manager.load_proxies()

        if args.proxy:
            from proxy_manager import ProxyStats
            proxy_manager.proxies[args.proxy] = ProxyStats(address=args.proxy)
            proxy_manager.unverified_proxies.append(args.proxy)

    # Set up CAPTCHA solver
    captcha_solver = None
    captcha_api_key = os.getenv("CAPTCHA_API_KEY", "CAP-956BF088AFEBDE1D55D75C975171507466CFFDF3C9657C7412145974FF602B9A")
    if captcha_api_key:
        captcha_solver = CaptchaSolver(captcha_api_key)

    # Initialize extractor
    extractor = EnergyLabelDataExtractor(
        proxy_manager=proxy_manager,
        captcha_solver=captcha_solver,
        headless=not args.no_headless,
        batch_size=args.batch_size
    )

    print("Energy Label Data Extractor - Module 2")
    print("=" * 60)
    print("This module will:")
    print("1. Read product links from Module 1 output")
    print("2. Visit each product page")
    print("3. Extract brand and seller information")
    print("4. Save detailed product data")
    print()
    print(f"Reading links from: {LINKS_DIR}")
    print(f"Saving results to: {RESULTS_DIR}")
    print(f"Batch size: {args.batch_size}")
    print()

    try:
        # Process countries
        await extractor.process_all_countries(countries)

        # Print summary
        extractor.print_summary()

    except KeyboardInterrupt:
        logger.info("Extraction interrupted by user")
        extractor.print_summary()
    except Exception as e:
        logger.error(f"Unhandled exception: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())