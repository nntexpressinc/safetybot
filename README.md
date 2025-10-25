# SafetyBot v3.0 - Event Storage & Daily Reporting

A production-grade bot that monitors GoMotive APIs for speeding and driver performance events, stores them in a structured format, and generates daily Excel reports for review.

## 🆕 New Features (v3.0)

✅ **Event Storage**: All events are now stored in JSON format organized by date
✅ **Daily Excel Reports**: Automatic Excel generation at 23:59 each day
✅ **On-Demand Reports**: `/getid` command to retrieve today's report anytime
✅ **Performance Events Fixed**: Removed `media_required` filter - now captures all 6 performance event types:
   - Hard Brake
   - Crash
   - Seat Belt Violation
   - Stop Sign Violation
   - Distraction
   - Unsafe Lane Change

## 📊 Excel Report Structure

The generated Excel files include the following columns:

| Column | Content |
|--------|---------|
| Event Type | Speeding, Hard Brake, Crash, etc. |
| Driver Name | Full name of the driver |
| Date & Time | Event timestamp in local timezone |
| Speed Range | Only for speeding (e.g., "35–45 mph") |
| Exceeded By | Only for speeding (e.g., "+5 mph") |
| Severity | medium, high, or critical |

## 📁 Storage Structure

Events are stored in the `events_data/` directory:

```
events_data/
├── events_2025-10-25.json
├── events_2025-10-26.json
└── Daily_Report_2025-10-26.xlsx
```

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create a `.env` file in the project root with:

```env
# GoMotive API Configuration
API_KEY=your_api_key_here
API_BASE_URL=https://api.gomotive.com/v2

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# Bot Configuration
CHECK_INTERVAL=300  # Check every 5 minutes
```

### 3. Run the Bot

```bash
python safetybot.py
```

## 📋 Commands

### `/getid` or `/getid@nntexpressinc_safety_bot`

Sends the Excel report for today's date to Telegram. Use this any time during the day to retrieve the current day's events.

## 🔄 Automatic Features

- **Event Checking**: Every 5 minutes (configurable via `CHECK_INTERVAL`)
- **Daily Report**: Automatically generated and sent at 23:59 PM each day
- **Event Deduplication**: Tracks processed event IDs to prevent duplicates
- **Separate Event Type Tracking**: Each event type maintains its own last-processed ID

## 📝 Event Data Format

Each event stored in JSON includes:

```json
{
  "event_type": "speeding",
  "driver_name": "John Doe",
  "severity": "high",
  "date_time": "10/25/2025 02:30 PM",
  "speed_range": "35–45 mph",
  "exceeded_by": "+5 mph",
  "event_id": 12345,
  "timestamp": "2025-10-25T14:30:00.123456"
}
```

## 🔧 Configuration

### Check Interval

The `CHECK_INTERVAL` environment variable controls how often the bot checks for new events (in seconds):

- `300` = Every 5 minutes (default, recommended)
- `600` = Every 10 minutes
- `1800` = Every 30 minutes

### Daily Report Time

The Excel report is sent automatically at **23:59 PM** each day. To change this, modify the scheduler in `run_scheduler()`:

```python
schedule.every().day.at("23:59").do(lambda: asyncio.run(self.send_daily_excel()))
```

## 📊 Features & Reliability

- **Retry Logic**: 3-attempt retry with exponential backoff for API calls
- **Health Monitoring**: Tracks consecutive failures with critical alerts
- **Timezone Support**: Converts UTC to local timezone based on vehicle GPS coordinates
- **Unicode Support**: Proper handling of international characters
- **Graceful Shutdown**: Properly closes connections on SIGTERM/SIGINT
- **Comprehensive Logging**: All events logged to `safetybot.log`

## ⚙️ System Requirements

- Python 3.8+
- 50MB disk space minimum
- Internet connection for API and Telegram

## 📦 Dependencies

See `requirements.txt` for complete list:
- `python-telegram-bot` - Telegram bot integration
- `requests` - HTTP client for API calls
- `schedule` - Job scheduling
- `openpyxl` - Excel file generation
- `pytz` - Timezone handling
- `python-dotenv` - Environment configuration

## 🐛 Troubleshooting

### Performance Events Not Appearing

**v3.0 Fix**: Removed the `media_required=true` filter that was restricting events to only those with video.

If you're still not seeing events:
1. Check API key permissions
2. Verify `CHECK_INTERVAL` isn't too long
3. Check `safetybot.log` for error messages
4. Ensure event severity is medium/high/critical

### Excel File Not Generating

- Check the `events_data/` directory exists and is writable
- Verify `openpyxl` is installed: `pip install openpyxl`
- Check logs for specific error messages

### No Excel Sent at End of Day

- Ensure bot is running when 23:59 arrives
- Check Telegram chat ID is correct
- Verify bot has permission to send documents
- Check logs for send failures

## 📜 Version History

### v3.0 (Current)
- Event storage system with JSON format
- Daily Excel report generation
- Performance events filter fix (removed media_required)
- `/getid` command support
- Enhanced logging

### v2.1
- Real-time Telegram alerts with videos
- Health monitoring
- ID tracking per event type

## 📞 Support

For issues:
1. Check `safetybot.log` for error details
2. Verify all environment variables are set correctly
3. Ensure API credentials are valid
4. Check network connectivity

## 📄 License

See LICENSE file for details.