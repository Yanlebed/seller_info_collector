import asyncio
import logging
import random
import json
import os
import time
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from dotenv import load_dotenv

from camoufox.async_api import AsyncCamoufox
from playwright.async_api import Page

from proxy_manager import ProxyManager, ProxyStats
from captcha_solver import CaptchaSolver
from models import SellerInfo

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('amazon_seller_scraper.log'),
        logging.StreamHandler()  # Also log to console
    ]
)
logger = logging.getLogger(__name__)

# Directory for saving error screenshots
SCREENSHOTS_DIR = "screenshots"
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

# Directory for saving seller data
DATA_DIR = "seller_data"
os.makedirs(DATA_DIR, exist_ok=True)

COOKIES_DIR = "cookies_cfox_pr"
os.makedirs(COOKIES_DIR, exist_ok=True)
COOKIE_VALIDITY_DAYS = 7  # Consider cookies valid for 7 days

# Country configurations
COUNTRY_CONFIGS = {
    "uk": {
        "domain": "amazon.co.uk",
        "postcode": "SE24 0AA",
        "category_url": "https://www.amazon.co.uk/s?k=fridge+freezer",
        "category_name": "Fridge Freezer",
        "category_query": "fridge freezer",
        "use_postcode": True
    },
    "sweden": {
        "domain": "amazon.se",
        "postcode": "112 19",
        "category_url": "https://www.amazon.se/s?k=elektrisk+v%C3%A4rmare&language=en_GB",
        "category_name": "Electric Heater",
        "category_query": "elektrisk värmare",
        "use_postcode": True
    },
    "finland": {
        "domain": "amazon.com",
        "country_name": "Finland",
        "category_url": "https://www.amazon.com/s?k=smart+home+devices&crid=3TUA8YLJR1PTR&sprefix=smart+home+%2Caps%2C181&ref=nb_sb_ss_ts-doa-p_1_11",
        "category_name": "Smart Home Devices",
        "use_postcode": False
    },
    "estonia": {
        "domain": "amazon.com",
        "country_name": "Estonia",
        "category_url": "https://www.amazon.com/s?k=sofa&rh=n%3A1063306&__mk_pt_BR=%C3%85M%C3%85%C5%BD%C3%95%C3%91&ref=nb_sb_noss",
        "category_name": "Sofa",
        "use_postcode": False
    },
    "portugal": {
        "domain": "amazon.com",
        "country_name": "Portugal",
        "category_url": "https://www.amazon.com/s?k=photo+camera&i=photo&crid=9MUTL9HQL4DN&sprefix=pho%2Cphoto%2C164&ref=nb_sb_ss_ts-doa-p_1_3",
        "category_name": "Photo Camera",
        "use_postcode": False
    }
}


