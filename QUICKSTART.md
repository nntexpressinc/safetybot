# SafetyBot v2.2 - Quick Start Guide

## ⚡ 5-Minute Setup

### 1. Install Excel Support
```bash
pip install openpyxl==3.10.1
```

### 2. Update the Bot
Replace your `safetybot.py` with the new v2.2 version.

### 3. Restart
```bash
# If using systemd service:
sudo systemctl restart safetybot.service

# If running manually:
# Press Ctrl+C to stop, then run again:
python3 safetybot.py
```

### 4. Done! ✓

## 🎯 What You Now Have

✅ Events stored as JSON in `events_data/`
✅ Excel reports generated daily at 11:59 PM  
✅ `/getexcel` command for on-demand reports
✅ All Telegram alerts still work

## 📝 Test It

**In Telegram, type:**
```
/getexcel@nntexpressinc_safety_bot
```

**Check the logs:**
```bash
tail -f safetybot.log | grep EXCEL
```

**View stored events:**
```bash
cat events_data/events_$(date +%Y-%m-%d).json | python3 -m json.tool
```

## 🆘 If Something Breaks

### openpyxl not found?
```bash
pip install openpyxl==3.10.1
```

### Bot won't start?
```bash
# Check for errors
python3 safetybot.py

# Read last 50 lines of logs
tail -50 safetybot.log
```

### /getexcel not working?
Make sure bot is added to the group/chat and has permission to send documents.

## 📚 Need More Help?

- **Setup Details:** See `EXCEL_SETUP_GUIDE.md`
- **Technical Changes:** See `CHANGES_SUMMARY.md`  
- **Complete Docs:** See `README.md`
- **What's New:** See `IMPLEMENTATION_COMPLETE.md`

## 🚀 Key Commands

```bash
# View today's events
cat events_data/events_$(date +%Y-%m-%d).json | python3 -m json.tool

# Watch Excel operations
tail -f safetybot.log | grep EXCEL

# Watch all commands
tail -f safetybot.log | grep COMMAND

# Check bot status
tail -20 safetybot.log
```

## 💡 Pro Tips

1. **Schedule reports at different time?**
   - Edit `safetybot.py` line ~960, change `"23:59"` to your preferred time
   - Restart bot

2. **Backup your data?**
   - Copy `events_data/` directory regularly

3. **Performance events not showing?**
   - Check: `tail -f safetybot.log | grep "ERROR\|performance"`
   - See troubleshooting in `EXCEL_SETUP_GUIDE.md`

## 📊 What Gets Exported

**Excel contains:**
- Event Type (Speeding, Hard Brake, Crash, etc.)
- Driver Name
- Date & Time  
- Speed Range (if speeding)
- Exceeded By (if speeding)
- Severity (medium, high, critical)

## ✨ That's It!

Your bot now stores data AND sends daily Excel reports.
Everything else works exactly as before.

For more details, see the documentation files! 📚 