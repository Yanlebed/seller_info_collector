"""
Amazon Energy Label Brand Scraper

This script scrapes Amazon marketplaces to identify products WITHOUT formal energy efficiency labels
in categories that typically require energy labels.

It specifically:
- SKIPS products with formal energy efficiency labels
- PROCESSES products without formal labels (including those with only energy text)
- Collects brand, seller, and product information

Output files:
- products_without_formal_energy_labels.xlsx: Detailed product information
- brands_without_formal_energy_labels_summary.xlsx: List of brands per marketplace
- brands_without_formal_labels_analysis.xlsx: Brand analysis with product counts
"""

#!/usr/bin/env python3
"""
Amazon Energy Label Brand Scraper

This script scrapes Amazon marketplaces to identify products WITHOUT formal energy efficiency labels
in categories that typically require energy labels.

It specifically:
- SKIPS products with formal energy efficiency labels
- PROCESSES products without formal labels (including those with only energy text)
- Collects brand, seller, and product information
- Handles intermediate pages on Amazon.it, Amazon.es, and Amazon.fr

Output files structure:
energy_label_data/
├── {country}/
│   ├── {country}_products_without_formal_energy_labels.xlsx
│   ├── {country}_brands_summary.xlsx
│   └── {country}_brand_analysis.xlsx
├── all_products_without_formal_energy_labels.xlsx
├── all_brands_without_formal_energy_labels_summary.xlsx
├── all_brands_without_formal_labels_analysis.xlsx
├── overall_country_summary.xlsx
└── overall_category_summary.xlsx

Special handling for:
- Amazon.it: Clicks "Clicca qui per tornare alla home page di Amazon.it" when present
- Amazon.es: Clicks "Seguir comprando" button when present
- Amazon.fr: Clicks "Continuer les achats" button when present

Cookie handling:
- Amazon.it: Clicks button[@aria-label="Rifiuta"]
- Amazon.es, Amazon.nl, Amazon.fr: Clicks button[@id="sp-cc-rejectall-link"]
"""

import asyncio
import logging
import random
import json
import os
import time
import re
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple, Tuple
from dataclasses import dataclass, field

from camoufox.async_api import AsyncCamoufox
from playwright.async_api import Page

