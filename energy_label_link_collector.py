"""
Energy Label Link Collector - Module 1

This module handles:
1. Navigation to Amazon categories
2. Setting location (postcode)
3. Finding products without formal energy labels
4. Collecting product links
5. Saving links to JSON files for processing by Module 2

Output: JSON files with product links organized by country
"""

import asyncio
import logging
import random
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field, asdict

from camoufox.async_api import AsyncCamoufox
from playwright.async_api import Page

from proxy_manager import ProxyManager
from captcha_solver import CaptchaSolver
from amazon_utils import add_language_param, navigate_with_handling
from models import ProductLink
from amazon_utils import (
    handle_cookie_banner as util_handle_cookie_banner,
    handle_intermediate_page as util_handle_intermediate_page,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('energy_label_link_collector.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Directories
DATA_DIR = "energy_label_data"
LINKS_DIR = os.path.join(DATA_DIR, "product_links")
os.makedirs(LINKS_DIR, exist_ok=True)


@dataclass
class ProductLink(ProductLink):
    pass


# Import configurations from the original module
from amazon_config import COUNTRY_CONFIGS, ENERGY_CATEGORIES, CATEGORY_QUERIES


class EnergyLabelLinkCollector:
    """Collector for Amazon product links without formal energy labels"""

    def __init__(self,
                 proxy_manager: Optional[ProxyManager] = None,
                 captcha_solver: Optional[CaptchaSolver] = None,
                 delay_range: tuple = (2.0, 5.0),
                 headless: bool = True):
        self.delay_range = delay_range
        self.proxy_manager = proxy_manager
        self.captcha_solver = captcha_solver
        self.headless = headless
        self.collected_links: Dict[str, List[ProductLink]] = {}  # country -> links
        self.processed_asins: Set[str] = set()
        self.progress_file = os.path.join(LINKS_DIR, "collection_progress.json")
        self.completed_countries: Set[str] = set()

    def load_progress(self) -> Dict[str, any]:
        """Load collection progress from file"""
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    progress = json.load(f)
                    self.completed_countries = set(progress.get('completed_countries', []))
                    logger.info(f"Loaded progress: {len(self.completed_countries)} countries completed")
                    return progress
            except Exception as e:
                logger.error(f"Error loading progress: {str(e)}")
        return {"completed_countries": [], "last_updated": None}

    def save_progress(self, country_key: str = None):
        """Save collection progress to file"""
        if country_key:
            self.completed_countries.add(country_key)

        progress = {
            "completed_countries": list(self.completed_countries),
            "last_updated": datetime.now().isoformat(),
            "total_countries": len(COUNTRY_CONFIGS),
            "remaining_countries": [c for c in COUNTRY_CONFIGS.keys() if c not in self.completed_countries]
        }

        try:
            with open(self.progress_file, 'w', encoding='utf-8') as f:
                json.dump(progress, f, indent=2, ensure_ascii=False)
            logger.debug(f"Progress saved: {len(self.completed_countries)}/{len(COUNTRY_CONFIGS)} countries completed")
        except Exception as e:
            logger.error(f"Error saving progress: {str(e)}")

    def get_existing_links_file(self, country_key: str) -> Optional[str]:
        """Check if a recent links file already exists for a country"""
        import glob
        pattern = os.path.join(LINKS_DIR, f"{country_key}_product_links_*.json")
        files = glob.glob(pattern)

        if files:
            # Get the most recent file
            latest_file = max(files, key=os.path.getmtime)
            # Check if file is from today (within last 24 hours)
            file_time = os.path.getmtime(latest_file)
            current_time = datetime.now().timestamp()
            if current_time - file_time < 86400:  # 24 hours
                return latest_file
        return None

    def is_country_completed(self, country_key: str) -> bool:
        """Check if a country has been completed recently"""
        # Check progress file
        if country_key in self.completed_countries:
            return True

        # Check if recent links file exists
        existing_file = self.get_existing_links_file(country_key)
        if existing_file:
            try:
                with open(existing_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get('total_links', 0) > 0:
                        logger.info(f"Found existing links file for {country_key}: {existing_file}")
                        self.completed_countries.add(country_key)
                        return True
            except Exception as e:
                logger.error(f"Error reading existing file {existing_file}: {str(e)}")

        return False

    def show_status(self):
        """Show current collection status"""
        print("Collection Status")
        print("=" * 50)

        progress = self.load_progress()
        completed = set(progress.get('completed_countries', []))
        all_countries = set(COUNTRY_CONFIGS.keys())
        remaining = all_countries - completed

        print(f"Total countries: {len(all_countries)}")
        print(f"Completed: {len(completed)}")
        print(f"Remaining: {len(remaining)}")
        print()

        if completed:
            print("Completed countries:")
            for country in sorted(completed):
                existing_file = self.get_existing_links_file(country)
                if existing_file:
                    try:
                        with open(existing_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            links_count = data.get('total_links', 0)
                            print(f"  ✓ {country}: {links_count} links")
                    except:
                        print(f"  ✓ {country}: file error")
                else:
                    print(f"  ✓ {country}: completed")
            print()

        if remaining:
            print("Remaining countries:")
            for country in sorted(remaining):
                print(f"  ○ {country}")
            print()

        last_updated = progress.get('last_updated')
        if last_updated:
            print(f"Last updated: {last_updated}")
        print()

    def reset_progress(self):
        """Reset collection progress"""
        try:
            if os.path.exists(self.progress_file):
                os.remove(self.progress_file)
            self.completed_countries.clear()
            print("Progress has been reset successfully.")
        except Exception as e:
            print(f"Error resetting progress: {str(e)}")

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

    async def handle_cookie_banner(self, page: Page) -> bool:
        """Delegate to shared cookie banner handler."""
        return await util_handle_cookie_banner(page)

    async def set_location_by_postcode(self, page: Page, postcode: str, category_url: Optional[str] = None) -> bool:
        """Set the delivery location using a postcode"""
        try:
            await page.wait_for_load_state("networkidle")

            logger.info(f"Looking for location selector to set postcode: {postcode}")

            location_block = await page.query_selector("xpath=//div[@id='nav-global-location-slot']")

            if not location_block and category_url:
                logger.info(f"Location block not found on main page. Navigating to category page")
                category_url_with_lang = self.add_language_param(category_url)
                await page.goto(category_url_with_lang, wait_until="domcontentloaded")
                await self.handle_cookie_banner(page)
                location_block = await page.query_selector("xpath=//div[@id='nav-global-location-slot']")

                if not location_block:
                    logger.warning("Location block not found on category page either")
                    return False

            location_selectors = [
                "xpath=//div[@id='glow-ingress-block']",
                "xpath=//span[@id='nav-global-location-data-modal-action']",
                "xpath=//a[@id='nav-global-location-popover-link']"
            ]

            location_selector = None
            for selector in location_selectors:
                element = await page.query_selector(selector)
                if element:
                    is_visible = await element.is_visible()
                    if is_visible:
                        location_selector = element
                        logger.info(f"Found visible location selector")
                        break

            if not location_selector:
                logger.error("Could not find any visible location selector")
                return False

            await location_selector.click()
            await self.random_delay()

            # Handle postcode input (single or dual field)
            postcode_inputs = await page.query_selector_all("xpath=//input[contains(@id, 'GLUXZipUpdateInput')]")

            if len(postcode_inputs) == 2:
                # Dual field (Sweden)
                logger.info("Detected dual-field postcode input")
                postcode_parts = postcode.strip().split()
                if len(postcode_parts) != 2:
                    if ' ' not in postcode and len(postcode) > 2:
                        midpoint = len(postcode) // 2
                        postcode_parts = [postcode[:midpoint], postcode[midpoint:]]
                    else:
                        postcode_parts = [postcode, ""]

                # Enter first part
                await postcode_inputs[0].click()
                await postcode_inputs[0].fill("")
                for char in postcode_parts[0]:
                    await page.keyboard.type(char)
                    await self.random_delay(0.05, 0.15)

                # Enter second part
                await postcode_inputs[1].click()
                await postcode_inputs[1].fill("")
                for char in postcode_parts[1]:
                    await page.keyboard.type(char)
                    await self.random_delay(0.05, 0.15)

            else:
                # Single field
                zip_input = None
                zip_selectors = [
                    "xpath=//div[@id='GLUXZipInputSection']/div/input",
                    "xpath=//input[@autocomplete='postal-code']",
                    "xpath=//input[@id='GLUXZipUpdateInput']"
                ]

                for selector in zip_selectors:
                    try:
                        element = await page.wait_for_selector(selector, timeout=5000)
                        if element and await element.is_visible():
                            zip_input = element
                            break
                    except:
                        pass

                if not zip_input:
                    logger.error("Could not find zip code input")
                    return False

                await zip_input.click()
                await zip_input.fill("")
                for char in postcode:
                    await page.keyboard.type(char)
                    await self.random_delay(0.05, 0.2)

            # Click apply button
            apply_button = None
            button_selectors = [
                "xpath=//span[@id='GLUXZipUpdate']//input[@type='submit']",
                "xpath=//input[@aria-labelledby='GLUXZipUpdate-announce']",
                "xpath=//span[@id='GLUXZipUpdate']"
            ]

            for selector in button_selectors:
                element = await page.query_selector(selector)
                if element and await element.is_visible():
                    apply_button = element
                    break

            if apply_button:
                await apply_button.click()
                await self.random_delay()

            # Click confirm if present
            confirm_selectors = [
                "xpath=//input[@id='GLUXConfirmClose']",
                "xpath=//button[contains(@class, 'a-button-primary') and contains(text(), 'Done')]",
            ]

            for selector in confirm_selectors:
                confirm_button = await page.query_selector(selector)
                if confirm_button and await confirm_button.is_visible():
                    await confirm_button.click()
                    break

            await self.random_delay(3.0, 4.0)
            logger.info(f"Location set to postcode: {postcode}")
            return True

        except Exception as e:
            logger.error(f"Error setting location: {str(e)}")
            return False

    def add_language_param(self, url: str) -> str:
        """Delegate to shared URL language parameter helper."""
        return add_language_param(url)

    async def check_for_energy_label(self, product_element) -> Tuple[bool, bool]:
        """Check if a product has an energy efficiency label or just energy text"""
        try:
            # Check for formal energy efficiency label
            energy_label = await product_element.query_selector(
                'xpath=.//div[@data-csa-c-content-id="energy-efficiency-label"]'
            )
            has_formal_label = energy_label is not None

            # Check for energy efficiency text
            energy_text = await product_element.query_selector(
                'xpath=.//div[@data-csa-c-type="item"][.//span[contains(normalize-space(.), "Energy Efficiency Class:")]]'
            )
            has_energy_text = energy_text is not None

            return has_formal_label, has_energy_text
        except Exception as e:
            logger.error(f"Error checking for energy label: {str(e)}")
            return False, False

    async def search_category(self, page: Page, category_key: str, domain: str) -> bool:
        """Navigate to a category using search"""
        try:
            # Handle intermediate page first
            if await self.handle_intermediate_page(page, domain):
                logger.info("Handled intermediate page before search")

            # Get search query
            search_query = CATEGORY_QUERIES.get(category_key, {}).get(domain, "")
            if not search_query:
                logger.warning(f"No search query found for {category_key} on {domain}")
                return False

            # Find and use search box - try multiple selectors
            search_box_selectors = [
                "xpath=//input[@id='twotabsearchtextbox']",
                "xpath=//input[@id='nav-bb-search']",
                "xpath=//input[@name='field-keywords']",
                "xpath=//input[@placeholder='Search Amazon']",
                "xpath=//input[contains(@class, 'nav-input')]",
                "xpath=//input[contains(@aria-label, 'Search')]"
            ]

            search_box = None
            for selector in search_box_selectors:
                search_box = await page.query_selector(selector)
                if search_box:
                    logger.debug(f"Found search box with selector: {selector}")
                    break

            if not search_box:
                logger.error("Could not find search box with any selector")
                # Take screenshot for debugging
                try:
                    import time
                    screenshot_path = f"debug_search_box_{domain}_{int(time.time())}.png"
                    await page.screenshot(path=screenshot_path)
                    logger.info(f"Debug screenshot saved: {screenshot_path}")
                except:
                    pass
                return False

            await search_box.click()
            await search_box.fill("")

            for char in search_query:
                await page.keyboard.type(char)
                await self.random_delay(0.05, 0.15)

            await self.random_delay(0.3, 0.8)
            await page.keyboard.press("Enter")

            await page.wait_for_load_state("domcontentloaded")

            # Check for intermediate page after search
            if await self.handle_intermediate_page(page, domain):
                logger.warning("Intermediate page appeared after search")
                return False

            await page.wait_for_selector('xpath=//span[@data-component-type="s-search-results"]', timeout=15000)
            return True

        except Exception as e:
            logger.error(f"Error searching for category {category_key}: {str(e)}")
            return False

    async def collect_product_links(self, page: Page, category_key: str, category_name: str,
                                    country_key: str, domain: str) -> List[ProductLink]:
        """Collect product links from search results"""
        links = []
        current_page = 1
        max_pages = 10  # Limit pages to avoid excessive scraping

        try:
            while current_page <= max_pages:
                logger.info(f"Processing search results page {current_page} for {category_name}")

                # Wait for results
                await page.wait_for_load_state("domcontentloaded")

                # Wait for search results container
                try:
                    await page.wait_for_selector('xpath=//div[contains(@class, "s-main-slot")]', timeout=10000)
                except:
                    logger.warning("Search results container not found")
                    break

                # Find all products
                product_selector = "xpath=//div[contains(@class, 's-main-slot')]//div[@data-component-type='s-search-result']"
                product_elements = await page.query_selector_all(product_selector)

                logger.info(f"Found {len(product_elements)} products on page {current_page}")

                products_without_formal_label = 0

                # Process each product
                for product_element in product_elements:
                    try:
                        # Extract ASIN
                        asin = await product_element.get_attribute("data-asin")
                        if not asin or asin in self.processed_asins:
                            continue

                        # Check for energy label
                        has_formal_label, has_energy_text = await self.check_for_energy_label(product_element)

                        # Skip products with formal energy label
                        if has_formal_label:
                            logger.debug(f"Skipping product {asin} - has formal energy label")
                            self.processed_asins.add(asin)
                            continue

                        # Collect products WITHOUT formal label
                        products_without_formal_label += 1

                        # Find product link
                        link_element = await product_element.query_selector('h2 a')
                        if not link_element:
                            link_element = await product_element.query_selector('a.a-link-normal')

                        if not link_element:
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

                        # Create ProductLink object
                        product_link = ProductLink(
                            asin=asin,
                            url=product_url,
                            has_energy_text=has_energy_text,
                            category=category_name,
                            category_key=category_key,
                            country=country_key,
                            domain=domain
                        )

                        links.append(product_link)
                        self.processed_asins.add(asin)

                        logger.debug(f"Collected link for product {asin} (energy text: {has_energy_text})")

                    except Exception as e:
                        logger.error(f"Error processing product element: {str(e)}")

                logger.info(
                    f"Collected {products_without_formal_label} products without formal labels on page {current_page}")

                # Check for next page
                next_button = await page.query_selector(
                    'xpath=//a[contains(@class, "s-pagination-item s-pagination-next")]')

                if next_button:
                    is_disabled = await next_button.get_attribute("aria-disabled")
                    classes = await next_button.get_attribute("class")

                    if (not is_disabled or is_disabled.lower() != "true") and "s-pagination-disabled" not in (
                            classes or ""):
                        logger.info(f"Going to page {current_page + 1}")

                        try:
                            await next_button.scroll_into_view_if_needed()
                            await self.random_delay(0.3, 0.6)
                            await next_button.click()
                            await page.wait_for_load_state("domcontentloaded")
                            await self.random_delay(1.0, 2.0)
                            current_page += 1
                            continue
                        except Exception as e:
                            logger.error(f"Error navigating to next page: {str(e)}")
                            break
                    else:
                        logger.info("Next button disabled, reached end")
                        break
                else:
                    logger.info("No next button found, reached end")
                    break

        except Exception as e:
            logger.error(f"Error collecting product links: {str(e)}")

        logger.info(f"Collected {len(links)} product links from {current_page} pages")
        return links

    async def collect_country_links(self, country_key: str) -> List[ProductLink]:
        """Collect all product links for a specific country"""
        country_config = COUNTRY_CONFIGS[country_key]
        domain = country_config["domain"]
        locale = country_config["locale"]
        use_postcode = country_config.get("use_postcode", False)
        postcode = country_config.get("postcode", "")

        logger.info(f"Starting link collection for {country_key} ({domain})")
        if use_postcode:
            logger.info(f"Will set location using postcode: {postcode}")

        country_links = []

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

                # Navigate to homepage with English language
                homepage_url = add_language_param(f"https://www.{domain}")
                logger.info(f"Navigating to {homepage_url}")
                await navigate_with_handling(page, homepage_url, domain, wait_until="domcontentloaded")

                # Set location if needed
                if use_postcode and postcode:
                    logger.info(f"Setting location to postcode: {postcode}")
                    location_set = await self.set_location_by_postcode(page, postcode)
                    if not location_set:
                        logger.warning(f"Could not set location for {country_key}")
                    await self.random_delay(1.0, 2.0)

                # Process each category
                for category_key, category_name in ENERGY_CATEGORIES.items():
                    logger.info(f"Processing category: {category_name}")

                    try:
                        # Search for category
                        if await self.search_category(page, category_key, domain):
                            # Collect links from search results
                            category_links = await self.collect_product_links(
                                page, category_key, category_name, country_key, domain
                            )
                            country_links.extend(category_links)
                            logger.info(f"Collected {len(category_links)} links from {category_name}")
                        else:
                            logger.warning(f"Failed to search for {category_name}")

                        # Return to homepage between categories
                        homepage_url_with_lang = add_language_param(homepage_url)
                        await navigate_with_handling(page, homepage_url_with_lang, domain,
                                                     wait_until="domcontentloaded", post_delay=(2.0, 4.0))

                    except Exception as e:
                        logger.error(f"Error processing category {category_name}: {str(e)}")
                        # Try to recover
                        try:
                            await page.goto(self.add_language_param(homepage_url), wait_until="networkidle")
                        except:
                            pass

        except Exception as e:
            logger.error(f"Error collecting links for {country_key}: {str(e)}")

        return country_links

    def save_links(self, country_key: str, links: List[ProductLink]):
        """Save collected links to JSON file"""
        if not links:
            logger.warning(f"No links to save for {country_key}")
            return

        # Create filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(LINKS_DIR, f"{country_key}_product_links_{timestamp}.json")

        # Convert to dictionaries
        links_data = [link.to_dict() for link in links]

        # Save to file
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({
                "country": country_key,
                "collection_timestamp": datetime.now().isoformat(),
                "total_links": len(links_data),
                "links": links_data
            }, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved {len(links)} links to {filename}")

        # Also save a summary
        summary = {
            "country": country_key,
            "total_links": len(links),
            "by_category": {},
            "with_energy_text": sum(1 for link in links if link.has_energy_text),
            "without_energy_info": sum(1 for link in links if not link.has_energy_text)
        }

        for link in links:
            if link.category not in summary["by_category"]:
                summary["by_category"][link.category] = 0
            summary["by_category"][link.category] += 1

        print(f"\n{country_key.upper()} Summary:")
        print(f"  Total links: {summary['total_links']}")
        print(f"  With energy text: {summary['with_energy_text']}")
        print(f"  Without energy info: {summary['without_energy_info']}")
        print("  By category:")
        for cat, count in summary["by_category"].items():
            print(f"    - {cat}: {count}")

    async def collect_all_countries(self, countries: Optional[List[str]] = None, resume: bool = True):
        """Collect links for all or specified countries with resume capability"""
        # Load existing progress
        if resume:
            self.load_progress()

        target_countries = countries or list(COUNTRY_CONFIGS.keys())
        logger.info(f"Starting link collection for {len(target_countries)} countries")

        if resume and self.completed_countries:
            remaining = [c for c in target_countries if c not in self.completed_countries]
            logger.info(f"Resume mode: {len(self.completed_countries)} countries already completed")
            logger.info(f"Remaining countries: {remaining}")
            target_countries = remaining

        if not target_countries:
            logger.info("All countries already completed!")
            return

        failed_countries = []

        for i, country_key in enumerate(target_countries):
            if country_key not in COUNTRY_CONFIGS:
                logger.warning(f"Unknown country: {country_key}")
                continue

            # Skip if already completed (double-check)
            if resume and self.is_country_completed(country_key):
                logger.info(f"Skipping {country_key} - already completed")
                continue

            logger.info(f"Processing country {i + 1}/{len(target_countries)}: {country_key}")

            # Try to collect links with retries
            success = await self.collect_country_with_retry(country_key, max_retries=2)

            if success:
                # Mark as completed
                self.save_progress(country_key)
                logger.info(f"✓ Completed {country_key}")
            else:
                failed_countries.append(country_key)
                logger.error(f"✗ Failed {country_key} after all retries")

            # Delay between countries
            if country_key != target_countries[-1]:
                await asyncio.sleep(5.0)

        # Summary
        if failed_countries:
            logger.warning(f"Failed countries: {failed_countries}")
            logger.info("You can rerun the script to retry failed countries")
        else:
            logger.info("All countries completed successfully!")

    async def collect_country_with_retry(self, country_key: str, max_retries: int = 2) -> bool:
        """Collect links for a country with retry logic"""
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    logger.info(f"Retry attempt {attempt} for {country_key}")
                    await asyncio.sleep(10.0)  # Wait before retry

                # Collect links for this country
                links = await self.collect_country_links(country_key)

                # Store in memory
                self.collected_links[country_key] = links

                # Save to file
                self.save_links(country_key, links)

                logger.info(f"Collected {len(links)} links for {country_key}")
                return True

            except KeyboardInterrupt:
                logger.info("Collection interrupted by user")
                raise
            except Exception as e:
                logger.error(f"Error processing {country_key} (attempt {attempt + 1}): {str(e)}")
                if attempt == max_retries:
                    return False

        return False

    def print_summary(self):
        """Print summary of collected links"""
        print("\n" + "=" * 60)
        print("LINK COLLECTION SUMMARY")
        print("=" * 60)

        total_links = sum(len(links) for links in self.collected_links.values())
        print(f"Total links collected: {total_links}")
        print("-" * 60)

        for country, links in self.collected_links.items():
            if links:
                with_text = sum(1 for link in links if link.has_energy_text)
                without_info = len(links) - with_text

                print(f"\n{country.upper()}:")
                print(f"  Total: {len(links)}")
                print(f"  With energy text: {with_text} ({with_text / len(links) * 100:.1f}%)")
                print(f"  Without energy info: {without_info} ({without_info / len(links) * 100:.1f}%)")

                # Category breakdown
                by_category = {}
                for link in links:
                    if link.category not in by_category:
                        by_category[link.category] = 0
                    by_category[link.category] += 1

                print("  Categories:")
                for cat, count in sorted(by_category.items()):
                    print(f"    - {cat}: {count}")

        print("\n" + "=" * 60)
        print(f"Links saved to: {LINKS_DIR}")
        print("=" * 60)


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Energy Label Link Collector - Module 1')
    parser.add_argument('--countries', type=str,
                        help='Comma-separated country codes (e.g., italy,france)')
    parser.add_argument('--no-headless', action='store_true',
                        help='Show browser window')
    parser.add_argument('--proxy', type=str,
                        help='Single proxy to use')
    parser.add_argument('--no-resume', action='store_true',
                        help='Start fresh without loading previous progress')
    parser.add_argument('--status', action='store_true',
                        help='Show collection status and exit')
    parser.add_argument('--reset', action='store_true',
                        help='Reset progress and start over')
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
    captcha_api_key = os.getenv("CAPTCHA_API_KEY",
                                "CAP-956BF088AFEBDE1D55D75C975171507466CFFDF3C9657C7412145974FF602B9A")
    if captcha_api_key:
        captcha_solver = CaptchaSolver(captcha_api_key)

    # Initialize collector
    collector = EnergyLabelLinkCollector(
        proxy_manager=proxy_manager,
        captcha_solver=captcha_solver,
        headless=not args.no_headless
    )

    # Handle status check
    if args.status:
        collector.show_status()
        return

    # Handle reset
    if args.reset:
        collector.reset_progress()
        print("Progress has been reset. You can now start collection fresh.")
        return

    print("Energy Label Link Collector - Module 1")
    print("=" * 60)
    print("This module will:")
    print("1. Navigate to Amazon marketplaces")
    print("2. Set location using postcodes")
    print("3. Search energy-related categories")
    print("4. Find products WITHOUT formal energy labels")
    print("5. Save product links for processing by Module 2")
    print()
    print(f"Links will be saved to: {LINKS_DIR}")
    print()

    # Show resume info
    resume_mode = not args.no_resume
    if resume_mode:
        progress = collector.load_progress()
        completed = progress.get('completed_countries', [])
        if completed:
            print(f"Resume mode: {len(completed)} countries already completed")
            remaining = [c for c in COUNTRY_CONFIGS.keys() if c not in completed]
            print(f"Remaining: {remaining}")
            print("Use --no-resume to start fresh or --reset to clear progress")
    print()

    try:
        # Collect links
        await collector.collect_all_countries(countries, resume=resume_mode)

        # Print summary
        collector.print_summary()

    except KeyboardInterrupt:
        logger.info("Collection interrupted by user")
        print("\nCollection was interrupted. Progress has been saved.")
        print("You can resume by running the script again (resume is enabled by default).")
        collector.print_summary()
    except Exception as e:
        logger.error(f"Unhandled exception: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
