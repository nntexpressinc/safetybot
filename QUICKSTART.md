# SafetyBot v3.0 - Quick Start (5 Minutes)

## 🚀 Get Running in 5 Steps

### 1️⃣ Install Package (1 min)
```bash
pip install openpyxl==3.10.0
```

### 2️⃣ Create `.env` File (1 min)

Create a new file called `.env` in your safetybot folder with:

```
API_KEY=your_api_key_here
API_BASE_URL=https://api.gomotive.com/v2
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
CHECK_INTERVAL=300
```

Replace:
- `your_api_key_here` → Your GoMotive API key
- `your_telegram_bot_token_here` → Your Telegram bot token
- `your_chat_id_here` → Your Telegram chat ID

### 3️⃣ Run the Bot (1 min)
```bash
python safetybot.py
```

You should see:
```
============================================================
SafetyBot v3.0 - Event Storage & Daily Reporting
Check interval: 5 minutes
Features:
  • Stores all speeding & performance events
  • Auto-sends Excel at 23:59 daily
  • /getid command for today's report
Press Ctrl+C to stop
============================================================
```

### 4️⃣ Verify Setup (1 min)

Look for messages in the console:
- ✅ `[TEST] Telegram OK`
- ✅ Telegram receives startup message
- ✅ `[TEST] API OK: X speeding, Y performance events`

### 5️⃣ Test the Bot (1 min)

In your Telegram chat, type:
```
/getid
```

You should receive an Excel file (if there are events).

## 📊 What Happens Next

- **Every 5 minutes**: Bot checks for new events and stores them
- **Daily at 23:59**: Bot generates and sends Excel report
- **Anytime**: Type `/getid` to get today's report

## 📁 Where's My Data?

Events are stored in: `events_data/` directory
- `events_2025-10-25.json` → Raw event data
- `Daily_Report_2025-10-25.xlsx` → Excel file

## 🔧 Need Help?

### Bot Not Starting?
```bash
python safetybot.py
# Look for error message
# Check safetybot.log file
```

### No Events Showing?
- Wait 5 minutes (first check cycle)
- Verify API key is correct
- Check `safetybot.log` for errors

### /getid Not Working?
- Make sure bot is running
- Type exact command: `/getid`
- Wait for bot to respond with Excel file

## 📋 What's New in v3.0?

✨ **Key Changes from Previous Version**:
- ✅ Now captures ALL 6 performance event types (not just those with video)
- ✅ Stores event data for reporting
- ✅ Generates daily Excel files
- ✅ `/getid` command for on-demand reports

## 🎯 Excel Report Format

The daily Excel contains:

| Column | Content |
|--------|---------|
| Event Type | Speeding, Hard Brake, Crash, etc. |
| Driver Name | Full name of driver |
| Date & Time | When event occurred |
| Speed Range | Only for speeding |
| Exceeded By | Only for speeding |
| Severity | medium / high / critical |

## ⏰ Schedule

- **Every 5 minutes**: Check for new events
- **11:59 PM (23:59)**: Generate and send daily Excel
- **Anytime**: `/getid` command gets today's data

## 💾 Changing Check Interval

Edit `.env`:
```env
CHECK_INTERVAL=300  # Change to:
# 600 for 10 minutes
# 1800 for 30 minutes
# etc.
```

Then restart bot.

## 📝 Logs

Watch real-time activity:
```bash
tail -f safetybot.log
```

Look for:
- `[FETCH]` - API calls
- `[STORED]` - Events saved
- `[SENT]` - Excel files sent
- `ERROR` - Any problems

## ✅ You're Done!

Your bot is now running and:
1. Collecting all events (speeding + 6 performance types)
2. Storing them in JSON
3. Generating daily Excel reports
4. Ready to send on-demand with `/getid`

## 🆘 Common Issues

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError: openpyxl` | Run: `pip install openpyxl` |
| `Missing required environment variables` | Check `.env` file has all 5 lines |
| `Bot not receiving events` | Wait 5+ minutes, check `safetybot.log` |
| No response to `/getid` | Make sure chat ID in `.env` matches |
| Excel file is empty | Wait for events to occur (5+ minutes) |

## 📞 Need Details?

- Full docs: See `README.md`
- Setup help: See `SETUP_GUIDE.md`
- All changes: See `CHANGELOG.md` and `IMPLEMENTATION_SUMMARY.md`

---

**That's it!** Your SafetyBot v3.0 is ready. 🎉