from proxy_manager import ProxyManager, ProxyStats
from captcha_solver import CaptchaSolver

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('energy_label_scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Directories
SCREENSHOTS_DIR = "screenshots_energy"
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

DATA_DIR = "energy_label_data"
os.makedirs(DATA_DIR, exist_ok=True)

COOKIES_DIR = "cookies_energy"
os.makedirs(COOKIES_DIR, exist_ok=True)

# Data structures for energy label scraping
@dataclass
class ProductInfo:
    """Structure to hold product information"""
    amazon_host: str
    brand: str
    product_name: str
    product_url: str
    seller_name: str
    seller_url: str
    has_energy_text: bool  # True if has energy text but no formal label, False if no energy info at all
    category: str
    asin: str
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> dict:
        return {
            "amazon_host": self.amazon_host,
            "brand": self.brand,
            "product_name": self.product_name,
            "product_url": self.product_url,
            "seller_name": self.seller_name,
            "seller_url": self.seller_url,
            "has_energy_text": self.has_energy_text,
            "category": self.category,
            "asin": self.asin,
            "timestamp": self.timestamp
        }

# Country and category configurations
COUNTRY_CONFIGS = {
    "sweden": {
        "domain": "amazon.se",
        "country_code": "SE",
        "locale": "sv-SE"
    },
    "france": {
        "domain": "amazon.fr",
        "country_code": "FR",
        "locale": "fr-FR",
        "note": "May show intermediate page with 'Continuer les achats' button"
    },
    "italy": {
        "domain": "amazon.it",
        "country_code": "IT",
        "locale": "it-IT",
        "note": "May show intermediate page with 'Clicca qui per tornare alla home page' link"
    },
    "spain": {
        "domain": "amazon.es",
        "country_code": "ES",
        "locale": "es-ES",
        "note": "May show intermediate page with 'Seguir comprando' button"
    },
    "netherlands": {
        "domain": "amazon.nl",
        "country_code": "NL",
        "locale": "nl-NL"
    }
}

# Categories with energy labels
ENERGY_CATEGORIES = {
    "light_sources": "Light Sources",
    "domestic_ovens": "Domestic Ovens",
    "range_hoods": "Range Hoods",
    "dishwashers": "Household Dishwashers",
    "washing_machines": "Household Washing Machines",
    "washing_dryers": "Household Washing Dryers",
    "tumble_dryers": "Tumble Dryers",
    "fridges_freezers": "Fridges and Freezers",
    "commercial_refrigerators": "Commercial Refrigerators",
    "professional_refrigerated_cabinets": "Professional Refrigerated Storage Cabinets",
    "air_conditioners": "Air Conditioners and Comfort Fans",
    "space_heaters": "Local Space Heaters",
    "ventilation_units": "Ventilation Units",
    "solid_fuel_boilers": "Solid Fuel Boilers",
    "water_heaters": "Water Heaters",
    "electronic_displays": "Electronic Displays",
    "smartphones_tablets": "Smartphones and Tablets",
    "tires": "Tires"
}

# Category search queries for each marketplace
CATEGORY_QUERIES = {
    "light_sources": {
        "amazon.se": "ljuskällor",
        "amazon.fr": "sources lumineuses",
        "amazon.it": "sorgenti luminose",
        "amazon.es": "fuentes de luz",
        "amazon.nl": "lichtbronnen"
    },
    "domestic_ovens": {
        "amazon.se": "ugnar",
        "amazon.fr": "fours domestiques",
        "amazon.it": "forni domestici",
        "amazon.es": "hornos domésticos",
        "amazon.nl": "ovens"
    },
    "range_hoods": {
        "amazon.se": "köksfläktar",
        "amazon.fr": "hottes de cuisine",
        "amazon.it": "cappe da cucina",
        "amazon.es": "campanas extractoras",
        "amazon.nl": "afzuigkappen"
    },
    "dishwashers": {
        "amazon.se": "diskmaskiner",
        "amazon.fr": "lave-vaisselle",
        "amazon.it": "lavastoviglie",
        "amazon.es": "lavavajillas",
        "amazon.nl": "vaatwassers"
    },
    "washing_machines": {
        "amazon.se": "tvättmaskiner",
        "amazon.fr": "machines à laver",
        "amazon.it": "lavatrici",
        "amazon.es": "lavadoras",
        "amazon.nl": "wasmachines"
    },
    "washing_dryers": {
        "amazon.se": "torktumlare",
        "amazon.fr": "sèche-linge",
        "amazon.it": "asciugatrici",
        "amazon.es": "secadoras",
        "amazon.nl": "wasdrogers"
    },
    "tumble_dryers": {
        "amazon.se": "torktumlare",
        "amazon.fr": "sèche-linge tambour",
        "amazon.it": "asciugatrici a tamburo",
        "amazon.es": "secadoras de tambor",
        "amazon.nl": "trommel drogers"
    },
    "fridges_freezers": {
        "amazon.se": "kylskåp frysar",
        "amazon.fr": "réfrigérateurs congélateurs",
        "amazon.it": "frigoriferi congelatori",
        "amazon.es": "frigoríficos congeladores",
        "amazon.nl": "koelkasten vriezers"
    },
    "air_conditioners": {
        "amazon.se": "luftkonditionering",
        "amazon.fr": "climatiseurs",
        "amazon.it": "condizionatori",
        "amazon.es": "aires acondicionados",
        "amazon.nl": "airconditioners"
    },
    "water_heaters": {
        "amazon.se": "varmvattenberedare",
        "amazon.fr": "chauffe-eau",
        "amazon.it": "scaldacqua",
        "amazon.es": "calentadores de agua",
        "amazon.nl": "boilers"
    },
    "electronic_displays": {
        "amazon.se": "bildskärmar",
        "amazon.fr": "écrans électroniques",
        "amazon.it": "display elettronici",
        "amazon.es": "pantallas electrónicas",
        "amazon.nl": "elektronische displays"
    },
    "smartphones_tablets": {
        "amazon.se": "smartphones surfplattor",
        "amazon.fr": "smartphones tablettes",
        "amazon.it": "smartphone tablet",
        "amazon.es": "smartphones tablets",
        "amazon.nl": "smartphones tablets"
    },
    "tires": {
        "amazon.se": "däck",
        "amazon.fr": "pneus",
        "amazon.it": "pneumatici",
        "amazon.es": "neumáticos",
        "amazon.nl": "banden"
    }
}

class EnergyLabelScraper:
    """
    Scraper for Amazon products WITHOUT formal energy efficiency labels.

    This scraper:
    1. SKIPS products that have formal energy labels (div[@data-csa-c-content-id="energy-efficiency-label"])
    2. PROCESSES products without formal labels, including:
       - Products with energy text only (Energy Efficiency Class: text without formal label)
       - Products with no energy information at all

    The goal is to identify brands selling products that should have energy labels but don't.

    Results are saved:
    - Per country in separate subdirectories
    - Overall summaries for cross-country comparison
    """
    def __init__(self,
                 proxy_manager: Optional[ProxyManager] = None,
                 captcha_solver: Optional[CaptchaSolver] = None,
                 delay_range: tuple = (2.0, 5.0),
                 headless: bool = True):
        """
        Initialize the Energy Label scraper
        """
        self.delay_range = delay_range
        self.proxy_manager = proxy_manager
        self.captcha_solver = captcha_solver
        self.headless = headless
        self.products_data: List[ProductInfo] = []
        self.processed_products: Set[str] = set()  # Set of processed ASINs
        self.brands_found: Dict[str, Set[str]] = {}  # Dict of host -> set of brands

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
        """
        Handle intermediate pages that appear on some Amazon domains.

        Amazon.it sometimes shows a page with "Clicca qui per tornare alla home page di Amazon.it"
        Amazon.es sometimes shows a page with "Seguir comprando" button
        Amazon.fr sometimes shows a page with "Continuer les achats" button

        These pages appear randomly and need to be clicked through to reach the actual site.

        Args:
            page: Playwright page object
            domain: Amazon domain (e.g., "amazon.it", "amazon.es", "amazon.fr")

        Returns:
            bool: True if intermediate page was handled, False if not found
        """
        try:
            # Amazon.it intermediate page
            if domain == "amazon.it":
                # Check for the "Click here to return to Amazon.it homepage" link
                it_button = await page.query_selector(
                    'xpath=//a[contains(text(), "Clicca qui per tornare alla home page di Amazon.it")]'
                )
                alternative_it_button = await page.query_selector(
                    'xpath=//button[@alt="Continua con gli acquisti"]'
                )
                final_it_button = it_button or alternative_it_button
                if final_it_button:
                    logger.info("Found Amazon.it intermediate page, clicking to go to homepage")
                    await final_it_button.click()
                    await page.wait_for_load_state("networkidle")
                    await self.random_delay(1.0, 2.0)
                    return True

            # Amazon.es intermediate page
            elif domain == "amazon.es":
                # Check for the "Continue shopping" button
                es_button = await page.query_selector('xpath=//button[@alt="Seguir comprando"]')
                if es_button:
                    logger.info("Found Amazon.es intermediate page, clicking to continue")
                    await es_button.click()
                    await page.wait_for_load_state("networkidle")
                    await self.random_delay(1.0, 2.0)
                    return True

            # Amazon.fr intermediate page
            elif domain == "amazon.fr":
                # Check for the "Continue shopping" button in French
                fr_button = await page.query_selector('xpath=//button[@alt="Continuer les achats"]')
                if fr_button:
                    logger.info("Found Amazon.fr intermediate page, clicking to continue")
                    await fr_button.click()
                    await page.wait_for_load_state("networkidle")
                    await self.random_delay(1.0, 2.0)
                    return True

            return False

        except Exception as e:
            logger.error(f"Error handling intermediate page: {str(e)}")
            return False
        """Handle cookie consent banner"""
        try:
            decline_selectors = [
                "xpath=//button[@aria-label='Decline']",
                "xpath=//input[@id='sp-cc-rejectall-link']",
                "xpath=//a[@id='sp-cc-rejectall-link']",
                "xpath=//button[contains(text(), 'Reject all')]",
                "xpath=//button[contains(text(), 'Decline')]"
            ]

            for selector in decline_selectors:
                decline_button = await page.query_selector(selector)
                if decline_button:
                    is_visible = await decline_button.is_visible()
                    if is_visible:
                        logger.info(f"Found cookie decline button, clicking it")
                        await decline_button.click()
                        await self.random_delay(0.5, 1.0)
                        return True

            return True
        except Exception as e:
            logger.error(f"Error handling cookie banner: {str(e)}")
            return False

    async def check_for_energy_label(self, product_element) -> Tuple[bool, bool]:
        """
        Check if a product has an energy efficiency label or just energy text

        Args:
            product_element: The product element from search results

        Returns:
            tuple: (has_formal_label, has_energy_text)
        """
        try:
            # Check for formal energy efficiency label element
            energy_label = await product_element.query_selector(
                'xpath=.//div[@data-csa-c-content-id="energy-efficiency-label"]'
            )
            has_formal_label = energy_label is not None

            # Check for energy efficiency text (without formal label)
            energy_text = await product_element.query_selector(
                'xpath=.//div[@data-csa-c-type="item"][.//span[contains(normalize-space(.), "Energy Efficiency Class:")]]'
            )
            has_energy_text = energy_text is not None

            return has_formal_label, has_energy_text
        except Exception as e:
            logger.error(f"Error checking for energy label: {str(e)}")
            return False, False

    async def extract_brand_from_product_page(self, page: Page) -> str:
        """Extract brand from product details table"""
        try:
            # Primary selector for brand in product details table
            brand_selectors = [
                'xpath=//table[@class="a-keyvalue prodDetTable"]/tbody/tr[th[contains(text(), "Brand")]]/td',
                'xpath=//table[@class="a-keyvalue prodDetTable"]//tr[th[contains(text(), "Marque")]]/td',  # French
                'xpath=//table[@class="a-keyvalue prodDetTable"]//tr[th[contains(text(), "Marca")]]/td',   # Spanish/Italian
                'xpath=//table[@class="a-keyvalue prodDetTable"]//tr[th[contains(text(), "Merk")]]/td',    # Dutch
                'xpath=//table[@class="a-keyvalue prodDetTable"]//tr[th[contains(text(), "Märke")]]/td',   # Swedish
                # Alternative selectors
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

    async def extract_product_info(self, page: Page, asin: str, has_energy_text: bool,
                                 category: str, domain: str) -> Optional[ProductInfo]:
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

            # Extract seller information - Enhanced extraction logic
            seller_name = "Unknown"
            seller_url = ""

            # Multiple selectors for seller information
            seller_selectors = [
                "xpath=//a[@id='sellerProfileTriggerId']",
                "xpath=//div[@id='merchant-info']//a[contains(@href, '/sp?seller=')]",
                "xpath=//div[@data-csa-c-slot-id='odf-feature-text-desktop-merchant-info']//a[contains(@href, '/sp?seller=')]",
                "xpath=//span[contains(text(), 'Sold by')]/../a",
                "xpath=//span[contains(text(), 'Vendu par')]/../a",  # French
                "xpath=//span[contains(text(), 'Venduto da')]/../a",  # Italian
                "xpath=//span[contains(text(), 'Vendido por')]/../a",  # Spanish
                "xpath=//span[contains(text(), 'Verkocht door')]/../a",  # Dutch
                "xpath=//span[contains(text(), 'Såld av')]/../a"  # Swedish
            ]

            seller_found = False
            for selector in seller_selectors:
                seller_element = await page.query_selector(selector)
                if seller_element:
                    # Extract seller name
                    seller_text = await seller_element.text_content()
                    if seller_text:
                        seller_name = seller_text.strip()

                    # Extract seller URL
                    href = await seller_element.get_attribute("href")
                    if href:
                        if not href.startswith("http"):
                            seller_url = f"https://www.{domain}{href}"
                        else:
                            seller_url = href

                        # Extract seller ID from URL
                        seller_id_match = re.search(r'seller=([A-Z0-9]+)', href)
                        if seller_id_match:
                            seller_id = seller_id_match.group(1)
                            if not seller_url or "/gp/" in seller_url:
                                # Construct proper seller URL
                                seller_url = f"https://www.{domain}/sp?seller={seller_id}"

                        seller_found = True
                        logger.info(f"Found seller: {seller_name} - {seller_url}")
                        break

            # If no seller found in links, check for "Ships from and sold by Amazon"
            if not seller_found:
                amazon_seller_selectors = [
                    "xpath=//div[@id='merchant-info'][contains(text(), 'Amazon')]",
                    "xpath=//span[contains(text(), 'Ships from and sold by Amazon')]",
                    "xpath=//span[contains(text(), 'Expédié et vendu par Amazon')]",  # French
                    "xpath=//span[contains(text(), 'Spedito e venduto da Amazon')]",  # Italian
                    "xpath=//span[contains(text(), 'Enviado y vendido por Amazon')]",  # Spanish
                    "xpath=//span[contains(text(), 'Verzonden en verkocht door Amazon')]",  # Dutch
                    "xpath=//span[contains(text(), 'Skickas från och säljs av Amazon')]"  # Swedish
                ]

                for selector in amazon_seller_selectors:
                    amazon_element = await page.query_selector(selector)
                    if amazon_element:
                        seller_name = "Amazon"
                        seller_url = f"https://www.{domain}"
                        logger.info("Product sold by Amazon")
                        break

            # Create product info object
            product_info = ProductInfo(
                amazon_host=f"www.{domain}",
                brand=brand,
                product_name=product_name,
                product_url=page.url,
                seller_name=seller_name,
                seller_url=seller_url,
                has_energy_text=has_energy_text,
                category=category,
                asin=asin
            )

            return product_info

        except Exception as e:
            logger.error(f"Error extracting product info for ASIN {asin}: {str(e)}")
            return None

    async def search_category(self, page: Page, category_key: str, domain: str) -> bool:
        """Navigate to a category using search"""
        try:
            # Check for intermediate page before searching
            if await self.handle_intermediate_page(page, domain):
                logger.info("Handled intermediate page before search")

            # Get the search query for this category and domain
            search_query = CATEGORY_QUERIES.get(category_key, {}).get(domain, "")
            if not search_query:
                logger.warning(f"No search query found for {category_key} on {domain}")
                return False

            # Find search box
            search_box = await page.query_selector("xpath=//input[@id='twotabsearchtextbox']")
            if not search_box:
                logger.error("Could not find search box")
                return False

            # Click and clear search box
            await search_box.click()
            await search_box.fill("")
            await self.random_delay(0.2, 0.4)

            # Type search query
            for char in search_query:
                await page.keyboard.type(char)
                await self.random_delay(0.05, 0.15)

            await self.random_delay(0.3, 0.8)

            # Press Enter
            await page.keyboard.press("Enter")

            # Wait for search results
            await page.wait_for_load_state("domcontentloaded")

            # Check if we landed on an intermediate page after search
            if await self.handle_intermediate_page(page, domain):
                logger.warning("Intermediate page appeared after search, may need to search again")
                return False

            await page.wait_for_selector('xpath=//span[@data-component-type="s-search-results"]', timeout=15000)

            return True

        except Exception as e:
            logger.error(f"Error searching for category {category_key}: {str(e)}")
            return False

    async def process_search_results(self, page: Page, category: str, domain: str) -> List[ProductInfo]:
        """Process search results and extract product information"""
        products = []
        current_page = 1

        try:
            while True:
                logger.info(f"Processing search results page {current_page} for {category}")

                # Wait for results to load
                await page.wait_for_load_state("networkidle")

                # Find all products on the page
                product_selector = "xpath=//div[contains(@class, 's-main-slot')]//div[@data-component-type='s-search-result']"
                product_elements = await page.query_selector_all(product_selector)

                logger.info(f"Found {len(product_elements)} products on page {current_page}")

                # Process each product
                for product_element in product_elements:
                    try:
                        # Extract ASIN
                        asin = await product_element.get_attribute("data-asin")
                        if not asin or asin in self.processed_products:
                            continue

                        # Check for energy label in search results
                        has_formal_label, has_energy_text = await self.check_for_energy_label(product_element)

                        # SKIP products with formal energy label
                        if has_formal_label:
                            logger.info(f"Skipping product {asin} - has formal energy label")
                            self.processed_products.add(asin)  # Mark as processed to avoid checking again
                            continue

                        # Process products WITHOUT formal label (includes those with energy text or no energy info)
                        logger.info(f"Processing product {asin} - No formal label (has energy text: {has_energy_text})")

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

                        # Navigate to product page
                        await page.goto(product_url, wait_until="domcontentloaded")

                        # Wait for product title
                        await page.wait_for_selector("xpath=//span[@id='productTitle']", timeout=10000)
                        await self.random_delay()

                        # Extract product information
                        product_info = await self.extract_product_info(
                            page, asin, has_energy_text, category, domain
                        )

                        if product_info:
                            products.append(product_info)
                            self.processed_products.add(asin)

                            # Track brands by host
                            if domain not in self.brands_found:
                                self.brands_found[domain] = set()
                            self.brands_found[domain].add(product_info.brand)

                            logger.info(f"Extracted info for {product_info.brand} - {product_info.product_name[:50]}...")

                        # Navigate back to search results
                        await page.go_back(wait_until="domcontentloaded")

                        # Check if we landed on an intermediate page
                        if await self.handle_intermediate_page(page, domain):
                            # If we handled an intermediate page, we might need to navigate back to search
                            logger.warning("Intermediate page appeared when going back, may need to re-navigate")

                        await self.random_delay(1.0, 2.0)

                    except Exception as e:
                        logger.error(f"Error processing product: {str(e)}")
                        # Try to return to search results
                        try:
                            await page.go_back(wait_until="domcontentloaded")
                            # Check for intermediate page
                            await self.handle_intermediate_page(page, domain)
                        except:
                            pass

                # Check for next page button with specific selector
                next_button = await page.query_selector('xpath=//a[contains(@class, "s-pagination-item s-pagination-next")]')

                if next_button:
                    # Check if the button is not disabled
                    is_disabled = await next_button.get_attribute("aria-disabled")
                    classes = await next_button.get_attribute("class")

                    # Check if button is actually clickable
                    if (not is_disabled or is_disabled.lower() != "true") and "s-pagination-disabled" not in (classes or ""):
                        logger.info(f"Navigating to page {current_page + 1}")

                        try:
                            # Scroll to the button first
                            await next_button.scroll_into_view_if_needed()
                            await self.random_delay(0.3, 0.6)

                            # Click the button
                            await next_button.click()

                            # Wait for new page to load
                            await page.wait_for_load_state("networkidle")
                            await self.random_delay(1.0, 2.0)

                            current_page += 1
                            continue
                        except Exception as e:
                            logger.error(f"Error clicking next page button: {str(e)}")
                            break
                    else:
                        logger.info("Next page button is disabled, reached end of results")
                        break
                else:
                    logger.info("No next page button found, reached end of results")
                    break

        except Exception as e:
            logger.error(f"Error processing search results: {str(e)}")

        logger.info(f"Processed {len(products)} products (without formal energy labels) across {current_page} pages")
        return products

    async def scrape_country(self, country_key: str) -> List[ProductInfo]:
        """Scrape all categories for a specific country"""
        country_config = COUNTRY_CONFIGS[country_key]
        domain = country_config["domain"]
        locale = country_config["locale"]

        logger.info(f"Starting scrape for {country_key} ({domain})")

        country_products = []

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

                # Navigate to homepage
                homepage_url = f"https://www.{domain}"
                logger.info(f"Navigating to {homepage_url}")
                await page.goto(homepage_url, wait_until="networkidle")

                # Handle intermediate page if present (Amazon.it and Amazon.es)
                await self.handle_intermediate_page(page, domain)

                # Handle cookie banner
                await self.handle_cookie_banner(page)
                await self.random_delay()

                # Process each category
                for category_key, category_name in ENERGY_CATEGORIES.items():
                    logger.info(f"Processing category: {category_name}")

                    try:
                        # Search for category
                        if await self.search_category(page, category_key, domain):
                            # Process search results
                            category_products = await self.process_search_results(
                                page, category_name, domain
                            )
                            country_products.extend(category_products)
                            logger.info(f"Found {len(category_products)} products in {category_name}")
                        else:
                            logger.warning(f"Failed to search for {category_name}")

                        # Return to homepage between categories
                        await page.goto(homepage_url, wait_until="networkidle")

                        # Handle intermediate page again if it appears
                        await self.handle_intermediate_page(page, domain)

                        await self.random_delay(2.0, 4.0)

                    except Exception as e:
                        logger.error(f"Error processing category {category_name}: {str(e)}")
                        # Try to recover by going back to homepage
                        try:
                            await page.goto(homepage_url, wait_until="networkidle")
                        except:
                            pass

        except Exception as e:
            logger.error(f"Error scraping {country_key}: {str(e)}")

        return country_products

    async def scrape_all_countries(self):
        """Scrape all configured countries"""
        logger.info(f"Starting energy label scraping for {len(COUNTRY_CONFIGS)} countries")
        logger.info("Will process only products WITHOUT formal energy efficiency labels")

        for country_key in COUNTRY_CONFIGS:
            try:
                products = await self.scrape_country(country_key)
                self.products_data.extend(products)

                logger.info(f"Completed {country_key}: Found {len(products)} products without formal energy labels")

            except Exception as e:
                logger.error(f"Error scraping {country_key}: {str(e)}")

        # Add these two methods to your EnergyLabelScraper class in energy_label_scraper.py

    def save_brand_summary(self):
        """Save overall brand summary across all countries"""
        try:
            import pandas as pd

            # Create summary data
            summary_data = []
            for host, brands in self.brands_found.items():
                if brands:
                    summary_data.append({
                        "amazon_host": f"www.{host}",
                        "brands": ", ".join(sorted(brands)),
                        "brand_count": len(brands)
                    })

            # Create DataFrame
            df = pd.DataFrame(summary_data)

            # Save to Excel
            filename = os.path.join(DATA_DIR, "all_brands_without_formal_energy_labels_summary.xlsx")
            df.to_excel(filename, index=False)

            logger.info(f"Saved brand summary for {len(summary_data)} hosts to {filename}")

            # Also create a detailed brand analysis across all countries
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

            # Save detailed brand analysis
            if brand_analysis:
                df_analysis = pd.DataFrame(brand_analysis)
                df_analysis = df_analysis.sort_values(['amazon_host', 'brand'])

                analysis_filename = os.path.join(DATA_DIR, "all_brands_without_formal_labels_analysis.xlsx")
                df_analysis.to_excel(analysis_filename, index=False)
                logger.info(f"Saved detailed brand analysis to {analysis_filename}")

        except ImportError:
            logger.error("pandas not installed, saving as JSON instead")
            filename = os.path.join(DATA_DIR, "all_brands_without_formal_energy_labels_summary.json")
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.brands_found, f, indent=2, ensure_ascii=False)

    def save_overall_summary(self):
        """Save an overall summary of results across all countries"""
        try:
            import pandas as pd

            # Create summary by country
            country_summary = []
            for country_key in COUNTRY_CONFIGS:
                country_products = [p for p in self.products_data if
                                    p.amazon_host.endswith(COUNTRY_CONFIGS[country_key]['domain'])]
                if country_products:
                    brands = set(p.brand for p in country_products)
                    products_with_text = sum(1 for p in country_products if p.has_energy_text)
                    products_without_info = len(country_products) - products_with_text

                    country_summary.append({
                        'country': country_key,
                        'domain': COUNTRY_CONFIGS[country_key]['domain'],
                        'total_products': len(country_products),
                        'unique_brands': len(brands),
                        'products_with_energy_text': products_with_text,
                        'products_without_any_info': products_without_info,
                        'percentage_with_text': round(products_with_text / len(country_products) * 100,
                                                      1) if country_products else 0
                    })

            # Save country summary
            if country_summary:
                df_summary = pd.DataFrame(country_summary)
                summary_file = os.path.join(DATA_DIR, "overall_country_summary.xlsx")
                df_summary.to_excel(summary_file, index=False)
                logger.info(f"Saved overall country summary to {summary_file}")

            # Create category summary across all countries
            category_summary = {}
            for product in self.products_data:
                cat = product.category
                if cat not in category_summary:
                    category_summary[cat] = {
                        'category': cat,
                        'total_products': 0,
                        'products_with_energy_text': 0,
                        'products_without_any_info': 0,
                        'countries': set()
                    }

                category_summary[cat]['total_products'] += 1
                category_summary[cat]['countries'].add(product.amazon_host.split('.')[-1])

                if product.has_energy_text:
                    category_summary[cat]['products_with_energy_text'] += 1
                else:
                    category_summary[cat]['products_without_any_info'] += 1

            # Convert to list
            category_data = []
            for cat, data in category_summary.items():
                data['countries'] = ', '.join(sorted(data['countries']))
                data['percentage_with_text'] = round(
                    data['products_with_energy_text'] / data['total_products'] * 100, 1
                ) if data['total_products'] > 0 else 0
                category_data.append(data)

            # Save category summary
            if category_data:
                df_category = pd.DataFrame(category_data)
                df_category = df_category.sort_values('total_products', ascending=False)
                category_file = os.path.join(DATA_DIR, "overall_category_summary.xlsx")
                df_category.to_excel(category_file, index=False)
                logger.info(f"Saved overall category summary to {category_file}")

        except ImportError:
            logger.error("pandas not installed, saving summaries as JSON instead")
            # Ensure all data is defined for JSON export
            if 'country_summary' not in locals():
                country_summary = []
            if 'category_data' not in locals():
                category_data = []

            # Save as JSON files
            summary_file = os.path.join(DATA_DIR, "overall_summary.json")
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "country_summary": country_summary,
                    "category_summary": category_data
                }, f, indent=2, ensure_ascii=False)

    def save_results(self):
        """Save overall results across all countries"""
        # Save overall detailed results
        self.save_detailed_results()

        # Save overall brand summary
        self.save_brand_summary()

        # Create overall summary report
        self.save_overall_summary()

    def save_detailed_results(self):
        """Save detailed product information to Excel"""
        try:
            import pandas as pd

            # Convert products to dictionaries
            data = [product.to_dict() for product in self.products_data]

            # Create DataFrame
            df = pd.DataFrame(data)

            # Add a column to clarify the energy status
            df['energy_status'] = df['has_energy_text'].apply(
                lambda x: 'Energy text only' if x else 'No energy info'
            )

            # Save to Excel in main directory
            filename = os.path.join(DATA_DIR, "all_products_without_formal_energy_labels.xlsx")
            df.to_excel(filename, index=False)

            logger.info(f"Saved {len(data)} products (all countries) to {filename}")

        except ImportError:
            logger.error("pandas not installed, saving as JSON instead")
            filename = os.path.join(DATA_DIR, "all_products_without_formal_energy_labels.json")
            data = [product.to_dict() for product in self.products_data]
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

    def save_country_results(self, country_key: str, products: List[ProductInfo]):
        """Save results for a specific country"""
        if not products:
            logger.warning(f"No products to save for {country_key}")
            return

        country_config = COUNTRY_CONFIGS.get(country_key, {})
        domain = country_config.get("domain", country_key)

        # Create country-specific subdirectory
        country_dir = os.path.join(DATA_DIR, country_key)
        os.makedirs(country_dir, exist_ok=True)

        logger.info(f"Saving results for {country_key} ({len(products)} products)")

        # Save detailed product information
        self.save_country_detailed_results(country_key, products, country_dir)

        # Save brand summary
        self.save_country_brand_summary(country_key, products, country_dir, domain)

        # Save brand analysis
        self.save_country_brand_analysis(country_key, products, country_dir)

    def save_country_detailed_results(self, country_key: str, products: List[ProductInfo], country_dir: str):
        """Save detailed product information for a specific country"""
        try:
            import pandas as pd

            # Convert products to dictionaries
            data = [product.to_dict() for product in products]

            # Create DataFrame
            df = pd.DataFrame(data)

            # Add a column to clarify the energy status
            df['energy_status'] = df['has_energy_text'].apply(
                lambda x: 'Energy text only' if x else 'No energy info'
            )

            # Save to Excel
            filename = os.path.join(country_dir, f"{country_key}_products_without_formal_energy_labels.xlsx")
            df.to_excel(filename, index=False)

            logger.info(f"Saved {len(data)} products to {filename}")

        except ImportError:
            logger.error("pandas not installed, saving as JSON instead")
            filename = os.path.join(country_dir, f"{country_key}_products_without_formal_energy_labels.json")
            data = [product.to_dict() for product in products]
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

    def save_country_brand_summary(self, country_key: str, products: List[ProductInfo],
                                  country_dir: str, domain: str):
        """Save brand summary for a specific country"""
        try:
            import pandas as pd

            # Extract unique brands
            brands = set(product.brand for product in products)

            # Create summary data
            summary_data = {
                "amazon_host": f"www.{domain}",
                "country": country_key,
                "brands": ", ".join(sorted(brands)),
                "total_brands": len(brands),
                "total_products": len(products)
            }

            # Create DataFrame
            df = pd.DataFrame([summary_data])

            # Save to Excel
            filename = os.path.join(country_dir, f"{country_key}_brands_summary.xlsx")
            df.to_excel(filename, index=False)

            logger.info(f"Saved brand summary to {filename}")

        except ImportError:
            logger.error("pandas not installed, saving as JSON instead")
            filename = os.path.join(country_dir, f"{country_key}_brands_summary.json")
            brands = sorted(set(product.brand for product in products))
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump({"country": country_key, "brands": brands}, f, indent=2, ensure_ascii=False)

    def save_country_brand_analysis(self, country_key: str, products: List[ProductInfo], country_dir: str):
        """Save detailed brand analysis for a specific country"""
        try:
            import pandas as pd

            # Create brand analysis
            brand_analysis = {}
            for product in products:
                brand = product.brand
                if brand not in brand_analysis:
                    brand_analysis[brand] = {
                        'brand': brand,
                        'total_products': 0,
                        'products_with_energy_text': 0,
                        'products_without_any_energy_info': 0,
                        'categories': set()
                    }

                brand_analysis[brand]['total_products'] += 1
                brand_analysis[brand]['categories'].add(product.category)

                if product.has_energy_text:
                    brand_analysis[brand]['products_with_energy_text'] += 1
                else:
                    brand_analysis[brand]['products_without_any_energy_info'] += 1

            # Convert to list and add category count
            analysis_data = []
            for brand, data in brand_analysis.items():
                data['categories'] = ', '.join(sorted(data['categories']))
                data['category_count'] = len(data['categories'].split(', '))
                analysis_data.append(data)

            # Create DataFrame and sort
            df = pd.DataFrame(analysis_data)
            df = df.sort_values(['total_products', 'brand'], ascending=[False, True])

            # Save to Excel
            filename = os.path.join(country_dir, f"{country_key}_brand_analysis.xlsx")
            df.to_excel(filename, index=False)

            logger.info(f"Saved brand analysis to {filename}")

        except ImportError:
            logger.error("pandas not installed, saving as JSON instead")
            # Ensure analysis_data is defined for JSON export
            if 'analysis_data' not in locals():
                analysis_data = []
                for brand, data in brand_analysis.items():
                    categories_list = sorted(data['categories'])
                    analysis_data.append({
                        'brand': data['brand'],
                        'total_products': data['total_products'],
                        'products_with_energy_text': data['products_with_energy_text'],
                        'products_without_any_energy_info': data['products_without_any_energy_info'],
                        'categories': ', '.join(categories_list),
                        'category_count': len(categories_list)
                    })

            filename = os.path.join(country_dir, f"{country_key}_brand_analysis.json")
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(analysis_data, f, indent=2, ensure_ascii=False)
        """Save brand summary by host"""
        try:
            import pandas as pd

            # Create summary data
            summary_data = []
            for host, brands in self.brands_found.items():
                if brands:
                    summary_data.append({
                        "amazon_host": f"www.{host}",
                        "brands": ", ".join(sorted(brands))
                    })

            # Create DataFrame
            df = pd.DataFrame(summary_data)

            # Save to Excel
            filename = os.path.join(DATA_DIR, "brands_without_formal_energy_labels_summary.xlsx")
            df.to_excel(filename, index=False)

            logger.info(f"Saved brand summary for {len(summary_data)} hosts to {filename}")

            # Also create a detailed brand analysis
            brand_analysis = []
            for product in self.products_data:
                brand_key = f"{product.amazon_host}_{product.brand}"
                existing = next((b for b in brand_analysis if b['amazon_host'] == product.amazon_host and b['brand'] == product.brand), None)

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

            # Save detailed brand analysis
            if brand_analysis:
                df_analysis = pd.DataFrame(brand_analysis)
                df_analysis = df_analysis.sort_values(['amazon_host', 'brand'])

                analysis_filename = os.path.join(DATA_DIR, "brands_without_formal_labels_analysis.xlsx")
                df_analysis.to_excel(analysis_filename, index=False)
                logger.info(f"Saved detailed brand analysis to {analysis_filename}")

        except ImportError:
            logger.error("pandas not installed, saving as JSON instead")
            filename = os.path.join(DATA_DIR, "brands_without_formal_energy_labels_summary.json")
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.brands_found, f, indent=2, ensure_ascii=False)

    def print_summary(self):
        """Print summary of results"""
        print("\n" + "=" * 60)
        print("ENERGY LABEL SCRAPING RESULTS SUMMARY")
        print("=" * 60)

        # Overall statistics
        total_products = len(self.products_data)
        products_with_energy_text = sum(1 for p in self.products_data if p.has_energy_text)
        products_without_any_info = total_products - products_with_energy_text

        print(f"Total products analyzed (without formal energy labels): {total_products}")
        print(f"Products with energy text only: {products_with_energy_text} ({products_with_energy_text/max(1,total_products)*100:.1f}%)")
        print(f"Products without any energy info: {products_without_any_info} ({products_without_any_info/max(1,total_products)*100:.1f}%)")
        print("-" * 60)

        # By country breakdown
        by_country = {}
        for product in self.products_data:
            host = product.amazon_host
            if host not in by_country:
                by_country[host] = {"total": 0, "with_energy_text": 0, "brands": set()}
            by_country[host]["total"] += 1
            if product.has_energy_text:
                by_country[host]["with_energy_text"] += 1
            by_country[host]["brands"].add(product.brand)

        for host, stats in by_country.items():
            print(f"\n{host}:")
            print(f"  Total products (no formal label): {stats['total']}")
            print(f"  With energy text only: {stats['with_energy_text']} ({stats['with_energy_text']/max(1,stats['total'])*100:.1f}%)")
            print(f"  Without any energy info: {stats['total'] - stats['with_energy_text']} ({(stats['total'] - stats['with_energy_text'])/max(1,stats['total'])*100:.1f}%)")
            print(f"  Unique brands: {len(stats['brands'])}")

        # By category breakdown
        print("\n" + "-" * 60)
        print("By Category:")
        by_category = {}
        for product in self.products_data:
            cat = product.category
            if cat not in by_category:
                by_category[cat] = {"total": 0, "with_energy_text": 0}
            by_category[cat]["total"] += 1
            if product.has_energy_text:
                by_category[cat]["with_energy_text"] += 1

        for category, stats in sorted(by_category.items()):
            text_pct = stats['with_energy_text']/max(1,stats['total'])*100
            print(f"  {category}: {stats['total']} products, {stats['with_energy_text']} with energy text ({text_pct:.1f}%)")

        print("\n" + "=" * 60)
        print("FILES SAVED:")
        print("=" * 60)
        print("\nCountry-specific files (in energy_label_data/{country}/):")
        for country_key in COUNTRY_CONFIGS:
            country_products = [p for p in self.products_data if p.amazon_host.endswith(COUNTRY_CONFIGS[country_key]['domain'])]
            if country_products:
                print(f"\n{country_key}:")
                print(f"  - {country_key}_products_without_formal_energy_labels.xlsx")
                print(f"  - {country_key}_brands_summary.xlsx")
                print(f"  - {country_key}_brand_analysis.xlsx")

        print("\nOverall summary files (in energy_label_data/):")
        print("  - all_products_without_formal_energy_labels.xlsx")
        print("  - all_brands_without_formal_energy_labels_summary.xlsx")
        print("  - all_brands_without_formal_labels_analysis.xlsx")
        print("  - overall_country_summary.xlsx")
        print("  - overall_category_summary.xlsx")

        print("\n" + "=" * 60)
        print("NOTE: All products with formal energy labels were skipped during scraping.")
        print("This data includes only products WITHOUT formal energy efficiency labels.")
        print("=" * 60)

    async def handle_cookie_banner(self, page: Page) -> bool:
        """
        Handle cookie consent banner

        Cookie decline buttons by country:
        - Italy: button[@aria-label="Rifiuta"]
        - Spain, Netherlands, France: button[@id="sp-cc-rejectall-link"]
        - Others: Various fallback selectors
        """
        try:
            decline_selectors = [
                # Italy specific - Primary selector
                "xpath=//button[@aria-label='Rifiuta']",  # Italian "Reject" button

                # Spain, Netherlands, France specific - Primary selector
                "xpath=//button[@id='sp-cc-rejectall-link']",  # Common for ES, NL, FR

                # Generic and fallback selectors
                "xpath=//button[@aria-label='Decline']",
                "xpath=//input[@id='sp-cc-rejectall-link']",
                "xpath=//a[@id='sp-cc-rejectall-link']",
                "xpath=//span[@id='sp-cc-rejectall-link']",
                "xpath=//button[@data-action='sp-cc-reject-all']",
                "xpath=//button[contains(text(), 'Reject all')]",
                "xpath=//button[contains(text(), 'Decline')]",
                "xpath=//button[contains(text(), 'Reject All')]",
                "xpath=//button[contains(text(), 'Decline All')]",

                # Additional language-specific text selectors as fallback
                "xpath=//button[contains(text(), 'Rifiuta tutto')]",  # Italian
                "xpath=//button[contains(text(), 'Tout refuser')]",  # French
                "xpath=//button[contains(text(), 'Rechazar todo')]",  # Spanish
                "xpath=//button[contains(text(), 'Alles afwijzen')]",  # Dutch
                "xpath=//button[contains(text(), 'Avvisa alla')]"  # Swedish
            ]

            for selector in decline_selectors:
                decline_button = await page.query_selector(selector)
                if decline_button:
                    is_visible = await decline_button.is_visible()
                    if is_visible:
                        logger.info(f"Found cookie decline button with selector: {selector}")
                        await decline_button.click()
                        await self.random_delay(0.5, 1.0)
                        return True

            logger.info("No cookie banner found or already handled")
            return True
        except Exception as e:
            logger.error(f"Error handling cookie banner: {str(e)}")
            return False


