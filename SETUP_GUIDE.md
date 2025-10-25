# SafetyBot v3.0 - Setup & Migration Guide

## 🎯 What's Changed in v3.0

This is a **major architectural change** from v2.1:

| Feature | v2.1 | v3.0 |
|---------|------|------|
| Alert Delivery | Real-time Telegram messages | Daily Excel files |
| Data Storage | Event IDs only | Full event data in JSON |
| Report Format | Individual messages | Formatted Excel workbooks |
| Video Handling | Downloaded & sent immediately | Not sent (focus on reporting) |
| Performance Events | Only with media (filtered) | **All events captured** ✨ |
| On-Demand Reports | Not available | `/getid` command |

## 🔧 Installation & Setup

### Step 1: Install openpyxl

The only new dependency is `openpyxl` for Excel generation:

```bash
cd C:\Users\Xolmirza\Desktop\safetybot
pip install openpyxl==3.10.0
```

Or use the updated requirements:

```bash
pip install -r requirements.txt
```

### Step 2: Create .env File

Create a `.env` file in your project root directory with your credentials:

```env
# GoMotive API Configuration
API_KEY=your_actual_api_key
API_BASE_URL=https://api.gomotive.com/v2

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_actual_bot_token
TELEGRAM_CHAT_ID=your_actual_chat_id

# Bot Configuration
CHECK_INTERVAL=300
```

**Important**: The `.env` file is in `.gitignore` for security - never commit it!

### Step 3: Test Configuration

Run the bot to test connections:

```bash
python safetybot.py
```

You should see:
- ✅ Telegram connection test
- ✅ Startup message in Telegram
- ✅ API connectivity test
- ✅ Event check cycle starting

## 📊 How It Works

### Event Collection Cycle

1. **Every 5 minutes** (or your CHECK_INTERVAL):
   - Fetch speeding events from v1 API
   - Fetch all 6 performance event types from v2 API
   - Filter for new events with medium/high/critical severity
   - **STORE** events to `events_data/events_YYYY-MM-DD.json`

2. **Daily at 23:59**:
   - Generate Excel from today's events
   - Send Excel file to Telegram chat

3. **On `/getid` command**:
   - Load today's events
   - Generate Excel
   - Send to Telegram immediately

### Event Storage

Events are stored in JSON format with full details:

```
events_data/
└── events_2025-10-25.json
```

Each event contains:
- Event type (speeding, hard_brake, crash, etc.)
- Driver name
- Date & time
- Severity
- Speed info (for speeding only)
- Event ID (for tracking)

### Excel Generation

The Excel file has:
- **Header row** with formatting (dark blue background, white text)
- **Data rows** with all event details
- **Formatted columns** with appropriate widths
- **Filename format**: `Daily_Report_YYYY-MM-DD.xlsx`

## 🚨 Key Fixes in v3.0

### Issue: Performance Events Not Coming Through (FIXED ✅)

**Problem**: Line 296 had `'media_required': 'true'` which filtered to only events with videos

**Solution**: Removed this parameter entirely

**Before**:
```python
params = {
    'event_types': event_type,
    'media_required': 'true',  # ❌ Restricts to only events with media
    'per_page': '25',
    'page_no': '1'
}
```

**After**:
```python
params = {
    'event_types': event_type,
    'per_page': '25',
    'page_no': '1'
}
```

Now you'll receive:
- ✅ Hard Brake events
- ✅ Crash events  
- ✅ Seat Belt Violation events
- ✅ Stop Sign Violation events
- ✅ Distraction events
- ✅ Unsafe Lane Change events

## 📋 Commands

### /getid

Send this command in the Telegram chat to get today's report:

```
/getid
```

Or the full bot mention:

```
/getid@nntexpressinc_safety_bot
```

**Response**: Excel file with today's events attached

## ⏱️ Scheduling

### Event Check Times

- **Interval**: Every 5 minutes (300 seconds) by default
- **Configurable**: Change `CHECK_INTERVAL` in `.env`

Examples:
- `300` = Every 5 minutes ⭐ Default
- `600` = Every 10 minutes
- `1800` = Every 30 minutes

### Daily Report Time

- **Time**: 23:59 PM (11:59 PM) every day
- **To change**: Edit `run_scheduler()` in safetybot.py:

```python
# Change "23:59" to your preferred time
schedule.every().day.at("23:59").do(lambda: asyncio.run(self.send_daily_excel()))
```

## 📁 File Structure

After first run, your directory will look like:

```
safetybot/
├── safetybot.py                    # Main bot code
├── requirements.txt                # Python packages
├── .env                            # Configuration (not in git)
├── README.md                       # Features & docs
├── SETUP_GUIDE.md                 # This file
├── safetybot.log                  # Detailed logs
├── last_speeding_event_id.txt     # Tracking
├── last_hard_brake_event_id.txt   # Tracking
├── ... (more event ID files)      # Tracking
└── events_data/                   # 📊 New!
    ├── events_2025-10-25.json
    ├── events_2025-10-26.json
    └── Daily_Report_2025-10-25.xlsx
```

## 🔍 Monitoring & Logs

### Real-time Logs

Watch the console output while running:

```bash
python safetybot.py
```

You'll see:
```
[2025-10-25 14:30:15] - Fetching speeding events
[2025-10-25 14:30:16] - Found 2 new speeding events
[2025-10-25 14:30:17] - Fetching hard_brake events
[2025-10-25 14:30:18] - Found 1 new hard_brake event
[2025-10-25 14:30:19] - [STORED] Event saved to events_2025-10-25.json
```

### Detailed Logs

All activity is logged to `safetybot.log`:

```bash
# Watch logs in real-time
tail -f safetybot.log

# Search for errors
grep ERROR safetybot.log

# Search for specific event type
grep hard_brake safetybot.log
```

## 🧪 Testing

### Test 1: Initial Setup

```bash
python safetybot.py
```

Check for:
- ✅ "Telegram OK" message
- ✅ Startup message in Telegram chat
- ✅ "API OK" with event counts
- ✅ "Starting event check cycle"

### Test 2: Event Storage

1. Let bot run for 5 minutes
2. Check `events_data/events_2025-10-25.json` exists
3. Open with any text editor to see stored events

### Test 3: Excel Generation

1. Run `/getid` command in Telegram
2. Should receive Excel file
3. Open file and verify data

### Test 4: Daily Report

1. Modify `run_scheduler()` to send at a sooner time (e.g., 1 minute from now)
2. Let bot run until that time
3. Check if Excel was sent to Telegram

## ⚙️ Troubleshooting

### Bot Not Receiving Events

**Checklist**:
- [ ] Verify `.env` has correct `API_KEY`
- [ ] Check API key has required permissions
- [ ] Verify `API_BASE_URL` is correct
- [ ] Wait 5 minutes for first check cycle
- [ ] Check `safetybot.log` for error messages

### Excel Not Generating

**Checklist**:
- [ ] Run `pip install openpyxl` to ensure it's installed
- [ ] Verify `events_data/` directory exists
- [ ] Check permissions on `events_data/` folder
- [ ] Look for errors in `safetybot.log`

### Events Not Sent to Telegram

**Checklist**:
- [ ] Verify `TELEGRAM_BOT_TOKEN` is correct
- [ ] Verify `TELEGRAM_CHAT_ID` is correct
- [ ] Confirm bot has permission to send documents in the chat
- [ ] Check network connectivity
- [ ] Look for Telegram errors in `safetybot.log`

### /getid Command Not Working

**Checklist**:
- [ ] Command format is exact: `/getid` or `/getid@nntexpressinc_safety_bot`
- [ ] Bot is running
- [ ] Command sent to the same chat as `TELEGRAM_CHAT_ID`
- [ ] Check logs for command handling errors

## 🔐 Security Notes

- **Never share `.env` file** - it contains API keys and bot tokens
- **Keep API key secret** - someone with it can access your fleet data
- **Protect bot token** - allow control of your bot if compromised
- **.gitignore has `.env`** - automatically excluded from git

## 📞 Getting Help

If issues persist:

1. **Check logs**:
   ```bash
   tail -50 safetybot.log | grep ERROR
   ```

2. **Verify configuration**:
   ```bash
   echo $API_KEY  # Verify env var is set
   ```

3. **Test manually**:
   ```bash
   python -c "from dotenv import load_dotenv; load_dotenv(); import os; print(os.getenv('API_KEY'))"
   ```

4. **Check connectivity**:
   ```bash
   python -c "import requests; print(requests.get('https://api.gomotive.com/v2').status_code)"
   ```

## 🚀 Next Steps

1. ✅ Install dependencies
2. ✅ Create `.env` file
3. ✅ Run `python safetybot.py`
4. ✅ Verify in logs
5. ✅ Wait for first Excel or test with `/getid`
6. ✅ Let it run continuously

---

**Version**: 3.0  
**Last Updated**: October 25, 2025  
**Next Major Update**: v4.0 (Database storage, advanced filtering)