class AmazonSellerScraper:
    def __init__(self,
                 proxy_manager: Optional[ProxyManager] = None,
                 captcha_solver: Optional[CaptchaSolver] = None,
                 delay_range: tuple = (2.0, 5.0),
                 max_products_per_category: int = 10,
                 max_concurrency: int = 3,
                 random_os: bool = True,
                 headless: bool = True):
        """
        Initialize the Amazon seller scraper with Camoufox

        Args:
            proxy_manager: ProxyManager instance for proxy rotation
            captcha_solver: CaptchaSolver instance for handling CAPTCHAs
            delay_range: Random delay range between actions (seconds)
            max_products_per_category: Maximum number of products to process per category
            max_concurrency: Maximum number of concurrent browser instances
            random_os: Whether to randomize the operating system fingerprint
            headless: Run browser in headless mode
        """
        self.delay_range = delay_range
        self.proxy_manager = proxy_manager
        self.captcha_solver = captcha_solver
        self.random_os = random_os
        self.max_products_per_category = max_products_per_category
        self.max_concurrency = max_concurrency
        self.headless = headless
        self.sellers_data: List[SellerInfo] = []
        self.processed_sellers: Set[str] = set()  # To avoid processing the same seller twice
        self.semaphore = asyncio.Semaphore(max_concurrency)  # Control concurrency

    async def random_delay(self, min_factor=1.0, max_factor=1.0):
        """
        Add a random delay to simulate human behavior

        Args:
            min_factor: Minimum multiplier for the base delay range
            max_factor: Maximum multiplier for the base delay range
        """
        min_delay, max_delay = self.delay_range
        factor = random.uniform(min_factor, max_factor)

        # Add some randomness to the delay to mimic human behavior
        # Humans rarely wait exact multiples of a second
        extra_ms = random.randint(0, 300) / 1000  # 0-300ms additional random delay

        delay = random.uniform(min_delay, max_delay) * factor + extra_ms
        await asyncio.sleep(delay)

    async def setup_camoufox(self, country_domain: str, proxy: Optional[str] = None, custom_config=None):
        """
        Initialize Camoufox with appropriate configuration

        Args:
            country_domain: Domain for locale determination
            proxy: Optional proxy server (format: 'http://user:pass@host:port')
            custom_config: Optional custom configuration to override defaults

        Returns:
            AsyncCamoufox instance
        """
        os_options = ["windows", "macos"] if self.random_os else "windows"

        # Map domains to locales
        locale_map = {
            "amazon.co.uk": "en-GB",
            "amazon.se": "sv-SE",  # Swedish locale for amazon.se
            "amazon.com": "en-US",
        }

        # Get locale from map or default
        locale = locale_map.get(country_domain, country_domain.split('.')[-1] if '.' in country_domain else "en-GB")

        # Default configuration
        camoufox_config = {
            "headless": self.headless,
            "os": os_options,
            "locale": locale,
            "geoip": True,  # Enable geolocation spoofing
            "block_webrtc": True,  # Prevent WebRTC leaks
            "humanize": True,  # Enable human-like cursor movements
        }

        # Apply proxy if provided
        if proxy:
            camoufox_config["proxy"] = {
                "server": proxy
            }

        # Apply custom config overrides if provided
        if custom_config and isinstance(custom_config, dict):
            camoufox_config.update(custom_config)
            logger.info(f"Using custom fingerprint config: {custom_config}")

        return AsyncCamoufox(**camoufox_config)

    async def get_cookie_file_path(self, country_code: str, proxy: Optional[str] = None) -> str:
        """
        Get the path to the cookie file for a specific country and proxy

        Args:
            country_code: Country code for the file name
            proxy: Optional proxy server used for these cookies

        Returns:
            Path to the cookie file
        """
        # If proxy is used, include a hash of it in the filename to have proxy-specific cookies
        if proxy:
            import hashlib
            proxy_hash = hashlib.md5(proxy.encode()).hexdigest()[:8]
            return os.path.join(COOKIES_DIR, f"{country_code}_{proxy_hash}_cookies.json")
        else:
            return os.path.join(COOKIES_DIR, f"{country_code}_cookies.json")

    async def save_cookies(self, page: Page, country_code: str, proxy: Optional[str] = None,
                           postcode: str = None) -> bool:
        """
        Save browser cookies to a file

        Args:
            page: Playwright page object
            country_code: Country code for the file name
            proxy: Optional proxy server used to get these cookies
            postcode: Postcode associated with these cookies (optional)

        Returns:
            bool: True if successful
        """
        try:
            # Get cookies from the context
            cookies = await page.context.cookies()

            # Create cookie data structure with metadata
            cookie_data = {
                "cookies": cookies,
                "timestamp": datetime.now().isoformat(),
                "postcode": postcode,
                "country": country_code,
                "proxy": proxy
            }

            # Save to file
            cookie_file = await self.get_cookie_file_path(country_code, proxy)
            with open(cookie_file, 'w', encoding='utf-8') as f:
                json.dump(cookie_data, f, indent=2)

            logger.info(f"Saved {len(cookies)} cookies for {country_code} to {cookie_file}")
            return True

        except Exception as e:
            logger.error(f"Error saving cookies: {str(e)}")
            return False

    async def load_cookies(self, browser, country_code: str, proxy: Optional[str] = None) -> Tuple[
        bool, Optional[str], Optional[List]]:
        """
        Load cookies from file into browser context

        Args:
            browser: Browser object to load cookies into
            country_code: Country code to load cookies for
            proxy: Optional proxy server to load specific cookies for

        Returns:
            tuple: (success, postcode, cookies)
        """
        try:
            cookie_file = await self.get_cookie_file_path(country_code, proxy)

            # Check if cookie file exists
            if not os.path.exists(cookie_file):
                logger.info(f"No cookie file found for {country_code} with proxy {proxy}")
                return False, None, None

            # Read cookie file
            with open(cookie_file, 'r', encoding='utf-8') as f:
                cookie_data = json.load(f)

            # Check cookie timestamp for validity
            saved_time = datetime.fromisoformat(cookie_data.get("timestamp", "2000-01-01T00:00:00"))
            if (datetime.now() - saved_time) > timedelta(days=COOKIE_VALIDITY_DAYS):
                logger.info(
                    f"Cookies for {country_code} are older than {COOKIE_VALIDITY_DAYS} days, considering invalid")
                return False, None, None

            # Extract cookies and postcode
            cookies = cookie_data.get("cookies", [])
            postcode = cookie_data.get("postcode")

            if not cookies:
                logger.warning(f"No cookies found in file for {country_code}")
                return False, None, None

            # Return cookies for later use
            return True, postcode, cookies

        except Exception as e:
            logger.error(f"Error loading cookies: {str(e)}")
            return False, None, None

    async def verify_location(self, page: Page, postcode: str) -> bool:
        """
        Verify if the current page reflects the expected location without clicking

        Args:
            page: Playwright page object
            postcode: Expected postcode to verify

        Returns:
            bool: True if location matches
        """
        try:
            # Wait for page to load
            await page.wait_for_load_state("networkidle")

            # Extract the location text from the delivery location element without clicking
            location_text = ""
            location_element = await page.query_selector(
                "//div[@id='glow-ingress-block']/span[@id='glow-ingress-line2']")

            if location_element:
                location_text = await location_element.text_content()
                location_text = location_text.strip()
                logger.info(f"Found location text: '{location_text}'")

            if not location_text:
                # Try alternative selectors if the main one didn't work
                alt_selectors = [
                    "//div[@id='glow-ingress-block']",
                    "//span[contains(@class, 'glow-ingress-line2')]",
                    "//*[contains(@id, 'nav-global-location')]"
                ]

                for selector in alt_selectors:
                    element = await page.query_selector(selector)
                    if element:
                        text = await element.text_content()
                        if text and text.strip():
                            location_text = text
                            logger.info(f"Found location text from alternative selector: '{location_text}'")
                            break

            if not location_text:
                logger.warning("Could not find any location text on the page")
                return False

            # Split postcode into elements for more flexible matching
            postcode_elements = postcode.replace(" ", " ").split(" ")

            # Check if any of the postcode elements are in the location text
            location_normalized = location_text.lower()
            for element in postcode_elements:
                if element.lower() in location_normalized:
                    logger.info(f"Location verified: Found postcode element '{element}' in '{location_text}'")
                    return True

            # If we're dealing with a numeric-only postcode
            if all(c.isdigit() or c.isspace() for c in postcode):
                # For numeric postcodes, check if the numbers appear in sequence
                postcode_digits = ''.join(c for c in postcode if c.isdigit())
                location_digits = ''.join(c for c in location_text if c.isdigit())

                if postcode_digits in location_digits:
                    logger.info(f"Location verified: Found numeric postcode '{postcode_digits}' in '{location_digits}'")
                    return True

            logger.info(f"Location verification failed - no postcode elements found in '{location_text}'")
            return False

        except Exception as e:
            logger.error(f"Error verifying location: {str(e)}")
            return False

    async def check_content_availability(self, page: Page) -> bool:
        """
        Check if the page shows 'Sorry, content is not available' message

        Args:
            page: Playwright page object

        Returns:
            bool: True if content is available, False if unavailable
        """
        try:
            # Check for the error message
            error_content = await page.query_selector("//div[contains(text(), 'Sorry, content is not available')]")
            if error_content:
                logger.warning("Detected 'Sorry, content is not available' message")

                # Take a screenshot
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = os.path.join(SCREENSHOTS_DIR, f"content_unavailable_{timestamp}.png")
                await page.screenshot(path=screenshot_path)

                return False

            return True
        except Exception as e:
            logger.error(f"Error checking content availability: {str(e)}")
            return True  # Assume content is available in case of error

    async def check_and_handle_cookie_banner(self, page: Page) -> bool:
        """
        Check for cookie consent banner and decline if present

        Args:
            page: Playwright page object

        Returns:
            bool: True if banner was handled or not present, False if error
        """
        try:
            # Amazon-specific cookie decline button selectors
            decline_selectors = [
                "//button[@aria-label='Decline']",
                "//input[@id='sp-cc-rejectall-link']",
                "//a[@id='sp-cc-rejectall-link']",  # Common Amazon cookie decline link
                "//a[contains(@class, 'sp-cc-buttons') and contains(text(), 'Decline')]",
                "//button[contains(text(), 'Reject all')]",
                "//button[contains(text(), 'Decline')]",
                "//button[contains(text(), 'Only accept essential cookies')]"
            ]

            for selector in decline_selectors:
                decline_button = await page.query_selector(selector)
                if decline_button:
                    is_visible = await decline_button.is_visible()
                    if is_visible:
                        logger.info(f"Found cookie decline button ({selector}), clicking it")

                        # Get button position
                        box = await decline_button.bounding_box()
                        if box:
                            # Move mouse to button with slight randomization
                            x_offset = random.uniform(5, box["width"] - 5)
                            y_offset = random.uniform(5, box["height"] - 5)

                            await page.mouse.move(box["x"] + x_offset, box["y"] + y_offset)
                            await self.random_delay(0.2, 0.5)
                            await page.mouse.click(box["x"] + x_offset, box["y"] + y_offset)

                            # Wait for banner to disappear
                            await self.random_delay(0.5, 1.0)
                            return True

            # No cookie banner found or it was already handled
            logger.info("No cookie banner found or it was already handled")
            return True

        except Exception as e:
            logger.error(f"Error handling cookie banner: {str(e)}")
            return False

    async def set_location_by_postcode(self, page: Page, postcode: str) -> bool:
        """
        Set the delivery location using a postcode with human-like interactions

        Args:
            page: Playwright page object
            postcode: Postcode to set

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Wait for the page to load completely
            await page.wait_for_load_state("networkidle")

            # Handle cookie banner if present
            await self.check_and_handle_cookie_banner(page)

            # Check content availability
            if not await self.check_content_availability(page):
                return False

            # Check if location selector exists
            logger.info(f"Looking for location selector to set postcode: {postcode}")

            # Try multiple selectors for the location element
            location_selectors = [
                "//div[@id='glow-ingress-block']",
                "//span[@id='nav-global-location-data-modal-action']",
                "//a[@id='nav-global-location-popover-link']"
            ]

            location_selector = None
            for selector in location_selectors:
                element = await page.query_selector(selector)
                if element:
                    is_visible = await element.is_visible()
                    if is_visible:
                        location_selector = element
                        logger.info(f"Found visible location selector: {selector}")
                        break

            if not location_selector:
                logger.error("Could not find any visible location selector")
                return False

            # Use humanized click with slight randomization
            box = await location_selector.bounding_box()
            x_position = box["x"] + random.uniform(5, box["width"] - 5)
            y_position = box["y"] + random.uniform(5, box["height"] - 5)

            await page.mouse.move(x_position, y_position)
            await self.random_delay(0.2, 0.5)  # Slight pause before clicking
            await page.mouse.click(x_position, y_position)
            await self.random_delay()

            # Check content availability again after clicking
            if not await self.check_content_availability(page):
                return False

            # Wait for the location modal to appear
            # Try multiple selectors for the zip input field
            zip_input = None
            zip_selectors = [
                "//div[@id='GLUXZipInputSection']/div/input",
                "//input[@autocomplete='postal-code']",
                "//input[@id='GLUXZipUpdateInput']"
            ]

            for selector in zip_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=5000)
                    if element:
                        is_visible = await element.is_visible()
                        if is_visible:
                            zip_input = element
                            logger.info(f"Found visible zip input: {selector}")
                            break
                except Exception as e:
                    logger.debug(f"Selector {selector} not found: {str(e)}")

            if not zip_input:
                logger.error("Could not find the zip code input field")
                return False

            # Move mouse to the input field with randomization
            box = await zip_input.bounding_box()
            x_position = box["x"] + random.uniform(5, box["width"] - 5)
            y_position = box["y"] + random.uniform(5, box["height"] - 5)

            await page.mouse.move(x_position, y_position)
            await self.random_delay(0.1, 0.3)
            await page.mouse.click(x_position, y_position)
            await self.random_delay(0.3, 0.7)

            # Clear the field first (just in case)
            await zip_input.fill("")
            await self.random_delay(0.2, 0.4)

            # Type postcode character by character with random delays
            for char in postcode:
                await page.keyboard.type(char)
                await self.random_delay(0.05, 0.2)  # Random delay between keystrokes

            await self.random_delay(0.5, 1.0)  # Slight pause after typing

            # Look for apply/update button with multiple possible selectors
            apply_button = None
            button_selectors = [
                "//span[@id='GLUXZipUpdate']//input[@type='submit']",
                "//input[@aria-labelledby='GLUXZipUpdate-announce']",
                "//span[@id='GLUXZipUpdate']",
                "//input[contains(@class, 'a-button-input') and contains(@aria-labelledby, 'GLUXZipUpdate')]"
            ]

            for selector in button_selectors:
                element = await page.query_selector(selector)
                if element:
                    is_visible = await element.is_visible()
                    if is_visible:
                        apply_button = element
                        logger.info(f"Found visible apply button: {selector}")
                        break

            if not apply_button:
                logger.error("Could not find the apply button")
                return False

            # Move mouse to button with randomization
            button_box = await apply_button.bounding_box()
            x_position = button_box["x"] + random.uniform(5, button_box["width"] - 5)
            y_position = button_box["y"] + random.uniform(5, button_box["height"] - 5)

            await page.mouse.move(x_position, y_position)
            await self.random_delay(0.2, 0.4)
            await page.mouse.click(x_position, y_position)
            await self.random_delay()

            # Check content availability again after clicking apply
            if not await self.check_content_availability(page):
                return False

            # Look for and click confirm button if it appears
            try:
                # Try multiple selectors for the confirm button
                confirm_selectors = [
                    "//div[@class='a-popover-footer']//span[@data-action='GLUXConfirmAction']/input[@id='GLUXConfirmClose']",
                    "//input[@id='GLUXConfirmClose']",
                    "//button[contains(@class, 'a-button-primary') and contains(text(), 'Done')]",
                    "//button[contains(@class, 'a-button-primary') and contains(text(), 'Continue')]"
                ]

                for selector in confirm_selectors:
                    confirm_button = await page.query_selector(selector)
                    if confirm_button:
                        is_visible = await confirm_button.is_visible()
                        if is_visible:
                            # Move mouse to button with randomization
                            conf_box = await confirm_button.bounding_box()
                            x_position = conf_box["x"] + random.uniform(5, conf_box["width"] - 5)
                            y_position = conf_box["y"] + random.uniform(5, conf_box["height"] - 5)

                            await page.mouse.move(x_position, y_position)
                            await self.random_delay(0.2, 0.4)
                            await page.mouse.click(x_position, y_position)
                            logger.info("Clicked on confirmation button")
                            break
            except Exception as e:
                logger.info(f"No confirmation button found or couldn't click it: {str(e)}")

            # Wait for location to update
            await self.random_delay(2.0, 3.0)

            # Verify location was updated by checking various elements
            try:
                location_text = ""
                location_elements = [
                    "//div[@id='glow-ingress-block']",
                    "//span[@id='glow-ingress-line2']"
                ]

                for selector in location_elements:
                    element = await page.query_selector(selector)
                    if element:
                        text = await element.text_content()
                        if text:
                            location_text += text + " "

                location_text = location_text.strip()
                logger.info(f"Location text after update: {location_text}")

                # Check if postcode is in the location text (ignore spaces for comparison)
                postcode_normalized = postcode.replace(" ", "").lower()
                location_normalized = location_text.replace(" ", "").lower()

                if postcode_normalized in location_normalized:
                    logger.info(f"Successfully set location to postcode: {postcode}")
                    return True
                else:
                    # Even if the exact postcode isn't visible, if we got to this point
                    # the location was likely updated successfully
                    logger.info("Location updated but postcode not visible in text")
                    return True

            except Exception as e:
                logger.warning(f"Error verifying location update: {str(e)}")
                # If we got this far without errors, the location was probably set
                return True

        except Exception as e:
            logger.error(f"Error setting location by postcode: {str(e)}")
            return False

    async def select_country_from_dropdown(self, page: Page, country_name: str) -> bool:
        """
        Select a country from the location dropdown

        Args:
            page: Playwright page object
            country_name: Name of the country to select

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Wait for the page to load completely
            await page.wait_for_load_state("networkidle")

            # Check content availability
            if not await self.check_content_availability(page):
                return False

            # Click on location selector
            logger.info(f"Clicking on location selector to select country: {country_name}")
            location_selector = await page.query_selector("//div[@id='glow-ingress-block']")
            if not location_selector:
                logger.warning("Location selector not found, trying alternative selectors")
                location_selector = await page.query_selector("//span[@id='nav-global-location-data-modal-action']")

            if location_selector:
                await location_selector.click()
                await self.random_delay()

                # Check content availability again after clicking
                if not await self.check_content_availability(page):
                    return False

                # Wait for the dropdown selector to appear and click it
                dropdown_selector = await page.wait_for_selector(
                    "//span[@id='GLUXCountryListDropdown']//span[@data-action='a-dropdown-button']",
                    timeout=10000
                )
                if dropdown_selector:
                    await dropdown_selector.click()
                    await self.random_delay()

                    # Check content availability after opening dropdown
                    if not await self.check_content_availability(page):
                        return False

                    # Find the country in the dropdown list
                    country_xpath = f"//ul[@role='listbox']/li/a[contains(text(), '{country_name}')]"
                    country_option = await page.wait_for_selector(country_xpath, timeout=5000)

                    if country_option:
                        # Click the country option
                        await country_option.click()
                        await self.random_delay()

                        # Check content availability after selecting country
                        if not await self.check_content_availability(page):
                            return False

                        # Click "Done" button if it exists
                        done_button = await page.query_selector("//button[contains(@class, 'a-button-primary')]")
                        if done_button:
                            await done_button.click()
                            await self.random_delay(2.0, 3.0)

                        return True
                    else:
                        logger.error(f"Could not find country option: {country_name}")
                        return False
                else:
                    logger.error("Could not find country dropdown selector")
                    return False
            else:
                logger.error("Could not find any location selector")
                return False

        except Exception as e:
            logger.error(f"Error selecting country from dropdown: {str(e)}")
            return False

    async def get_product_links(self, page: Page, max_products: int) -> List[Dict]:
        """
        Get links to individual product pages from search results with human-like interactions

        Args:
            page: Playwright page object
            max_products: Maximum number of products to process

        Returns:
            List of dictionaries with product info (ASIN and URL)
        """
        try:
            # Wait for search results to load
            await page.wait_for_load_state("networkidle")

            # Human-like interaction - simulate scrolling down the page
            await self.human_scroll(page)

            # Wait for the product grid to appear
            await page.wait_for_selector("//div[contains(@class, 's-main-slot')]", timeout=15000)

            # Use the specified XPath selector to find products
            product_selector = "//div[contains(@class, 's-main-slot') and contains(@class, 's-search-results')]//div[contains(@data-component-type, 's-search-result') and not(contains(@class, 'AdHolder'))]"
            products = await page.query_selector_all(product_selector)

            product_links = []
            count = 0

            for product in products[:max_products]:
                try:
                    # Extract the ASIN
                    asin = await product.get_attribute("data-asin")
                    if not asin:
                        continue

                    # Find the product link using a more reliable selector
                    # Try multiple different selectors to find the link
                    link_element = await product.query_selector('a.a-link-normal.s-no-outline')
                    if not link_element:
                        link_element = await product.query_selector('h2 a')
                    if not link_element:
                        link_element = await product.query_selector('.a-link-normal[href*="/dp/"]')

                    if not link_element:
                        continue

                    href = await link_element.get_attribute("href")
                    if href:
                        # Extract full URL
                        if not href.startswith("http"):
                            domain = page.url.split("/")[2]
                            href = f"https://{domain}{href}"

                        product_links.append({
                            "asin": asin,
                            "url": href
                        })
                        count += 1

                        # Simulate looking at the product (hover over it)
                        box = await link_element.bounding_box()
                        if box:
                            await page.mouse.move(
                                box["x"] + box["width"] / 2,
                                box["y"] + box["height"] / 2
                            )
                            await self.random_delay(0.3, 0.8)

                except Exception as e:
                    logger.error(f"Error extracting product link: {str(e)}")

            logger.info(f"Found {len(product_links)} product links")
            return product_links

        except Exception as e:
            logger.error(f"Error getting product links: {str(e)}")
            return []

    async def human_scroll(self, page: Page):
        """Simulate human-like scrolling behavior but only part way down the page"""
        # Get page height
        page_height = await page.evaluate("document.body.scrollHeight")
        viewport_height = await page.evaluate("window.innerHeight")

        # Only scroll about 60% of the way down the page
        max_scroll = min(page_height * 0.6, 2000)  # Don't scroll more than 2000px

        # Scroll down in chunks with variable speed
        current_position = 0

        # Determine a random number of scroll steps (2-4)
        scroll_steps = random.randint(2, 4)
        scroll_points = [random.uniform(0.2, 0.9) * max_scroll for _ in range(scroll_steps)]
        scroll_points.sort()  # Make sure they're in ascending order

        for target in scroll_points:
            # Move to this scroll position
            target_position = int(target)

            # Scroll to the new position
            await page.evaluate(f"window.scrollTo(0, {target_position})")

            # Random pause (longer pauses occasionally to simulate reading)
            if random.random() < 0.3:  # 30% chance of a longer pause
                await self.random_delay(1.0, 2.0)
            else:
                await self.random_delay(0.3, 0.7)

        # Occasionally scroll back up a bit
        if random.random() < 0.5:  # 50% chance to scroll back up
            scroll_up_to = int(max_scroll * random.uniform(0.5, 0.8))
            await page.evaluate(f"window.scrollTo(0, {scroll_up_to})")
            await self.random_delay(0.5, 1.0)

    async def navigate_to_search_category(self, page: Page, search_query: str) -> bool:
        """
        Navigate to a search category with human-like typing

        Args:
            page: Playwright page object
            search_query: Search query to enter

        Returns:
            bool: True if successful
        """
        try:
            # Find search box
            search_box = await page.query_selector("//div[@class='nav-fill']//input[@id='twotabsearchtextbox']")
            if not search_box:
                logger.warning("Search box not found, trying alternative selector")
                search_box = await page.query_selector("//input[@id='twotabsearchtextbox']")

            if not search_box:
                logger.error("Could not find search box")
                return False

            # Move mouse to search box
            box = await search_box.bounding_box()
            await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            await self.random_delay(0.2, 0.5)
            await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)

            # Clear the field (just in case)
            await search_box.fill("")
            await self.random_delay(0.2, 0.4)

            # Type search query character by character with random delays
            for char in search_query:
                await page.keyboard.type(char)
                await self.random_delay(0.05, 0.2)  # Random delay between keystrokes

            await self.random_delay(0.3, 0.8)  # Pause after typing

            # Press Enter
            logger.info("Pressing Enter to search")
            await page.keyboard.press("Enter")

            logger.info("Waiting for search results to load")
            await page.wait_for_selector('xpath=//span[@data-component-type="s-search-results"]', timeout=15000)

            logger.info("Search successful")
            # Wait for search results to load
            await page.wait_for_load_state("networkidle")

            return True

        except Exception as e:
            logger.error(f"Error navigating to search category: {str(e)}")
            return False

    async def get_product_links_with_pagination(self, page: Page, max_products: int, max_pages: int = 3) -> List[Dict]:
        """
        Get links to individual product pages from search results with pagination

        Args:
            page: Playwright page object
            max_products: Maximum number of products to process in total
            max_pages: Maximum number of pages to process

        Returns:
            List of dictionaries with product info (ASIN and URL)
        """
        all_product_links = []
        current_page = 1

        try:
            while len(all_product_links) < max_products and current_page <= max_pages:
                logger.info(f"Processing search results page {current_page}")

                # Wait for search results to load
                await page.wait_for_load_state("networkidle")

                # Human-like interaction - simulate scrolling down the page
                await self.human_scroll(page)

                # Wait for the product grid to appear
                await page.wait_for_selector("//div[contains(@class, 's-main-slot')]", timeout=15000)

                # Use the specified XPath selector to find products
                product_selector = "//div[contains(@class, 's-main-slot') and contains(@class, 's-search-results')]//div[contains(@data-component-type, 's-search-result') and not(contains(@class, 'AdHolder'))]"
                products = await page.query_selector_all(product_selector)

                products_on_page = []

                for product in products:
                    # Stop if we've reached the maximum number of products
                    if len(all_product_links) >= max_products:
                        break

                    try:
                        # Extract the ASIN
                        asin = await product.get_attribute("data-asin")
                        if not asin:
                            continue

                        # Find the product link using a more reliable selector
                        # Try multiple different selectors to find the link
                        link_element = await product.query_selector('a.a-link-normal.s-no-outline')
                        if not link_element:
                            link_element = await product.query_selector('h2 a')
                        if not link_element:
                            link_element = await product.query_selector('.a-link-normal[href*="/dp/"]')

                        if not link_element:
                            continue

                        href = await link_element.get_attribute("href")
                        if href:
                            # Extract full URL
                            if not href.startswith("http"):
                                domain = page.url.split("/")[2]
                                href = f"https://{domain}{href}"

                            products_on_page.append({
                                "asin": asin,
                                "url": href
                            })

                            # # Simulate looking at the product (hover over it)
                            # box = await link_element.bounding_box()
                            # if box:
                            #     await page.mouse.move(
                            #         box["x"] + box["width"] / 2,
                            #         box["y"] + box["height"] / 2
                            #     )
                            #     await self.random_delay(0.3, 0.8)

                    except Exception as e:
                        logger.error(f"Error extracting product link: {str(e)}")

                # Add products from this page to the overall list
                all_product_links.extend(products_on_page)
                logger.info(
                    f"Found {len(products_on_page)} product links on page {current_page}, {len(all_product_links)} total so far")

                # Check if there's a next page button and it's enabled
                next_page_button = await page.query_selector("//a[contains(@class, 's-pagination-next')]")

                if not next_page_button:
                    logger.info("No next page button found, reached the end of search results")
                    break

                # Check if the next button is disabled
                is_disabled = await next_page_button.get_attribute("aria-disabled")
                if is_disabled and is_disabled.lower() == "true":
                    logger.info("Next page button is disabled, reached the end of search results")
                    break

                # Click on the next page button with human-like movement
                logger.info(f"Navigating to search results page {current_page + 1}")

                # Move mouse to the button with randomization
                box = await next_page_button.bounding_box()
                if box:
                    x_position = box["x"] + random.uniform(5, box["width"] - 5)
                    y_position = box["y"] + random.uniform(5, box["height"] - 5)

                    await page.mouse.move(x_position, y_position)
                    await self.random_delay(0.2, 0.5)
                    await page.mouse.click(x_position, y_position)

                    # Wait for the page to load
                    await page.wait_for_load_state("networkidle")

                    # Random delay before processing next page
                    await self.random_delay(1.0, 2.0)

                    current_page += 1
                else:
                    logger.warning("Could not get bounding box for next page button")
                    break

            logger.info(
                f"Completed pagination, processed {current_page} page(s), found {len(all_product_links)} products")
            return all_product_links

        except Exception as e:
            logger.error(f"Error during pagination: {str(e)}")
            return all_product_links

    async def extract_seller_info(self, page: Page, product_asin: str, country: str, category: str, domain: str) -> \
            Optional[SellerInfo]:
        """
        Extract seller information from a product page

        Args:
            page: Playwright page object
            product_asin: ASIN of the product
            country: Country code
            category: Category name
            domain: Amazon domain

        Returns:
            SellerInfo object or None if extraction failed
        """
        try:
            # Check if there's a seller link on the page
            seller_link = await page.query_selector("//a[@id='sellerProfileTriggerId']")
            if not seller_link:
                logger.warning(f"No seller link found for product {product_asin}")
                return None

            # Extract seller ID from the link
            href = await seller_link.get_attribute("href")
            if not href:
                logger.warning(f"Seller link has no href attribute for product {product_asin}")
                return None

            # Extract seller ID from URL
            import re
            seller_id_match = re.search(r'seller=([A-Z0-9]+)', href)
            if not seller_id_match:
                logger.warning(f"Could not extract seller ID from href: {href}")
                return None

            seller_id = seller_id_match.group(1)

            # Check if we've already processed this seller
            if seller_id in self.processed_sellers:
                logger.info(f"Seller {seller_id} already processed, skipping")
                return None

            # Mark this seller as processed
            self.processed_sellers.add(seller_id)

            # Create seller info object
            seller_info = SellerInfo(
                seller_id=seller_id,
                country=country,
                category=category,
                amazon_store_url=f"https://www.{domain}/sp?seller={seller_id}",
                product_asin=product_asin
            )

            # Click on the seller link to navigate to the seller page
            logger.info(f"Navigating to seller page for {seller_id}")
            await seller_link.click()

            # Wait for the seller page to load
            await page.wait_for_load_state("networkidle")
            await self.random_delay()

            # Extract seller name
            try:
                seller_name_element = await page.query_selector("//h1[@id='seller-name']")
                if seller_name_element:
                    seller_info.seller_name = await seller_name_element.text_content()
            except Exception as e:
                logger.warning(f"Error extracting seller name: {str(e)}")

            # Extract business name
            try:
                business_name_element = await page.query_selector(
                    "//span[contains(text(), 'Business Name:')]/following-sibling::span")
                if business_name_element:
                    seller_info.business_name = await business_name_element.text_content()
            except Exception as e:
                logger.warning(f"Error extracting business name: {str(e)}")

            # Extract business type
            try:
                business_type_element = await page.query_selector(
                    "//span[contains(text(), 'Business Type:')]/following-sibling::span")
                if business_type_element:
                    seller_info.business_type = await business_type_element.text_content()
            except Exception as e:
                logger.warning(f"Error extracting business type: {str(e)}")

            # Extract trade registry number
            try:
                registry_element = await page.query_selector(
                    "//span[contains(text(), 'Trade Register Number:')]/following-sibling::span")
                if registry_element:
                    seller_info.trade_registry_number = await registry_element.text_content()
            except Exception as e:
                logger.warning(f"Error extracting registry number: {str(e)}")

            # Extract phone number
            try:
                phone_element = await page.query_selector(
                    "//span[contains(text(), 'Phone number')]/following-sibling::span")
                if phone_element:
                    seller_info.phone_number = await phone_element.text_content()
            except Exception as e:
                logger.warning(f"Error extracting phone number: {str(e)}")

            # Extract email
            try:
                email_element = await page.query_selector("//span[contains(text(), 'Email')]/following-sibling::span")
                if email_element:
                    seller_info.email = await email_element.text_content()
            except Exception as e:
                logger.warning(f"Error extracting email: {str(e)}")

            # Extract address
            try:
                address_elements = await page.query_selector_all(
                    "//div[@class='a-row a-spacing-none' and contains(span/text(), 'Business Address')]/following-sibling::div/span")
                address_parts = []
                for element in address_elements:
                    text = await element.text_content()
                    if text.strip():
                        address_parts.append(text.strip())

                seller_info.address = ", ".join(address_parts)
            except Exception as e:
                logger.warning(f"Error extracting address: {str(e)}")

            # Extract seller rating data
            try:
                # Look for the script tag containing rating data
                rating_script = await page.query_selector(
                    "//script[@data-a-state='{\\'key\\':\\\"lifetimeRatingsData\\\"}'")
                if not rating_script:
                    rating_script = await page.query_selector(
                        "//script[contains(@data-a-state, 'lifetimeRatingsData')]")

                if rating_script:
                    script_content = await rating_script.get_attribute("data-a-state")
                    if script_content:
                        # Parse the JSON content
                        import json
                        try:
                            # Clean up the JSON string
                            script_content = script_content.replace("\\'", "'").replace("'", '"')
                            data_obj = json.loads(script_content)

                            # Extract the rating data
                            ratings_data = data_obj.get("key", {})
                            if isinstance(ratings_data, str) and ratings_data == "lifetimeRatingsData":
                                # The data is in the script content itself
                                ratings_data = json.loads(await rating_script.evaluate("el => el.textContent"))

                            # Calculate the rating
                            if isinstance(ratings_data, dict):
                                # If we have counts for each star rating
                                star1 = ratings_data.get("star1Count", 0)
                                star2 = ratings_data.get("star2Count", 0)
                                star3 = ratings_data.get("star3Count", 0)
                                star4 = ratings_data.get("star4Count", 0)
                                star5 = ratings_data.get("star5Count", 0)

                                total_ratings = star1 + star2 + star3 + star4 + star5
                                if total_ratings > 0:
                                    weighted_sum = star1 * 1 + star2 * 2 + star3 * 3 + star4 * 4 + star5 * 5
                                    seller_info.rating = round(weighted_sum / total_ratings, 2)
                                    seller_info.rating_count = total_ratings

                        except json.JSONDecodeError as e:
                            logger.warning(f"Error parsing rating data JSON: {str(e)}")
            except Exception as e:
                logger.warning(f"Error extracting seller rating: {str(e)}")

            # If we still don't have a business name, try alternative XPath
            if not seller_info.business_name and seller_info.seller_name:
                seller_info.business_name = seller_info.seller_name

            # Try to extract the JSON data directly using JavaScript
            try:
                ratings_data = await page.evaluate("""
                    () => {
                        const ratingScripts = document.querySelectorAll('script[data-a-state]');
                        for (const script of ratingScripts) {
                            const dataAttr = script.getAttribute('data-a-state');
                            if (dataAttr && dataAttr.includes('lifetimeRatingsData')) {
                                try {
                                    // Try to parse the data-a-state attribute
                                    const parsed = JSON.parse(dataAttr.replace(/\\'/g, '"'));
                                    if (parsed.key === 'lifetimeRatingsData') {
                                        // If it's just the key, the data might be in the script content
                                        return JSON.parse(script.textContent);
                                    }
                                    return parsed;
                                } catch (e) {
                                    // If parsing fails, try to extract from textContent
                                    try {
                                        return JSON.parse(script.textContent);
                                    } catch (e2) {
                                        console.error('Failed to parse rating data');
                                        return null;
                                    }
                                }
                            }
                        }
                        return null;
                    }
                """)

                if ratings_data:
                    # Calculate the rating
                    star1 = ratings_data.get("star1Count", 0)
                    star2 = ratings_data.get("star2Count", 0)
                    star3 = ratings_data.get("star3Count", 0)
                    star4 = ratings_data.get("star4Count", 0)
                    star5 = ratings_data.get("star5Count", 0)

                    total_ratings = star1 + star2 + star3 + star4 + star5
                    if total_ratings > 0:
                        weighted_sum = star1 * 1 + star2 * 2 + star3 * 3 + star4 * 4 + star5 * 5
                        seller_info.rating = round(weighted_sum / total_ratings, 2)
                        seller_info.rating_count = total_ratings
            except Exception as e:
                logger.warning(f"Error extracting rating data via JavaScript: {str(e)}")

            logger.info(f"Successfully extracted seller info for {seller_id}")
            return seller_info

        except Exception as e:
            logger.error(f"Error extracting seller info: {str(e)}")
            return None

    async def handle_captcha(self, page: Page) -> bool:
        """
        Check for and attempt to handle CAPTCHA challenges

        Args:
            page: Playwright page object

        Returns:
            bool: True if handled or not present, False if couldn't handle
        """
        try:
            # Check for common CAPTCHA indicators
            captcha_indicators = [
                "//form[contains(@action, 'validateCaptcha')]",
                "//input[@id='captchacharacters']",
                "//div[contains(text(), 'Enter the characters you see')]",
                "//div[contains(text(), 'Type the characters you see')]",
                "//div[contains(text(), 'Bot check')]"
            ]

            for selector in captcha_indicators:
                captcha_element = await page.query_selector(selector)
                if captcha_element:
                    logger.warning("CAPTCHA detected!")

                    # If we have a CAPTCHA solver, try to solve it
                    if self.captcha_solver:
                        logger.info("Attempting to solve CAPTCHA automatically...")
                        success, message = await self.captcha_solver.solve_amazon_captcha(page)
                        if success:
                            logger.info(f"CAPTCHA solved successfully: {message}")
                            return True
                        else:
                            logger.error(f"Failed to solve CAPTCHA: {message}")

                    # Take screenshot of the CAPTCHA
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    screenshot_path = os.path.join(SCREENSHOTS_DIR, f"captcha_{timestamp}.png")
                    await page.screenshot(path=screenshot_path)

                    logger.info(f"CAPTCHA screenshot saved to: {screenshot_path}")
                    return False

            return True  # No CAPTCHA found

        except Exception as e:
            logger.error(f"Error checking for CAPTCHA: {str(e)}")
            return False

    async def scrape_sellers_for_country(self, country_code: str, max_retries: int = 5) -> List[SellerInfo]:
        """
        Scrape seller information for a specific country with retry logic

        Args:
            country_code: Country code from COUNTRY_CONFIGS
            max_retries: Maximum number of retries with different fingerprints

        Returns:
            List of SellerInfo objects
        """
        if country_code not in COUNTRY_CONFIGS:
            logger.error(f"Country code {country_code} not found in configurations")
            return []

        country_config = COUNTRY_CONFIGS[country_code]
        domain = country_config["domain"]
        category_url = country_config["category_url"]
        category_name = country_config.get("category_name", "Unknown")
        start_url = f"https://www.{domain}"

        sellers_found = []

        # Load all proxies at the start
        if self.proxy_manager:
            await self.proxy_manager.load_proxies()

        # Retry loop for fingerprint rotation
        for attempt in range(max_retries):
            logger.info(f"Attempt {attempt + 1}/{max_retries} for {country_code}")

            try:
                # Get a proxy if available - we'll use one proxy for the entire browser session
                proxy = None
                if self.proxy_manager:
                    proxy = await self.proxy_manager.get_next_proxy()
                    if proxy:
                        logger.info(f"Using proxy: {proxy}")
                    else:
                        logger.info("No proxy available, proceeding without proxy")

                # Track start time to measure proxy performance
                proxy_start_time = time.time()

                # Setup Camoufox with the selected proxy
                camoufox = await self.setup_camoufox(domain, proxy)

                async with camoufox as browser:
                    # Try to load cookies if they exist
                    cookies_loaded = False
                    saved_postcode = None
                    cookies = None

                    if proxy:
                        # Try to load proxy-specific cookies first
                        cookies_result = await self.load_cookies(browser, country_code, proxy)
                        cookies_loaded, saved_postcode, cookies = cookies_result

                    # If no proxy-specific cookies, try generic cookies
                    if not cookies_loaded:
                        cookies_result = await self.load_cookies(browser, country_code)
                        cookies_loaded, saved_postcode, cookies = cookies_result

                    # Create a new page
                    page = await browser.new_page()

                    # Now apply cookies if they were loaded
                    if cookies_loaded and cookies:
                        try:
                            # Add cookies to the context
                            await page.context.add_cookies(cookies)
                            logger.info(f"Added {len(cookies)} cookies to browser context")

                            # Navigate to homepage to verify cookies
                            await page.goto(start_url, wait_until="networkidle")

                            # Handle cookie banner if present (sometimes appears even with cookies)
                            await self.check_and_handle_cookie_banner(page)

                            # Check for CAPTCHA
                            if not await self.handle_captcha(page):
                                logger.error(f"CAPTCHA detected on homepage with cookies, retrying")
                                continue

                            # Verify location is correct
                            location_verified = False
                            if country_config.get("use_postcode", False) and saved_postcode:
                                location_verified = await self.verify_location(page, saved_postcode)

                            if location_verified:
                                logger.info(f"Location verified using loaded cookies: {saved_postcode}")
                                if self.proxy_manager and proxy:
                                    await self.proxy_manager.mark_proxy_success(proxy, 0.1, True)
                            else:
                                logger.warning(f"Location not verified with loaded cookies, will set location manually")
                                cookies_loaded = False
                        except Exception as e:
                            logger.error(f"Error applying cookies: {str(e)}")
                            cookies_loaded = False

                    # If cookies didn't work, go through the normal setup process
                    if not cookies_loaded:
                        # Navigate to the homepage
                        logger.info(f"Navigating to {start_url}")
                        await page.goto(start_url, wait_until="networkidle")

                        # Handle cookie banner if present
                        await self.check_and_handle_cookie_banner(page)

                        # Check for content availability
                        if not await self.check_content_availability(page):
                            logger.warning(
                                f"Content unavailable on homepage for {country_code}, retrying with different fingerprint")
                            if self.proxy_manager and proxy:
                                await self.proxy_manager.mark_proxy_failure(proxy)
                            continue

                        # Check for CAPTCHA
                        if not await self.handle_captcha(page):
                            logger.error(
                                f"CAPTCHA detected on homepage for {country_code}, retrying with different fingerprint")
                            if self.proxy_manager and proxy:
                                await self.proxy_manager.mark_proxy_failure(proxy)
                            continue

                        # Set location based on country configuration
                        location_set = False
                        postcode = None

                        if country_config.get("use_postcode", False):
                            postcode = country_config.get("postcode", "")
                            location_set = await self.set_location_by_postcode(page, postcode)
                        else:
                            country_name = country_config.get("country_name", "")
                            location_set = await self.select_country_from_dropdown(page, country_name)

                        if not location_set:
                            logger.warning(
                                f"Could not set location for {country_code}, will retry with different fingerprint")
                            if self.proxy_manager and proxy:
                                await self.proxy_manager.mark_proxy_failure(proxy)
                            continue

                        # Save cookies after successful location setup
                        await self.save_cookies(page, country_code, proxy, postcode)

                        # Mark proxy as successful with cookies verified
                        if self.proxy_manager and proxy:
                            await self.proxy_manager.mark_proxy_success(proxy, 0.1, True)

                    # Navigate to category
                    navigation_successful = False

                    # Try search navigation if query is provided
                    category_query = country_config.get("category_query", "")
                    if category_query:
                        logger.info(f"Attempting to navigate via search: {category_query}")
                        navigation_successful = await self.navigate_to_search_category(page, category_query)

                    # Fall back to direct URL if needed
                    if not navigation_successful:
                        logger.info(f"Navigating directly to category page: {category_url}")
                        await page.goto(category_url, wait_until="networkidle")

                    # Handle cookie banner again (sometimes appears after navigation)
                    await self.check_and_handle_cookie_banner(page)

                    # Check for content availability
                    if not await self.check_content_availability(page):
                        logger.warning(
                            f"Content unavailable on category page for {country_code}, retrying with different fingerprint")
                        if self.proxy_manager and proxy:
                            await self.proxy_manager.mark_proxy_failure(proxy)
                        continue

                    # Check for CAPTCHA again
                    if not await self.handle_captcha(page):
                        logger.error(
                            f"CAPTCHA detected on category page for {country_code}, retrying with different fingerprint")
                        if self.proxy_manager and proxy:
                            await self.proxy_manager.mark_proxy_failure(proxy)
                        continue

                    # Get product links with pagination
                    product_links = await self.get_product_links_with_pagination(
                        page,
                        1000000,
                        max_pages=1000  # Adjust based on your needs
                    )

                    if not product_links:
                        logger.warning(
                            f"No product links found for {country_code}, will retry with different fingerprint")
                        if self.proxy_manager and proxy:
                            await self.proxy_manager.mark_proxy_failure(proxy)
                        continue

                    # Process products sequentially using the same browser instance
                    logger.info(
                        f"Processing {len(product_links)} products sequentially using a single browser instance")
                    sellers_batch = []
                    for product in product_links:
                        if len(sellers_found) + len(sellers_batch) >= self.max_products_per_category:
                            break

                        asin = product["asin"]
                        url = product["url"]
                        logger.info(f"Processing product {asin}: {url}")

                        try:
                            # Create a new page using the existing browser instance
                            page = await browser.new_page()

                            try:
                                # Navigate to product page
                                await page.goto(url, wait_until="domcontentloaded")
                                await page.wait_for_selector("//span[@id='productTitle']", timeout=10000)

                                # Check for content availability
                                if not await self.check_content_availability(page):
                                    logger.warning(f"Content unavailable on product page {asin}, skipping")
                                    continue

                                # Check for CAPTCHA
                                if not await self.handle_captcha(page):
                                    logger.error(f"CAPTCHA detected on product page for {asin}, retrying with backoff")
                                    # Take a longer break to avoid triggering more CAPTCHAs
                                    await self.random_delay(3.0, 5.0)
                                    continue

                                # Extract seller information
                                seller_info = await self.extract_seller_info(page, asin, country_code, category_name,
                                                                             domain)
                                if seller_info:
                                    sellers_batch.append(seller_info)
                                    logger.info(f"Added seller info for {seller_info.seller_id}")

                                # Take a short random delay between products to appear more human-like
                                await self.random_delay(1.0, 2.0)

                            finally:
                                # Always close the page to free up resources
                                await page.close()

                        except Exception as e:
                            logger.error(f"Error processing product {asin}: {str(e)}")
                            continue

                    # Add the batch of sellers to our overall list
                    sellers_found.extend(sellers_batch)

                    # If we've processed some products successfully, mark proxy as successful
                    if sellers_found and self.proxy_manager and proxy:
                        elapsed_time = time.time() - proxy_start_time
                        # Calculate average time per successful operation
                        avg_time = elapsed_time / max(1, len(sellers_found))
                        await self.proxy_manager.mark_proxy_success(proxy, avg_time, True)
                        logger.info(
                            f"Proxy {proxy} performed well: found {len(sellers_found)} sellers in {elapsed_time:.2f} seconds")
                    elif self.proxy_manager and proxy:
                        await self.proxy_manager.mark_proxy_failure(proxy)
                        logger.warning(f"Proxy {proxy} failed to find any sellers")

                    # Save cookies after successful processing to help future runs
                    if sellers_found:
                        # Create a new temporary page for saving cookies
                        cookie_page = await browser.new_page()
                        try:
                            # Navigate to homepage to ensure cookies are properly set
                            await cookie_page.goto(start_url, wait_until="networkidle")
                            await self.save_cookies(cookie_page, country_code, proxy, saved_postcode)
                            logger.info(f"Saved cookies for future use with {country_code}")
                        finally:
                            await cookie_page.close()

                    # Return the sellers found in this attempt
                    logger.info(f"Found {len(sellers_found)} unique sellers for {country_code}")
                    return sellers_found

            except Exception as e:
                logger.error(f"Error during attempt {attempt + 1} for {country_code}: {str(e)}")

                # If this is the last attempt, just return whatever we have
                if attempt == max_retries - 1:
                    logger.error(f"All {max_retries} attempts failed for {country_code}")
                    return sellers_found

                # Otherwise wait before retrying
                await asyncio.sleep(random.uniform(5.0, 10.0))

        logger.info(f"Found {len(sellers_found)} unique sellers for {country_code} after {max_retries} attempts")
        return sellers_found

    async def scrape_all_countries(self, country_codes: Optional[List[str]] = None):
        """
        Scrape seller information for all countries or specified countries

        Args:
            country_codes: Optional list of country codes to scrape. If None, scrape all.
        """
        if country_codes:
            target_countries = [code for code in country_codes if code in COUNTRY_CONFIGS]
            if not target_countries:
                logger.error(f"None of the specified country codes {country_codes} were found in configurations")
                return
        else:
            target_countries = list(COUNTRY_CONFIGS.keys())

        logger.info(f"Starting to scrape {len(target_countries)} countries: {', '.join(target_countries)}")

        for country_code in target_countries:
            try:
                sellers = await self.scrape_sellers_for_country(country_code)
                self.sellers_data.extend(sellers)

                # Save intermediate results after each country
                self.save_results_to_json(f"{country_code}_sellers.json", sellers)

                logger.info(f"Completed scraping for {country_code}: Found {len(sellers)} sellers")
            except Exception as e:
                logger.error(f"Error scraping country {country_code}: {str(e)}")

    def save_results_to_json(self, filename="all_sellers.json", sellers=None):
        """Save results to a JSON file"""
        data_to_save = sellers if sellers is not None else self.sellers_data

        if not data_to_save:
            logger.warning("No seller data to save")
            return

        file_path = os.path.join(DATA_DIR, filename)

        results_data = []
        for seller in data_to_save:
            results_data.append(seller.to_dict())

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(results_data, f, indent=4, ensure_ascii=False)

        logger.info(f"Saved {len(results_data)} sellers to {file_path}")

    def print_summary(self):
        """Print a summary of the scraping results"""
        print("\n" + "=" * 60)
        print("AMAZON SELLER SCRAPING RESULTS SUMMARY")
        print("=" * 60)

        # Group by country
        by_country = {}
        for seller in self.sellers_data:
            if seller.country not in by_country:
                by_country[seller.country] = []
            by_country[seller.country].append(seller)

        print(f"Total unique sellers found: {len(self.processed_sellers)}")
        print(f"Total seller records: {len(self.sellers_data)}")
        print("-" * 60)

        # Print breakdown by country
        for country, sellers in by_country.items():
            print(f"{country.upper()}: {len(sellers)} sellers")

            # Calculate average rating
            ratings = [seller.rating for seller in sellers if seller.rating > 0]
            if ratings:
                avg_rating = sum(ratings) / len(ratings)
                print(f"  Average rating: {avg_rating:.2f} stars")

            # Count sellers with complete information
            complete_info = sum(1 for seller in sellers
                                if seller.business_name and seller.address)
            print(f"  Sellers with complete info: {complete_info} ({(complete_info / len(sellers) * 100):.1f}%)")

        print("=" * 60)


