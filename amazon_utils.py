import asyncio
import logging
import re
from typing import Optional

from playwright.async_api import Page


logger = logging.getLogger(__name__)


async def random_delay(min_delay: float = 1.0, max_delay: float = 3.0) -> None:
    """Asynchronous sleep for a random duration in the provided range."""
    import random

    delay = random.uniform(min_delay, max_delay)
    await asyncio.sleep(delay)


def clean_brand_name(brand_name: str) -> str:
    """Remove common prefixes/suffixes and invisible chars from brand names."""
    prefixes_to_remove = [
        "Brand: ",
        "Visit the ",
        " Store",
        "‎",  # Zero-width char
    ]

    cleaned = brand_name or ""
    for token in prefixes_to_remove:
        if cleaned.startswith(token):
            cleaned = cleaned[len(token):]
        if cleaned.endswith(token):
            cleaned = cleaned[:-len(token)]
    return cleaned.strip()


def sanitize_dirname(brand_name: str) -> str:
    """Normalize brand name into a filesystem-safe directory name."""
    cleaned_name = clean_brand_name(brand_name)
    # Remove special characters; allow letters, numbers, underscore, hyphen and spaces
    dirname = re.sub(r'[^\w\s-]', '', cleaned_name)
    dirname = re.sub(r'[-\s]+', '_', dirname)
    return dirname[:100]


def extract_asin_from_url(url: str) -> Optional[str]:
    """Extract ASIN from various Amazon URL shapes.

    Supports typical patterns such as:
    - /dp/<ASIN>
    - %2Fdp%2F<ASIN>%2F
    - dp%2F<ASIN>
    """
    if not url:
        return None

    patterns = [
        r"/dp/([A-Z0-9]{8,})",
        r"%2Fdp%2F([A-Z0-9]{8,})%2F",
        r"dp%2F([A-Z0-9]{8,})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


async def handle_cookie_banner(page: Page) -> bool:
    """Handle cookie consent banners across locales.

    Returns True when either successfully handled or nothing to do; False on error.
    """
    try:
        await asyncio.sleep(2)

        decline_selectors = [
            # Locale-specific primary selectors
            "xpath=//button[@aria-label='Rifiuta']",  # Italian
            "xpath=//button[@id='sp-cc-rejectall-link']",  # Common (ES, NL, FR)

            # Generic fallbacks
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
        ]

        for selector in decline_selectors:
            try:
                btn = await page.query_selector(selector)
                if btn and await btn.is_visible():
                    logger.info(f"Found cookie decline button with selector: {selector}")
                    await btn.click()
                    await asyncio.sleep(1)
                    return True
            except Exception:
                # Move to next selector
                continue

        # Not finding a banner is not an error for our flow
        return True
    except Exception as e:
        logger.debug(f"Error handling cookie banner: {e}")
        return False


async def handle_intermediate_page(page: Page, domain: str) -> bool:
    """Handle Amazon intermediate pages that occasionally appear.

    Returns True if any intermediate page was handled, False otherwise.
    """
    handled_any = False
    max_attempts = 3

    for _ in range(max_attempts):
        try:
            # Generic intermediate page with ref=cs_503_link
            generic_button = await page.query_selector('xpath=//a[contains(@href, "ref=cs_503_link")]')
            if generic_button:
                logger.info("Found intermediate page with ref=cs_503_link, clicking to continue")
                await generic_button.click()
                await page.wait_for_load_state("domcontentloaded")
                await random_delay(1.0, 2.0)
                handled_any = True
                continue

            # Primary button container
            primary_button = await page.query_selector('xpath=//span[@class="a-button a-button-primary a-span12"]')
            if primary_button:
                logger.info("Found intermediate page with primary button, clicking to continue")
                await primary_button.click()
                await page.wait_for_load_state("domcontentloaded")
                await random_delay(1.0, 2.0)
                handled_any = True
                continue

            # Sometimes the clickable element is an inner input
            primary_button_parent = await page.query_selector(
                'xpath=//span[@class="a-button a-button-primary a-span12"]/span/input'
            )
            if primary_button_parent:
                logger.info("Found intermediate page with primary button input, clicking to continue")
                await primary_button_parent.click()
                await page.wait_for_load_state("domcontentloaded")
                await random_delay(1.0, 2.0)
                handled_any = True
                continue

            # Country-specific pages
            if domain == "amazon.it":
                it_button = await page.query_selector(
                    'xpath=//a[contains(text(), "Clicca qui per tornare alla home page di Amazon.it")]'
                )
                alternative_it_button = await page.query_selector('xpath=//button[@alt="Continua con gli acquisti"]')
                final_it_button = it_button or alternative_it_button
                if final_it_button:
                    logger.info("Found Amazon.it intermediate page, clicking to go to homepage")
                    await final_it_button.click()
                    await page.wait_for_load_state("domcontentloaded")
                    await random_delay(1.0, 2.0)
                    handled_any = True
                    continue

            elif domain == "amazon.es":
                es_button = await page.query_selector('xpath=//button[@alt="Seguir comprando"]')
                if es_button:
                    logger.info("Found Amazon.es intermediate page, clicking to continue")
                    await es_button.click()
                    await page.wait_for_load_state("domcontentloaded")
                    await random_delay(1.0, 2.0)
                    handled_any = True
                    continue

            elif domain == "amazon.fr":
                fr_button = await page.query_selector('xpath=//button[@alt="Continuer les achats"]')
                if fr_button:
                    logger.info("Found Amazon.fr intermediate page, clicking to continue")
                    await fr_button.click()
                    await page.wait_for_load_state("domcontentloaded")
                    await random_delay(1.0, 2.0)
                    handled_any = True
                    continue

            # None found this iteration
            break
        except Exception as e:
            logger.error(f"Error handling intermediate page: {e}")
            break

    return handled_any


def add_language_param(url: str) -> str:
    """Ensure language=en_GB is present in the URL."""
    if not url:
        return url
    if "language=en_GB" in url:
        return url
    if "?" in url:
        return f"{url}&language=en_GB"
    return f"{url}?language=en_GB"


async def navigate_with_handling(page: Page, url: str, domain: str,
                                wait_until: str = "domcontentloaded",
                                timeout_ms: int = 30000,
                                handle_cookies: bool = True,
                                post_delay: tuple = (1.0, 2.0)) -> None:
    """Navigate to URL then handle intermediate page and cookies with optional delay.

    - Adds no language parameter; caller should pass correct URL (can use add_language_param).
    - Handles common Amazon intermediate pages and cookie banners.
    - Adds a small randomized post-delay.
    """
    await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
    if await handle_intermediate_page(page, domain):
        await random_delay(1.0, 2.0)
    if handle_cookies:
        await handle_cookie_banner(page)
    await random_delay(*post_delay)


