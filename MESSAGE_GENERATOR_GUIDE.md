# Message Generator Guide

## Overview
The Message Generator creates personalized messages for brands that have products without energy labels and takes screenshots for brands with 4+ products.

## Enhanced Navigation Features

### Intermediate Page Handling
The script now includes robust intermediate page handling from the energy label link collector:

- **Generic Intermediate Pages**: Handles pages with `ref=cs_503_link` buttons
- **Primary Button Pages**: Handles pages with Amazon's primary action buttons
- **Country-Specific Pages**:
  - **Amazon.it**: "Clicca qui per tornare alla home page di Amazon.it"
  - **Amazon.es**: "Seguir comprando" buttons
  - **Amazon.fr**: "Continuer les achats" buttons
- **Multiple Page Handling**: Can handle up to 3 consecutive intermediate pages

### Enhanced Cookie Banner Handling
Comprehensive cookie banner detection and handling:

- **Multi-language Support**: Italian ("Rifiuta"), English ("Decline"), etc.
- **Multiple Selectors**: XPath and CSS selectors for different banner types
- **Robust Detection**: Checks visibility before clicking
- **Graceful Fallback**: Continues even if no banner found

### Random Delays
Human-like behavior simulation:

- **Navigation Delays**: 2-4 seconds after page loads
- **Screenshot Delays**: 3-6 seconds between screenshots
- **Action Delays**: 1-2 seconds after intermediate page handling

## Usage

### Basic Commands

```bash
# Test mode - check files and show sample data
python generate_personalized_messages.py --test

# Generate messages for all brands (headless mode)
python generate_personalized_messages.py

# Generate with visible browser (for debugging)
python generate_personalized_messages.py --no-headless

# Limit processing to specific number of brands
python generate_personalized_messages.py --limit 10

# Start fresh (ignore previous progress)
python generate_personalized_messages.py --no-resume

# Reset all progress
python generate_personalized_messages.py --reset
```

### Advanced Options

```bash
# Combine options for testing
python generate_personalized_messages.py --limit 5 --no-headless --no-resume

# Resume interrupted processing
python generate_personalized_messages.py  # Automatically resumes by default
```

## How It Works

### 1. Data Loading
- Loads brand analysis from `all_brands_analysis_extracted.xlsx`
- Loads product data from `all_products_extracted.xlsx`
- Identifies brands needing messages (products_without_any_energy_info > 0)

### 2. Message Generation
- **Template Substitution**: Replaces placeholders with actual data
- **Brand Name Cleaning**: Removes "Brand: ", "Visit the ", " Store" prefixes/suffixes
- **Country Mapping**: Converts amazon.fr → France, amazon.se → Sweden, etc.
- **Category Detection**: Uses most common category for the brand

### 3. Screenshot Process (for brands with 4+ products)
- **Browser Setup**: Camoufox with fingerprinting protection
- **Navigation Enhancement**: 
  - Handles intermediate pages automatically
  - Manages cookie banners
  - Uses random delays
- **Smart Element Detection**:
  - Product pages: Uses `div#ppd` with 0.8x zoom
  - Search results: Uses multiple fallback selectors
- **File Organization**: `screenshots/brand_products/[country]/[brand]/product_[ASIN].png`

### 4. Progress Tracking
- **Resume Capability**: Automatically resumes interrupted processing
- **Progress File**: `message_generation_progress.json`
- **Screenshot Mapping**: `screenshot_mapping.json`

## Output Files

### Main Output
- **`all_brands_analysis_with_messages.xlsx`**: Original data + personalized messages

### Screenshots
- **Directory Structure**: `screenshots/brand_products/[country]/[brand]/`
- **Filename Format**: `product_[ASIN].png`
- **Max per Brand**: 4 screenshots

### Progress Files
- **`message_generation_progress.json`**: Tracks processed brands
- **`screenshot_mapping.json`**: Maps brands to screenshot paths

## Message Templates

### With Screenshots (4+ products)
```
Subject: We've reviewed [brand]'s listings on Amazon [country] - Compliance Support Available

Hello,

We've reviewed [brand]'s listings on Amazon [country] and noticed that [number_of_products] [product_category] products may be missing required energy efficiency information.

We've taken screenshots of some of your products to help illustrate the compliance requirements. Our team can help ensure your listings meet all energy labeling standards.

Would you like to schedule a brief call to discuss how we can help with compliance?

Best regards,
[Your Team]
```

### Without Screenshots (< 4 products)
```
Subject: We've reviewed [brand]'s listings on Amazon [country] - Compliance Support Available

Hello,

We've reviewed [brand]'s listings on Amazon [country] and noticed that [number_of_products] [product_category] products may be missing required energy efficiency information.

Our team can help ensure your listings meet all energy labeling standards.

Would you like to schedule a brief call to discuss how we can help with compliance?

Best regards,
[Your Team]
```

## Technical Improvements

### Robust Navigation
- **Intermediate Page Detection**: Automatically handles Amazon's redirect pages
- **Cookie Management**: Comprehensive banner handling across all countries
- **Timeout Handling**: Graceful failure for unresponsive pages
- **URL Parsing**: Enhanced ASIN extraction from complex sponsored URLs

### Browser Configuration
- **Fingerprinting Protection**: Uses Camoufox with humanization
- **Locale Support**: Proper locale settings for each country
- **Error Recovery**: Continues processing even if individual screenshots fail

### Performance Optimizations
- **Random Delays**: Prevents detection and rate limiting
- **Smart Retries**: Handles temporary failures gracefully
- **Progress Persistence**: Saves progress frequently to prevent data loss

## Statistics

Based on the extracted data:
- **Total Brands**: 6,982
- **Brands Needing Messages**: 6,676 (95.6%)
- **Brands Getting Screenshots**: 420 (6.3% of total, 6.3% of those needing messages)
- **Countries Covered**: 5 (France, Italy, Netherlands, Spain, Sweden)

## Troubleshooting

### Common Issues
1. **Timeout Errors**: Some Amazon URLs may be slow - this is normal, script continues
2. **Missing Screenshots**: Complex URLs or intermediate pages - enhanced handling reduces this
3. **Progress Lost**: Use `--reset` to start fresh if progress file corrupted

### Debug Mode
```bash
# Run with visible browser to see what's happening
python generate_personalized_messages.py --limit 1 --no-headless
```

### Log Files
The script logs all activities including:
- Navigation attempts
- Intermediate page handling
- Cookie banner interactions
- Screenshot success/failure
- Progress updates

## Best Practices

1. **Start Small**: Use `--limit 10` for initial testing
2. **Monitor Progress**: Check logs for any recurring issues
3. **Resume Safely**: Default resume behavior prevents duplicate work
4. **Backup Results**: Save output files before making changes
5. **Test Different Countries**: Each country may have different intermediate pages

The enhanced navigation makes the script much more reliable across different Amazon domains and handles the various redirect patterns that can occur during automated browsing. 