async def main():
    """Main entry point for the scraper"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Amazon Seller Information Scraper with Camoufox')
    parser.add_argument('--countries', type=str, help='Comma-separated country codes to scrape (default: all)')
    parser.add_argument('--proxy', type=str, help='Single proxy server (http://user:pass@host:port)')
    parser.add_argument('--max-products', type=int, default=10, help='Maximum products to process per category')
    parser.add_argument('--max-concurrency', type=int, default=3, help='Maximum concurrent browser instances')
    parser.add_argument('--no-headless', action='store_true', help='Disable headless mode (show browser)')
    args = parser.parse_args()

    # Set up proxy manager
    proxy_manager = ProxyManager("proxies.txt")

    # Set up Capsolver with the provided API key
    captcha_api_key = "CAP-956BF088AFEBDE1D55D75C975171507466CFFDF3C9657C7412145974FF602B9A"
    captcha_solver = CaptchaSolver(captcha_api_key)
    logger.info("Capsolver initialized with provided API key")

    # Initialize the scraper
    scraper = AmazonSellerScraper(
        proxy_manager=proxy_manager,
        captcha_solver=captcha_solver,
        max_products_per_category=args.max_products,
        max_concurrency=args.max_concurrency,
        headless=False
    )

    # If a specific proxy was provided as an argument, add it to the proxy manager
    if args.proxy:
        await proxy_manager.load_proxies()  # Load existing proxies first
        proxy_manager.proxies[args.proxy] = ProxyStats(address=args.proxy)
        proxy_manager.unverified_proxies.append(args.proxy)
        logger.info(f"Added command-line proxy: {args.proxy}")

    try:
        if args.countries:
            # Scrape specific countries
            countries = args.countries.split(',')
            await scraper.scrape_all_countries(countries)
        else:
            # Scrape all countries
            await scraper.scrape_all_countries()

        # Save final results
        scraper.save_results_to_json()

        # Print summary
        scraper.print_summary()

    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user")
        # Save whatever data we have so far
        scraper.save_results_to_json("interrupted_scrape.json")
    except Exception as e:
        logger.error(f"Unhandled exception: {str(e)}")
        # Try to save whatever data we have
        scraper.save_results_to_json("error_recovery.json")


if __name__ == "__main__":
    asyncio.run(main())