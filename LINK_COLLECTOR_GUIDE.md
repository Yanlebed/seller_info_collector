# Enhanced Link Collector Guide

## Overview

The enhanced link collector now includes robust resume functionality, allowing you to safely collect links from all Amazon countries even if the process gets interrupted.

## Key Features

✅ **Resume Capability**: Automatically resumes from where it left off  
✅ **Progress Tracking**: Saves progress after each country  
✅ **Retry Logic**: Automatically retries failed countries  
✅ **Status Checking**: View current collection status  
✅ **Error Handling**: Graceful handling of network issues and crashes  

## Countries Supported

- Sweden (amazon.se)
- France (amazon.fr)
- Italy (amazon.it)
- Spain (amazon.es)
- Netherlands (amazon.nl)

## Quick Start

### Option 1: Using the Runner Script (Recommended)

```bash
python run_link_collector.py
```

This will show you a menu with options:
1. Check status
2. Start/resume collection
3. Reset progress
4. Start fresh (no resume)
5. Exit

### Option 2: Direct Command Line

```bash
# Start with resume (default)
python energy_label_link_collector.py

# Check current status
python energy_label_link_collector.py --status

# Start fresh without resume
python energy_label_link_collector.py --no-resume

# Reset all progress
python energy_label_link_collector.py --reset

# Run specific countries only
python energy_label_link_collector.py --countries spain,italy
```

## How Resume Works

1. **Progress Tracking**: After each country is completed, progress is saved to `energy_label_data/product_links/collection_progress.json`

2. **Automatic Detection**: When you restart, the script automatically detects:
   - Which countries have been completed
   - Which countries need to be processed
   - Recent link files (within 24 hours)

3. **Smart Skipping**: Already completed countries are automatically skipped

## What Happens When Things Go Wrong

### Script Crashes or Gets Interrupted
- Progress is automatically saved after each country
- Simply restart the script - it will resume from where it left off
- No data loss occurs

### Network Issues or Timeouts
- Each country has automatic retry logic (2 retries by default)
- If a country fails after all retries, it's marked as failed
- You can rerun the script to retry only the failed countries

### Computer Shutdown/Restart
- All progress is saved to disk
- Restart the script and it will continue from the last completed country

## Monitoring Progress

### Check Status
```bash
python energy_label_link_collector.py --status
```

Shows:
- Total countries: 5
- Completed: 2
- Remaining: 3
- List of completed countries with link counts
- List of remaining countries
- Last update timestamp

### Example Status Output
```
Collection Status
==================================================
Total countries: 5
Completed: 2
Remaining: 3

Completed countries:
  ✓ spain: 45 links
  ✓ italy: 32 links

Remaining countries:
  ○ france
  ○ netherlands
  ○ sweden

Last updated: 2025-06-14T13:45:00
```

## Output Files

The collector saves files to `energy_label_data/product_links/`:

### Country-specific Link Files
- `spain_product_links_20250614_134500.json`
- `italy_product_links_20250614_135200.json`
- etc.

### Progress File
- `collection_progress.json` - tracks overall progress

### File Structure
```json
{
  "country": "spain",
  "collection_timestamp": "2025-06-14T13:45:00",
  "total_links": 45,
  "links": [
    {
      "asin": "B0DX6WTYXW",
      "url": "https://www.amazon.es/...",
      "has_energy_text": false,
      "category": "Refrigerators",
      "category_key": "fridges_freezers",
      "country": "spain",
      "domain": "amazon.es",
      "timestamp": "2025-06-14 13:45:00"
    }
  ]
}
```

## Troubleshooting

### Starting Over Completely
```bash
python energy_label_link_collector.py --reset
python energy_label_link_collector.py --no-resume
```

### Retry Failed Countries Only
Just run the script again - it will automatically skip completed countries and retry failed ones.

### Check What Countries Are Available
```bash
python energy_label_link_collector.py --status
```

### Run Specific Countries
```bash
python energy_label_link_collector.py --countries france,sweden
```

## Best Practices

1. **Run in Background**: For long collections, consider using `screen` or `tmux`
   ```bash
   screen -S link_collector
   python run_link_collector.py
   # Press Ctrl+A, then D to detach
   ```

2. **Monitor Progress**: Check status periodically
   ```bash
   python energy_label_link_collector.py --status
   ```

3. **Handle Interruptions**: If you need to stop, use Ctrl+C - progress will be saved

4. **Network Issues**: If you have network problems, just restart - resume will handle everything

## Recovery Scenarios

### Scenario 1: Script Crashes During Spain
- Spain was being processed when crash occurred
- Spain is NOT marked as completed
- Restart: Script will retry Spain from the beginning
- All other completed countries are skipped

### Scenario 2: Computer Shutdown After 3 Countries
- 3 countries were completed and saved
- Restart: Script loads progress and processes remaining 2 countries
- No re-processing of completed countries

### Scenario 3: Network Timeout in France
- France fails after 3 attempts
- Script continues to remaining countries
- France is marked as failed
- Restart: Script will retry only France (and any other failed countries)

## Tips for Large Collections

1. **Use Resume**: Always use resume mode (it's the default)
2. **Monitor Logs**: Check `energy_label_link_collector.log` for detailed progress
3. **Check Status**: Regularly check status to see progress
4. **Be Patient**: Each country can take 10-30 minutes depending on products found
5. **Network Stability**: Ensure stable internet connection for best results

## After Collection Completes

Once all countries are collected, you can:

1. **Proceed to Module 2**: Use the data extractor to get detailed product information
2. **Analyze Results**: Check the link files to see what was collected
3. **Reset for Future**: Use `--reset` if you want to collect fresh data later

The collected links are now ready for processing by the Energy Label Data Extractor (Module 2). 