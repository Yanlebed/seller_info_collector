#!/usr/bin/env python3
"""
Generate personalized messages for brands missing energy labels
and take screenshots for brands with 4 or more products
"""

import json
import asyncio
import pandas as pd
from typing import List, Dict, Optional, Set
from datetime import datetime
import logging
from pathlib import Path
import re

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

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Directories
RESULTS_DIR = Path("energy_label_data/extracted_data")
SCREENSHOTS_DIR = Path("screenshots/brand_products")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# Progress file
PROGRESS_FILE = RESULTS_DIR / "message_generation_progress.json"

# Country mapping for messages
COUNTRY_NAMES = {
    "www.amazon.es": "Spain",
    "www.amazon.se": "Sweden", 
    "www.amazon.fr": "France",
    "www.amazon.it": "Italy",
    "www.amazon.nl": "Netherlands"
}

# Message template
MESSAGE_TEMPLATE = """Hi ,

We've reviewed {brand}'s listings on Amazon in {country} and noticed that at least {number_of_products} products in {product_category} don't have EPREL Energy Label. (see screenshot).

Since energy labelling is mandatory under EU Regulation (Framework RegulationEU2017/1369), non-compliance can lead to penalties and product removal from the market.

We help brands like {brand} fix this by identifying missing labels, collecting required data, and automating EPREL submissions across EU markets.

Let me know if this is something worth discussing.

Best,"""

MESSAGE_TEMPLATE_NO_SCREENSHOT = """Hi ,

We've reviewed {brand}'s listings on Amazon in {country} and noticed that at least {number_of_products} products in {product_category} don't have EPREL Energy Label.

Since energy labelling is mandatory under EU Regulation (Framework RegulationEU2017/1369), non-compliance can lead to penalties and product removal from the market.

We help brands like {brand} fix this by identifying missing labels, collecting required data, and automating EPREL submissions across EU markets.

Let me know if this is something worth discussing.

Best,"""


