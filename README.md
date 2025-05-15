# Amazon Seller Information Collector

A flexible, high-performance web scraper for gathering Amazon seller data across multiple countries.

## Features

- **Multi-Country Support**: Collect seller information from Amazon in different countries including UK, Sweden, Finland, Estonia, and Portugal
- **Proxy Management**: Intelligent proxy rotation with performance tracking and scoring
- **CAPTCHA Handling**: Automated solving using Capsolver service
- **Browser Fingerprinting**: Uses Camoufox for advanced browser fingerprinting and detection avoidance
- **Concurrency**: Process multiple products simultaneously for better performance
- **Cross-Platform**: Works on Windows, macOS, and Linux
- **Customizable Categories**: Easily add or modify product categories to scrape
- **Robust Error Handling**: Automatic retries and recovery from errors
- **Cookie Management**: Saves and reuses cookies to maintain sessions and avoid CAPTCHAs

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

The script will automatically load and manage these proxies, prioritizing those with better performance based on success rate, response time, and recency.

### CAPTCHA Solving

The project uses Capsolver for automated CAPTCHA solving:

1. Sign up at [Capsolver](https://capsolver.com) and get an API key
2. Update the `captcha_api_key` variable in `main.py` or add it to a `.env` file:
```
CAPTCHA_API_KEY=your_capsolver_api_key_here
```

### Country Configurations

Countries to scrape and their settings are defined in the `COUNTRY_CONFIGS` dictionary in `main.py`. You can modify this to:
- Add/remove countries
- Change product categories
- Update postcodes
- Configure country-specific settings

Current supported countries include:
- UK (amazon.co.uk)
- Sweden (amazon.se)
- Finland (via amazon.com)
- Estonia (via amazon.com)
- Portugal (via amazon.com)

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

- **main.py**: Entry point script and main Amazon scraping implementation
- **proxy_manager.py**: Handles proxy rotation and performance tracking
- **captcha_solver.py**: Automated CAPTCHA solving implementation
- **models.py**: Data models for seller information

### Data Flow

1. The application starts in `main.py`, which parses arguments and initializes services
2. `ProxyManager` loads and manages proxies with intelligent scoring
3. Browser instances are launched with Camoufox for fingerprinting
4. For each target country:
   - Set up browser with appropriate locale and fingerprint
   - Load/save cookies to maintain sessions
   - Navigate to Amazon and set location
   - Search for products in the configured category
   - Process product pages to extract seller information
   - Handle CAPTCHAs if encountered
5. Results are saved to both JSON and Excel files in the `seller_data` directory

## Extending the Project

### Adding a New Country

To add a new country, update the `COUNTRY_CONFIGS` dictionary in `main.py`:

```python
COUNTRY_CONFIGS = {
    # Existing countries...
    
    "new_country": {
        "domain": "amazon.com",  # or amazon.co.uk, amazon.de, etc.
        "country_name": "New Country",
        "category_url": "https://www.amazon.com/s?k=your+category",
        "category_name": "Your Category",
        "category_query": "your category",  # Optional search query
        "use_postcode": True,  # True if the country requires postcode
        "postcode": "12345"  # Only needed if use_postcode is True
    }
}
```

### Adding Custom Selectors

If Amazon's UI changes or you need to support a unique country variant, you can add custom selectors in the `AmazonSellerScraper` class in `main.py`.

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
   - Ensure proxies have appropriate permissions for Amazon

3. **High CAPTCHA Rate**
   - Try using residential proxies
   - Reduce request frequency
   - Ensure browser fingerprint randomization is working correctly
   - Update the Camoufox configuration

### Logging

Logs are stored in `amazon_seller_scraper.log` and contain detailed information about the scraping process, including errors and warnings.