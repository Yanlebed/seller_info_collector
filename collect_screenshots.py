#!/usr/bin/env python3
"""
Collect screenshots for products missing formal energy labels as standalone step.

Defaults:
- Targets products with no energy info (has_energy_text == False).
- Skips products whose screenshots already exist on disk.
- Resumable via progress JSON.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

import pandas as pd
from camoufox.async_api import AsyncCamoufox
from playwright.async_api import Page

from amazon_utils import (
    handle_cookie_banner as util_handle_cookie_banner,
    handle_intermediate_page as util_handle_intermediate_page,
    random_delay as util_random_delay,
    clean_brand_name as util_clean_brand_name,
    sanitize_dirname as util_sanitize_dirname,
    extract_asin_from_url,
)


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


RESULTS_DIR = Path("energy_label_data/extracted_data")
SCREENSHOTS_DIR = Path("screenshots/brand_products")
PROGRESS_FILE = RESULTS_DIR / "screenshot_collection_progress.json"
MAPPING_FILE = SCREENSHOTS_DIR / "screenshot_mapping.json"


class ScreenshotCollector:
    def __init__(self,
                 headless: bool = True,
                 resume: bool = True,
                 limit: Optional[int] = None,
                 include_energy_text: bool = False,
                 countries: Optional[List[str]] = None,
                 brands: Optional[List[str]] = None):
        self.headless = headless
        self.resume = resume
        self.limit = limit
        self.include_energy_text = include_energy_text
        self.filter_countries = countries or []
        self.filter_brands = set(brands or [])

        self.processed_asins: Set[str] = set()
        self.collected_by_brand: Dict[str, List[str]] = {}

    def load_progress(self) -> None:
        if self.resume and PROGRESS_FILE.exists():
            try:
                data = json.loads(PROGRESS_FILE.read_text())
                self.processed_asins = set(data.get("processed_asins", []))
                self.collected_by_brand = data.get("collected_by_brand", {})
                logger.info(f"Resumed: {len(self.processed_asins)} ASINs processed previously")
            except Exception as e:
                logger.warning(f"Could not load progress: {e}")

    def save_progress(self) -> None:
        data = {
            "processed_asins": list(self.processed_asins),
            "collected_by_brand": self.collected_by_brand,
            "last_updated": datetime.now().isoformat(),
        }
        try:
            PROGRESS_FILE.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.warning(f"Could not save progress: {e}")

    async def setup_browser(self, amazon_host: str) -> AsyncCamoufox:
        logger.info(f"Setting up browser for {amazon_host}")
        camoufox = AsyncCamoufox(headless=self.headless, humanize=True)
        return camoufox

    def sanitize_dirname(self, brand_name: str) -> str:
        return util_sanitize_dirname(brand_name)

    async def handle_cookie_banner(self, page: Page) -> bool:
        return await util_handle_cookie_banner(page)

    async def handle_intermediate_page(self, page: Page, domain: str) -> bool:
        return await util_handle_intermediate_page(page, domain)

    async def random_delay(self, a: float, b: float) -> None:
        await util_random_delay(a, b)

    async def take_product_screenshot(self, page: Page, product_url: str, amazon_host: str, brand_name: str) -> Optional[str]:
        try:
            asin = extract_asin_from_url(product_url)
            if not asin:
                logger.warning(f"ASIN not found in URL: {product_url}")
                return None

            domain = amazon_host.replace("www.", "")
            logger.info(f"Goto product: {product_url}")
            await page.goto(product_url, wait_until="domcontentloaded", timeout=30000)

            if await self.handle_intermediate_page(page, domain):
                logger.info("Handled intermediate page after navigation")
                await self.random_delay(1.0, 2.0)

            await self.handle_cookie_banner(page)
            await self.random_delay(2.0, 4.0)

            product_title = await page.query_selector("#productTitle")
            if product_title:
                await page.evaluate("document.body.style.zoom = '0.8'")
                await asyncio.sleep(1)
                element = await page.query_selector("div#ppd")
                if not element:
                    for selector in ("#dp", "#dp-container", "#centerCol"):
                        element = await page.query_selector(selector)
                        if element:
                            break
                if not element:
                    logger.warning("Suitable product element not found")
                    return None
            else:
                # Fallback: search results by ASIN
                search_url = f"https://{amazon_host}/s?k={asin}"
                logger.info(f"Searching by ASIN at: {search_url}")
                await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                if await self.handle_intermediate_page(page, domain):
                    logger.info("Handled intermediate page after search navigation")
                    await self.random_delay(1.0, 2.0)
                await self.handle_cookie_banner(page)
                await self.random_delay(2.0, 4.0)
                element = None
                for selector in (
                    f'div[data-asin="{asin}"]',
                    'div[data-component-type="s-search-result"]',
                    'div[data-cel-widget*="search_result_"]',
                ):
                    elements = await page.query_selector_all(selector)
                    if elements:
                        element = elements[0]
                        break
                if not element:
                    logger.warning("ASIN not found in search results")
                    return None

            country = amazon_host.replace("www.amazon.", "")
            brand_dirname = self.sanitize_dirname(brand_name)
            filepath = SCREENSHOTS_DIR / country / brand_dirname / f"product_{asin}.png"
            filepath.parent.mkdir(parents=True, exist_ok=True)
            await element.screenshot(path=str(filepath))
            logger.info(f"Saved screenshot: {filepath}")
            return str(filepath)
        except Exception as e:
            logger.error(f"Screenshot failed for {product_url}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    async def process_brand(self, page: Page, amazon_host: str, brand: str, brand_df: pd.DataFrame) -> List[str]:
        screenshots: List[str] = []
        for idx, row in brand_df.iterrows():
            product_url = str(row['product_url'])
            asin = extract_asin_from_url(product_url) or ""
            if asin in self.processed_asins:
                continue
            # Skip if file already exists
            if asin:
                country = amazon_host.replace("www.amazon.", "")
                brand_dirname = self.sanitize_dirname(brand)
                expected = SCREENSHOTS_DIR / country / brand_dirname / f"product_{asin}.png"
                if expected.exists():
                    screenshots.append(str(expected))
                    self.processed_asins.add(asin)
                    continue

            path = await self.take_product_screenshot(page, product_url, amazon_host, brand)
            if path:
                screenshots.append(path)
                if asin:
                    self.processed_asins.add(asin)
            await self.random_delay(3.0, 6.0)
        return screenshots

    async def run(self):
        self.load_progress()

        products_file = RESULTS_DIR / "all_products_extracted.xlsx"
        if not products_file.exists():
            logger.error(f"Products file not found: {products_file}")
            return

        df = pd.read_excel(products_file)

        # Filter: default only products without any energy info
        if not self.include_energy_text:
            df = df[df['has_energy_text'] == False]

        # Filter by countries if provided (amazon_host contains domain)
        if self.filter_countries:
            allowed_hosts = {f"www.amazon.{c.strip()}" for c in self.filter_countries}
            df = df[df['amazon_host'].isin(allowed_hosts)]

        # Filter by brands if provided
        if self.filter_brands:
            df = df[df['brand'].isin(self.filter_brands)]

        # Apply limit
        if self.limit and len(df) > self.limit:
            df = df.head(self.limit)

        logger.info(f"Products to consider: {len(df)}")
        if df.empty:
            return

        # Load existing mapping
        existing_mapping: Dict[str, List[str]] = {}
        if MAPPING_FILE.exists():
            try:
                existing_mapping = json.loads(MAPPING_FILE.read_text())
            except Exception:
                pass

        # Group by (amazon_host, brand) for efficient navigation
        grouped = df.groupby(['amazon_host', 'brand'])

        for (amazon_host, brand), brand_df in grouped:
            logger.info(f"Processing brand {brand} on {amazon_host} with {len(brand_df)} products")
            try:
                camoufox = await self.setup_browser(amazon_host)
                async with camoufox as browser:
                    page = await browser.new_page()
                    shots = await self.process_brand(page, amazon_host, brand, brand_df)
                    key = f"{amazon_host}_{brand}"
                    if key not in existing_mapping:
                        existing_mapping[key] = []
                    existing_mapping[key].extend([s for s in shots if s not in existing_mapping[key]])
                    self.collected_by_brand[key] = shots
            except Exception as e:
                logger.error(f"Error in browser session for {brand}: {e}")
            finally:
                self.save_progress()
                # Persist mapping frequently
                try:
                    MAPPING_FILE.parent.mkdir(parents=True, exist_ok=True)
                    MAPPING_FILE.write_text(json.dumps(existing_mapping, indent=2))
                except Exception as me:
                    logger.warning(f"Could not save mapping: {me}")


async def main():
    import argparse
    parser = argparse.ArgumentParser(description='Collect product screenshots as a standalone step')
    parser.add_argument('--no-headless', action='store_true', help='Show browser window')
    parser.add_argument('--no-resume', action='store_true', help='Start fresh, ignore previous progress')
    parser.add_argument('--reset', action='store_true', help='Reset progress file')
    parser.add_argument('--limit', type=int, help='Limit number of products overall')
    parser.add_argument('--include-energy-text', action='store_true', help='Include products that have energy text (but no formal label)')
    parser.add_argument('--countries', type=str, help='Comma-separated country TLDs, e.g., es,fr,it')
    parser.add_argument('--brands', type=str, help='Comma-separated brand names to include')
    args = parser.parse_args()

    if args.reset:
        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()
            print("✅ Screenshot progress reset")
        else:
            print("ℹ️  No screenshot progress file to reset")
        return

    countries = [c.strip() for c in args.countries.split(',')] if args.countries else None
    brands = [b.strip() for b in args.brands.split(',')] if args.brands else None

    collector = ScreenshotCollector(
        headless=not args.no_headless,
        resume=not args.no_resume,
        limit=args.limit,
        include_energy_text=args.include_energy_text,
        countries=countries,
        brands=brands,
    )
    await collector.run()


if __name__ == "__main__":
    asyncio.run(main())


