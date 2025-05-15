# Amazon Seller Information Collector

A flexible, high-performance web scraper for gathering Amazon seller data across multiple countries.

## Features

- **Multi-Country Support**: Collect seller information from Amazon in different countries
- **Proxy Management**: Intelligent proxy rotation with performance tracking
- **CAPTCHA Handling**: Automated solving using 2Captcha
- **Concurrency**: Process multiple products simultaneously for better performance
- **Cross-Platform**: Works on Windows, macOS, and Linux
- **Customizable Categories**: Easily add or modify product categories to scrape
- **Robust Error Handling**: Automatic retries and recovery from errors

## Installation

### Prerequisites

- Python 3.8 or higher
- pip (Python package installer)

### Step 1: Clone the repository

```bash
git clone https://github.com/yourusername/seller_info_collector.git
cd seller_info_collector
```

### Step 2: Set up a virtual environment (recommended)

#### Windows
```bash
python -m venv .venv
.venv\Scripts\activate
```

#### macOS/Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Step 3: Install dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Install browser dependencies for Playwright

```bash
playwright install
```

## Configuration

### Proxies

Create a file named `proxies.txt` in the project root directory. Each line should contain one proxy in the following format:

```
http://username:password@host:port
```

For example:
```
http://user123:pass456@proxy1.example.com:8080
http://user456:pass789@proxy2.example.com:8080
```

The script will automatically load and manage these proxies, prioritizing those with better performance.

### CAPTCHA Solving

To enable automated CAPTCHA solving using 2Captcha:

1. Sign up at [2Captcha](https://2captcha.com) and get an API key
2. Create a file named `.env` in the project root:
```
CAPTCHA_API_KEY=your_2captcha_api_key_here
```

### Country Configurations

Countries to scrape and their settings are defined in `amazon_cfox_bt_cookies.py`. You can modify the `COUNTRY_CONFIGS` dictionary to:
- Add/remove countries
- Change product categories
- Update postcodes

## Usage

### Basic Usage

```bash
python main.py
```

This will scrape all configured countries with default settings.

### Advanced Usage

```bash
# Scrape specific countries
python main.py --countries uk,sweden

# Use a specific proxy
python main.py --proxy http://user:pass@host:port

# Process more products per category
python main.py --max-products 20

# Increase concurrency
python main.py --max-concurrency 5

# Disable headless mode (show browser)
python main.py --no-headless
```

## Project Architecture

### Core Components

- **main.py**: Entry point script
- **amazon_cfox_bt_cookies.py**: Main Amazon scraping implementation
- **proxy_manager.py**: Handles proxy rotation and performance tracking
- **captcha_solver.py**: Automated CAPTCHA solving implementation
- **models.py**: Data models for seller information

### Data Flow

1. The application starts in `main.py`, which parses arguments and initializes services
2. `ProxyManager` loads and manages proxies
3. `AmazonSellerScraper` uses Camoufox to launch browser instances
4. For each target country:
   - Set up browser with appropriate locale and fingerprint
   - Navigate to Amazon and set location
   - Search for products in the configured category
   - Process product pages to extract seller information
   - Handle CAPTCHAs if encountered
5. Results are saved to JSON files in the `seller_data` directory

## Extending the Project

### Adding a New Country

To add a new country, update the `COUNTRY_CONFIGS` dictionary in `amazon_cfox_bt_cookies.py`:

```python
COUNTRY_CONFIGS = {
    # Existing countries...
    
    "new_country": {
        "domain": "amazon.com",  # or amazon.co.uk, amazon.de, etc.
        "country_name": "New Country",
        "category_url": "https://www.amazon.com/s?k=your+category",
        "category_query": "your category",  # Optional search query
        "use_postcode": True,  # True if the country requires postcode
        "postcode": "12345"  # Only needed if use_postcode is True
    }
}
```

### Adding Custom Selectors

If Amazon's UI changes or you need to support a unique country variant, you can add custom selectors in the `AmazonSellerScraper` class.

### Improving CAPTCHA Handling

To enhance CAPTCHA solving capabilities, you can extend the `CaptchaSolver` class in `captcha_solver.py`.

## Troubleshooting

### Common Issues

1. **Browser Fails to Launch**
   - Ensure you've installed Playwright's browser dependencies
   - On Linux, you may need additional system libraries

2. **Proxies Not Working**
   - Verify proxy format in `proxies.txt`
   - Check proxy credentials and connectivity

3. **High CAPTCHA Rate**
   - Try using residential proxies
   - Reduce request frequency
   - Ensure browser fingerprint randomization is enabled

### Logging

Logs are stored in `amazon_seller_scraper.log` and contain detailed information about the scraping process, including errors and warnings.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