async def main():
    """Main entry point"""
    import argparse

    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Amazon Energy Label Brand Scraper')
    parser.add_argument('--no-headless', action='store_true',
                       help='Show browser window (default: headless)')
    parser.add_argument('--proxy', type=str,
                       help='Single proxy to use (format: http://user:pass@host:port)')
    args = parser.parse_args()

    # Set up proxy manager if needed
    proxy_manager = None
    if os.path.exists("proxies.txt") or args.proxy:
        proxy_manager = ProxyManager("proxies.txt")
        if os.path.exists("proxies.txt"):
            await proxy_manager.load_proxies()

        # Add command-line proxy if provided
        if args.proxy:
            from proxy_manager import ProxyStats
            proxy_manager.proxies[args.proxy] = ProxyStats(address=args.proxy)
            proxy_manager.unverified_proxies.append(args.proxy)
            logger.info(f"Added command-line proxy: {args.proxy}")

    # Set up CAPTCHA solver if API key is available
    captcha_solver = None
    captcha_api_key = os.getenv("CAPTCHA_API_KEY", "CAP-956BF088AFEBDE1D55D75C975171507466CFFDF3C9657C7412145974FF602B9A")
    if captcha_api_key:
        captcha_solver = CaptchaSolver(captcha_api_key)
        logger.info("CAPTCHA solver initialized")

    # Initialize scraper
    scraper = EnergyLabelScraper(
        proxy_manager=proxy_manager,
        captcha_solver=captcha_solver,
        headless=not args.no_headless
    )

    print(f"\nScraper initialized. Results will be saved to:")
    print(f"- Country-specific files in: {DATA_DIR}/{{country}}/")
    print(f"- Overall summary files in: {DATA_DIR}/")
    print()

    try:
        # Scrape all countries
        await scraper.scrape_all_countries()

        # Save final results
        scraper.save_results()

        # Print summary
        scraper.print_summary()

    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user")
        scraper.save_results()
    except Exception as e:
        logger.error(f"Unhandled exception: {str(e)}")
        scraper.save_results()


if __name__ == "__main__":
    asyncio.run(main())