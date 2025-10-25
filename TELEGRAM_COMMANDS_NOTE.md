# Telegram Commands & Known Limitations (v3.0)

## Issue: /getid Command Not Working

The `/getid` command handler is implemented in the code but currently **not active** because the bot uses the `schedule` library for its main loop instead of Telegram's `Application.run_polling()`.

### Why This Limitation Exists

- **Current Architecture**: Uses `schedule.every()` for periodic event checking (every 5 minutes)
- **Required for Commands**: Telegram commands need `Application.run_polling()` which blocks the main thread
- **Conflict**: Can't run both simultaneously in a single-threaded application

### Workaround #1: Check Files Directly (Easiest)

View stored events directly from the command line:

```bash
# List files
ls -la ~/safetybot/events_data/

# View today's JSON events
cat ~/safetybot/events_data/events_$(date +%Y-%m-%d).json

# View generated Excel reports
ls -la ~/safetybot/events_data/*.xlsx
```

### Workaround #2: Daily Excel (Automatic)

The bot **automatically** generates and sends Excel reports at **23:59 PM** every day to Telegram.

- No action needed - it happens automatically
- Contains ALL events for the day
- Professional formatting

### Workaround #3: Manual Excel Generation

You can also manually generate Excel from Python:

```python
from safetybot import SafetyBot
import asyncio
from datetime import datetime

bot = SafetyBot()
today = datetime.now().strftime('%Y-%m-%d')
events = bot.event_store.load_events(bot.event_store.get_today_file())
excel_path = bot.generate_excel_file(events, today)
print(f"Generated: {excel_path}")
```

## Future Enhancement (v3.1)

To enable `/getid` command, we would need to:

1. **Run bot in separate thread** with `Application.run_polling()`
2. **Keep scheduler in main thread** with `schedule.run_pending()`
3. **Share state** between threads safely with locks/queues
4. **Handle cleanup** when bot is stopped

This is more complex but feasible for a future update.

## What Works Now

✅ **Real-time event alerts** - Speeding and performance events sent immediately  
✅ **Event storage** - All events saved to JSON  
✅ **Daily Excel reports** - Automatically sent at 23:59  
✅ **Video attachments** - Included with performance events  
✅ **Rate limiting** - Prevents Telegram flood control

## What Doesn't Work Now

❌ **`/getid` command** - Needs different architecture  
❌ **Other Telegram commands** - Same limitation

---

**Status**: Workarounds available, full implementation planned for v3.1+
