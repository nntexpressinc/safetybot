# SafetyBot v2.2 - Excel Reports Setup Guide

## What's New

The bot has been upgraded to **store all events and generate Excel reports**. Here's what you need to know:

## New Features

### 1. **Automatic Daily Excel Reports**
- At **11:59 PM every day**, the bot automatically:
  - Collects all events from that day
  - Generates a professional Excel file
  - Sends it to your Telegram group/chat
  - Each day's report contains a summary table with formatted headers

### 2. **On-Demand Excel Reports (/getexcel command)**
- Members of your group can request today's report anytime by typing:
  ```
  /getexcel@nntexpressinc_safety_bot
  ```
- The bot will immediately generate and send today's Excel file
- No events? Bot will notify you

### 3. **Event Data Storage**
- All events are now stored in JSON files in the `events_data/` folder
- Files are organized by date: `events_2024-09-25.json`, etc.
- You can manually access/backup these files anytime
- This allows for historical reporting or re-generating reports

## Excel File Format

Each Excel report contains a professional table with these columns:

| Column 1 | Column 2 | Column 3 | Column 4 | Column 5 | Column 6 |
|----------|----------|----------|----------|----------|----------|
| **Event Type** | **Driver Name** | **Date & Time** | **Speed Range** | **Exceeded By** | **Severity** |
| Speeding | John Smith | 09/25/2024 12:37 PM | 62.1–72.5 mph | +8.7 mph | high |
| Hard Brake | Jane Doe | 09/25/2024 01:15 PM | — | — | medium |
| Crash | Bob Johnson | 09/25/2024 02:45 PM | — | — | critical |

**Features:**
- Colored header row (blue background, white text)
- Professional formatting with borders
- Title row showing the date of the report
- Properly sized columns for readability
- All event data formatted consistently

## Installation Steps

### Step 1: Update Requirements
The new version uses `openpyxl` for Excel generation. This was already added to `requirements.txt`.

If you're using an existing installation, run:
```bash
pip install -r requirements.txt
```

Or just install openpyxl directly:
```bash
pip install openpyxl==3.10.1
```

### Step 2: Replace safetybot.py
Replace your old `safetybot.py` with the new version that includes:
- `store_event()` - Saves events to JSON
- `generate_excel_report()` - Creates Excel files
- `send_daily_excel_report()` - Schedules and sends daily reports
- `handle_get_excel_command()` - Handles /getexcel command

### Step 3: No .env Changes Needed
Your existing `.env` file works as-is. No new configuration variables are required.

### Step 4: Restart the Bot
```bash
# If running as service:
sudo systemctl restart safetybot.service

# If running manually:
# Press Ctrl+C, then restart
python3 safetybot.py
```

## Usage

### Automatic Reports
- The bot will automatically send Excel reports at **11:59 PM** (23:59)
- Reports are sent to the same Telegram chat configured in your `.env`
- The files are automatically cleaned up after sending

### On-Demand Reports
In your Telegram group, any member can type:
```
/getexcel@nntexpressinc_safety_bot
```

The bot will respond:
1. "📊 Generating Excel report for today..."
2. Send the Excel file
3. Or notify if no events exist: "📭 No events recorded for today yet."

## Monitoring & Debugging

### View Stored Events
```bash
# See today's events
cat events_data/events_$(date +%Y-%m-%d).json

# Pretty print
cat events_data/events_$(date +%Y-%m-%d).json | python3 -m json.tool
```

### Check Logs for Excel Operations
```bash
# Watch for EXCEL-related logs
tail -f safetybot.log | grep EXCEL

# Watch for command operations
tail -f safetybot.log | grep COMMAND
```

### Manual Excel Generation (for testing)
If you want to test Excel generation:
```python
from safetybot import SafetyBot
from datetime import datetime

bot = SafetyBot()
excel_path = bot.generate_excel_report(datetime.now())
print(f"Excel generated at: {excel_path}")
```

## Performance Events Not Showing?

If you're only seeing Speeding events and not performance events (hard brake, crash, etc.), check:

1. **Check logs for errors:**
   ```bash
   tail -f safetybot.log | grep "performance\|hard_brake\|crash"
   ```

2. **Verify severity levels:**
   - Only events with `medium`, `high`, or `critical` severity are processed
   - Low severity events are filtered out

3. **Test API directly:**
   ```bash
   curl -H "x-api-key: YOUR_API_KEY" \
     "https://api.gomotive.com/v2/driver_performance_events?event_types=hard_brake&media_required=true&per_page=25"
   ```

4. **Check if events have videos:**
   - The bot filters for `media_required=true`
   - Events without camera media may not be returned

## File Structure

```
events_data/
├── events_2024-09-24.json       # Yesterday's events
├── events_2024-09-25.json       # Today's events
└── events_2024-09-26.json       # Tomorrow's events (when available)

safetybot.log                     # All bot activity
```

## Troubleshooting

### Problem: "No events recorded for today yet."
**Solution:** 
- Events might not have the right severity level
- No events may have occurred
- Check the logs: `tail safetybot.log`

### Problem: Excel file doesn't send to Telegram
**Solution:**
1. Check file permissions in `events_data/`
2. Verify temp directory has space: `df -h /tmp`
3. Check logs: `tail safetybot.log | grep -i excel`

### Problem: /getexcel command not working
**Solution:**
1. Command must be used in a group where the bot is a member
2. Ensure the bot has permission to send documents
3. Check logs for command handler errors

### Problem: openpyxl import error
**Solution:**
```bash
pip install openpyxl==3.10.1
# Or if in venv:
source venv/bin/activate
pip install openpyxl==3.10.1
```

## Performance Considerations

- **Excel generation:** < 1 second for 100 events
- **Daily report sending:** Happens at 11:59 PM
- **On-demand reports:** Generated instantly when requested
- **Storage:** ~1KB per event in JSON format
- **Memory:** Negligible impact

## Security & Privacy

- Excel files are temporary and deleted after sending
- No data is stored on external servers
- JSON files are stored locally in `events_data/`
- Consider backing up important reports
- Keep your `.env` file secure

## Customization

### Change Daily Report Time
Edit `safetybot.py` and find this line:
```python
schedule.every().day.at("23:59").do(lambda: asyncio.run(self.send_daily_excel_report()))
```

Change `"23:59"` to your desired time (24-hour format):
- `"18:00"` for 6 PM
- `"06:00"` for 6 AM
- `"00:00"` for midnight

### Change Excel Formatting
Edit the `generate_excel_report()` method:
- Change colors: `PatternFill(start_color="4472C4"...)`
- Change font sizes: `Font(size=11)`
- Change column widths: `ws.column_dimensions['A'].width = 18`

### Archive Old Reports
Add this to your cron job:
```bash
# Archive events older than 30 days
find /home/safetybot/events_data -name "events_*.json" -mtime +30 -exec gzip {} \;
```

## Support

If you encounter issues:

1. **Check the logs first:**
   ```bash
   tail -100 safetybot.log | grep -i "error\|exception"
   ```

2. **Verify configuration:**
   ```bash
   cat .env
   ```

3. **Test manually:**
   ```bash
   python3 -c "from safetybot import SafetyBot; print(SafetyBot())"
   ```

4. **Review the README.md** for more troubleshooting tips

## Version Info

- **Bot Version:** 2.2 Pro - Excel Reports Edition
- **Release Date:** 2024
- **Python Required:** 3.8+
- **New Dependencies:** openpyxl==3.10.1