class MessageGenerator:
    def __init__(self, headless: bool = True, resume: bool = True, limit: Optional[int] = None):
        self.headless = headless
        self.resume = resume
        self.limit = limit
        self.brand_messages = []
        self.screenshots_taken = {}
        self.processed_brands: Set[str] = set()
        self.progress_data = {}

    def load_progress(self):
        """Load progress from file"""
        if self.resume and PROGRESS_FILE.exists():
            try:
                with open(PROGRESS_FILE, 'r') as f:
                    self.progress_data = json.load(f)
                    self.processed_brands = set(self.progress_data.get('processed_brands', []))
                    self.screenshots_taken = self.progress_data.get('screenshots_taken', {})
                    logger.info(f"Resumed progress: {len(self.processed_brands)} brands already processed")
                    return True
            except Exception as e:
                logger.error(f"Error loading progress: {str(e)}")
        return False

    def save_progress(self):
        """Save progress to file"""
        self.progress_data = {
            'processed_brands': list(self.processed_brands),
            'screenshots_taken': self.screenshots_taken,
            'last_updated': datetime.now().isoformat()
        }
        
        try:
            with open(PROGRESS_FILE, 'w') as f:
                json.dump(self.progress_data, f, indent=2)
            logger.debug("Progress saved")
        except Exception as e:
            logger.error(f"Error saving progress: {str(e)}")

    async def setup_browser(self, amazon_host: str) -> AsyncCamoufox:
        """Setup Camoufox browser with appropriate configuration"""
        logger.info(f"Setting up browser for {amazon_host}")
        
        try:
            # Simplified configuration to avoid initialization issues
            camoufox = AsyncCamoufox(
                headless=self.headless,
                humanize=True
            )
            
            return camoufox
            
        except Exception as e:
            logger.error(f"Error setting up browser: {str(e)}")
            raise

    def sanitize_filename(self, url: str) -> str:
        """Convert URL to safe filename"""
        # Extract ASIN from URL
        asin_match = re.search(r'/dp/([A-Z0-9]+)', url)
        if asin_match:
            asin = asin_match.group(1)
            return f"product_{asin}"
        
        # Fallback: replace special characters
        filename = url.replace("https://", "").replace("http://", "")
        filename = re.sub(r'[^\w\-_]', '_', filename)
        return filename[:100]  # Limit length

    def clean_brand_name(self, brand_name: str) -> str:
        """Delegate to shared brand name cleaner."""
        return util_clean_brand_name(brand_name)

    def sanitize_dirname(self, brand_name: str) -> str:
        """Delegate to shared directory sanitizer."""
        return util_sanitize_dirname(brand_name)

    async def handle_cookie_banner(self, page: Page) -> bool:
        """Delegate to shared cookie handler."""
        return await util_handle_cookie_banner(page)

    async def handle_intermediate_page(self, page: Page, domain: str) -> bool:
        """Delegate to shared intermediate-page handler."""
        return await util_handle_intermediate_page(page, domain)

    async def random_delay(self, min_delay: float = 1.0, max_delay: float = 3.0):
        """Delegate to shared random delay."""
        await util_random_delay(min_delay, max_delay)

    async def take_product_screenshot(self, page: Page, product_url: str, amazon_host: str, brand_name: str) -> Optional[str]:
        """Take screenshot of product on search results page or product page"""
        try:
            logger.info(f"Taking screenshot for: {product_url}")
            
            # Extract ASIN from URL via shared utility
            asin = extract_asin_from_url(product_url)
            if not asin:
                logger.warning(f"Could not extract ASIN from URL: {product_url}")
                return None
            logger.info(f"Extracted ASIN: {asin}")
            
            # Extract domain for intermediate page handling
            domain = amazon_host.replace("www.", "")
            
            # Navigate to product URL
            logger.info(f"Navigating to: {product_url}")
            await page.goto(product_url, wait_until="domcontentloaded", timeout=30000)
            
            # Handle intermediate pages first
            if await self.handle_intermediate_page(page, domain):
                logger.info("Handled intermediate page after navigation")
                await self.random_delay(1.0, 2.0)
            
            # Handle cookie banner
            await self.handle_cookie_banner(page)
            
            # Additional wait for page to fully load
            await self.random_delay(2.0, 4.0)
            
            # Check if we're on a product page
            product_title = await page.query_selector("#productTitle")
            
            if product_title:
                # We're on a product page, use div#ppd selector
                logger.info("On product page, taking screenshot of product details")
                
                # Zoom out slightly for better view
                await page.evaluate("document.body.style.zoom = '0.8'")
                await asyncio.sleep(1)
                
                # Try to find the product details div
                element = await page.query_selector("div#ppd")
                
                if not element:
                    logger.warning("Could not find div#ppd on product page, trying alternative selectors")
                    # Try alternative selectors
                    alt_selectors = ["#dp", "#dp-container", "#centerCol"]
                    for selector in alt_selectors:
                        element = await page.query_selector(selector)
                        if element:
                            logger.info(f"Found element with selector: {selector}")
                            break
                
                if not element:
                    logger.warning("Could not find any suitable element on product page")
                    return None
                
            else:
                # We're likely on a search results page or got redirected, search for the product
                logger.info("Not on product page, searching for product")
                
                # Search for the product by ASIN
                search_url = f"https://{amazon_host}/s?k={asin}"
                logger.info(f"Searching at: {search_url}")
                await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                
                # Handle intermediate pages after search navigation
                if await self.handle_intermediate_page(page, domain):
                    logger.info("Handled intermediate page after search")
                    await self.random_delay(1.0, 2.0)
                
                # Handle cookie banner again if needed
                await self.handle_cookie_banner(page)
                
                await self.random_delay(2.0, 4.0)
                
                # Try multiple selectors for product results
                selectors = [
                    f'div[data-asin="{asin}"]',
                    'div[data-component-type="s-search-result"]',
                    'div[data-cel-widget*="search_result_"]'
                ]
                
                element = None
                for selector in selectors:
                    elements = await page.query_selector_all(selector)
                    if elements:
                        element = elements[0]  # Take first match
                        logger.info(f"Found product element with selector: {selector}")
                        break
                
                if not element:
                    logger.warning("Could not find product element in search results")
                    return None
            
            # Create directory structure: screenshots/brand_products/[amazon_country]/[brand_name]/
            country = amazon_host.replace("www.amazon.", "")
            brand_dirname = self.sanitize_dirname(brand_name)
            
            # Take screenshot of the element
            filename = f"product_{asin}.png"
            filepath = SCREENSHOTS_DIR / country / brand_dirname / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"Taking screenshot and saving to: {filepath}")
            await element.screenshot(path=str(filepath))
            logger.info(f"Screenshot saved successfully to: {filepath}")
            
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Error taking screenshot for {product_url}: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    async def take_screenshots_for_brand(self, brand_data: Dict, products_df: pd.DataFrame) -> List[str]:
        """Take screenshots for a brand's products (max 3)"""
        brand_name = brand_data['brand']
        amazon_host = brand_data['amazon_host']
        
        logger.info(f"Starting screenshot process for brand: {brand_name}")
        
        # Get products for this brand without energy labels
        brand_products = products_df[
            (products_df['brand'] == brand_name) & 
            (products_df['amazon_host'] == amazon_host) &
            (products_df['has_energy_text'] == False)
        ]
        
        if brand_products.empty:
            logger.warning(f"No products without energy labels found for brand: {brand_name}")
            return []
        
        # Take max 4 screenshots
        screenshots = []
        products_to_screenshot = brand_products.head(4)
        
        logger.info(f"Will take screenshots for {len(products_to_screenshot)} products")
        
        # Setup browser for this amazon host
        try:
            camoufox = await self.setup_browser(amazon_host)
            
            async with camoufox as browser:
                logger.info("Browser started successfully")
                page = await browser.new_page()
                logger.info("New page created")
                
                for idx, (_, product) in enumerate(products_to_screenshot.iterrows()):
                    logger.info(f"Processing product {idx + 1}/{len(products_to_screenshot)}")
                    screenshot_path = await self.take_product_screenshot(
                        page, 
                        str(product['product_url']), 
                        amazon_host,
                        brand_name
                    )
                    
                    if screenshot_path:
                        screenshots.append(screenshot_path)
                        logger.info(f"Successfully took screenshot {idx + 1}")
                    else:
                        logger.warning(f"Failed to take screenshot {idx + 1}")
                    
                    # Random delay between screenshots to avoid detection
                    if idx < len(products_to_screenshot) - 1:  # Don't delay after last screenshot
                        await self.random_delay(3.0, 6.0)
                
        except Exception as e:
            logger.error(f"Error in browser session for {brand_name}: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
        
        logger.info(f"Completed screenshot process for {brand_name}: {len(screenshots)} screenshots taken")
        return screenshots

    def generate_message(self, brand_data: Dict, category: str, include_screenshot: bool = False) -> str:
        """Generate personalized message for a brand"""
        country = COUNTRY_NAMES.get(brand_data['amazon_host'], brand_data['amazon_host'])
        
        # Clean brand name
        clean_brand = self.clean_brand_name(brand_data['brand'])
        
        template = MESSAGE_TEMPLATE if include_screenshot else MESSAGE_TEMPLATE_NO_SCREENSHOT
        
        message = template.format(
            brand=clean_brand,
            country=country,
            number_of_products=brand_data['products_without_any_energy_info'],
            product_category=category
        )
        
        return message

    async def process_brands(self, brands_df: pd.DataFrame, products_df: pd.DataFrame):
        """Process all brands and generate messages"""
        # Apply limit if specified
        if self.limit:
            # Filter to only brands that need messages
            brands_needing_messages = brands_df[brands_df['products_without_any_energy_info'] > 0]
            
            # If resuming, exclude already processed brands
            if self.resume:
                unprocessed_mask = ~brands_needing_messages.apply(
                    lambda row: f"{row['amazon_host']}_{row['brand']}" in self.processed_brands, 
                    axis=1
                )
                brands_to_process = brands_needing_messages[unprocessed_mask]
            else:
                brands_to_process = brands_needing_messages
            
            # Sort by total_products descending to prioritize brands with more products (for screenshot testing)
            brands_to_process = brands_to_process.sort_values('total_products', ascending=False)
            
            # Apply limit
            if len(brands_to_process) > self.limit:
                brands_df = brands_df[brands_df.index.isin(brands_to_process.head(self.limit).index)]
                logger.info(f"Limited to processing {self.limit} brands (prioritizing those with more products)")
            else:
                logger.info(f"Only {len(brands_to_process)} unprocessed brands available (limit was {self.limit})")
        
        logger.info(f"Processing {len(brands_df)} brands")
        
        # Create a copy of brands_df to add the message column
        result_df = brands_df.copy()
        messages = []
        
        # Load existing messages if resuming
        existing_messages = {}
        if self.resume and (RESULTS_DIR / "all_brands_analysis_with_messages.xlsx").exists():
            try:
                existing_df = pd.read_excel(RESULTS_DIR / "all_brands_analysis_with_messages.xlsx")
                for _, row in existing_df.iterrows():
                    key = f"{row['amazon_host']}_{row['brand']}"
                    if 'personalized_message' in row and pd.notna(row['personalized_message']):
                        existing_messages[key] = row['personalized_message']
            except Exception as e:
                logger.warning(f"Could not load existing messages: {str(e)}")
        
        for idx, brand_data in brands_df.iterrows():
            brand_name = brand_data['brand']
            amazon_host = brand_data['amazon_host']
            total_products = brand_data['total_products']
            products_without_labels = brand_data['products_without_any_energy_info']
            
            brand_key = f"{amazon_host}_{brand_name}"
            
            # Check if already processed
            if self.resume and brand_key in self.processed_brands:
                # Use existing message
                messages.append(existing_messages.get(brand_key, ""))
                continue
            
            # Skip brands with no products missing labels
            if products_without_labels == 0:
                messages.append("")
                self.processed_brands.add(brand_key)
                continue
            
            # Get category for this brand
            brand_products = products_df[
                (products_df['brand'] == brand_name) & 
                (products_df['amazon_host'] == amazon_host)
            ]
            
            if brand_products.empty:
                logger.warning(f"No products found for brand: {brand_name}")
                messages.append("")
                self.processed_brands.add(brand_key)
                continue
            
            # Get the most common category for this brand
            category_counts = brand_products['category'].value_counts()
            if len(category_counts) > 0:
                category = str(category_counts.index[0])
            else:
                category = "appliances"
            
            # Determine if we need screenshots (4 or more products)
            need_screenshots = total_products >= 4
            
            if need_screenshots:
                logger.info(f"Taking screenshots for {brand_name} ({total_products} products)")
                screenshots = await self.take_screenshots_for_brand(brand_data.to_dict(), products_df)
                self.screenshots_taken[brand_key] = screenshots
            
            # Generate message
            message = self.generate_message(
                brand_data.to_dict(), 
                category, 
                include_screenshot=need_screenshots
            )
            
            messages.append(message)
            self.processed_brands.add(brand_key)
            
            # Save progress periodically
            if len(self.processed_brands) % 10 == 0:
                self.save_progress()
            
            # Log progress
            row_num = idx if isinstance(idx, int) else 0
            if (row_num + 1) % 10 == 0:
                logger.info(f"Processed {row_num + 1}/{len(brands_df)} brands")
        
        # Add messages to dataframe
        result_df['personalized_message'] = messages
        
        # Save final progress
        self.save_progress()
        
        return result_df

    async def run(self):
        """Main execution function"""
        try:
            # Load progress if resuming
            if self.resume:
                self.load_progress()
            
            # Load data
            logger.info("Loading brand analysis data...")
            brands_file = RESULTS_DIR / "all_brands_analysis_extracted.xlsx"
            products_file = RESULTS_DIR / "all_products_extracted.xlsx"
            
            if not brands_file.exists():
                logger.error(f"Brands file not found: {brands_file}")
                return
            
            if not products_file.exists():
                logger.error(f"Products file not found: {products_file}")
                return
            
            brands_df = pd.read_excel(brands_file)
            products_df = pd.read_excel(products_file)
            
            logger.info(f"Loaded {len(brands_df)} brands and {len(products_df)} products")
            
            # Process brands
            result_df = await self.process_brands(brands_df, products_df)
            
            # Save results
            output_file = RESULTS_DIR / "all_brands_analysis_with_messages.xlsx"
            result_df.to_excel(output_file, index=False)
            logger.info(f"Saved results to: {output_file}")
            
            # Save screenshot mapping
            if self.screenshots_taken:
                screenshots_file = SCREENSHOTS_DIR / "screenshot_mapping.json"
                with open(screenshots_file, 'w') as f:
                    json.dump(self.screenshots_taken, f, indent=2)
                logger.info(f"Saved screenshot mapping to: {screenshots_file}")
            
            # Print summary
            print("\n" + "="*60)
            print("MESSAGE GENERATION SUMMARY")
            print("="*60)
            print(f"Total brands processed: {len(brands_df)}")
            print(f"Brands with messages: {len([m for m in result_df['personalized_message'] if m])}")
            print(f"Brands with screenshots: {len(self.screenshots_taken)}")
            print(f"Output file: {output_file}")
            print("="*60)
            
        except Exception as e:
            logger.error(f"Error in main execution: {str(e)}")
            raise


async def main():
    """Entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate personalized messages for brands')
    parser.add_argument('--no-headless', action='store_true', help='Show browser window')
    parser.add_argument('--test', action='store_true', help='Test mode - only process first 5 brands')
    parser.add_argument('--no-resume', action='store_true', help='Start fresh, ignore previous progress')
    parser.add_argument('--reset', action='store_true', help='Reset progress and start over')
    parser.add_argument('--limit', type=int, help='Limit the number of brands to process')
    args = parser.parse_args()
    
    # Reset progress if requested
    if args.reset:
        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()
            print("✅ Progress reset")
        else:
            print("ℹ️  No progress file to reset")
        return
    
    # Test mode - check if files exist
    if args.test:
        brands_file = RESULTS_DIR / "all_brands_analysis_extracted.xlsx"
        products_file = RESULTS_DIR / "all_products_extracted.xlsx"
        
        if not brands_file.exists():
            print(f"❌ Brands file not found: {brands_file}")
            print("Please ensure you have run the data extractor first.")
            return
        
        if not products_file.exists():
            print(f"❌ Products file not found: {products_file}")
            print("Please ensure you have run the data extractor first.")
            return
        
        print("✅ Required files found!")
        print(f"   - Brands file: {brands_file}")
        print(f"   - Products file: {products_file}")
        
        # Check progress
        if PROGRESS_FILE.exists():
            with open(PROGRESS_FILE, 'r') as f:
                progress = json.load(f)
                processed = len(progress.get('processed_brands', []))
                print(f"\n📊 Progress: {processed} brands already processed")
                print(f"   Last updated: {progress.get('last_updated', 'Unknown')}")
        
        # Try loading the files
        try:
            brands_df = pd.read_excel(brands_file)
            products_df = pd.read_excel(products_file)
            print(f"\n✅ Successfully loaded {len(brands_df)} brands and {len(products_df)} products")
            
            # Show sample of brands that would get messages
            brands_needing_messages = brands_df[brands_df['products_without_any_energy_info'] > 0]
            print(f"\nBrands needing messages: {len(brands_needing_messages)}")
            
            # Show which brands would get screenshots (4+ products)
            brands_with_screenshots = brands_needing_messages[brands_needing_messages['total_products'] >= 4]
            print(f"Brands that would get screenshots (4+ products): {len(brands_with_screenshots)}")
            
            if len(brands_needing_messages) > 0:
                print("\nSample brands (first 5):")
                for idx, row in brands_needing_messages.head(5).iterrows():
                    screenshot_note = " (with screenshots)" if row['total_products'] >= 4 else ""
                    print(f"  - {row['brand']} ({row['amazon_host']}): {row['products_without_any_energy_info']} products without labels{screenshot_note}")
            
            return
            
        except Exception as e:
            print(f"❌ Error loading files: {str(e)}")
            return
    
    generator = MessageGenerator(
        headless=not args.no_headless,
        resume=not args.no_resume,
        limit=args.limit
    )
    await generator.run()


if __name__ == "__main__":
    asyncio.run(main()) 