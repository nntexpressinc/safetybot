# 📁 SafetyBot v2.2 - Files Guide

## Quick Navigation

### 🚀 **Start Here First**
- **[START_HERE.md](START_HERE.md)** ← Read this first! Complete overview and setup

### ⚡ **Fast Setup**
- **[QUICKSTART.md](QUICKSTART.md)** ← 5-minute deployment

### 📚 **All Documentation**
1. **[README.md](README.md)** - Complete reference documentation
2. **[EXCEL_SETUP_GUIDE.md](EXCEL_SETUP_GUIDE.md)** - Detailed Excel features & troubleshooting
3. **[CHANGES_SUMMARY.md](CHANGES_SUMMARY.md)** - Technical implementation details
4. **[IMPLEMENTATION_COMPLETE.md](IMPLEMENTATION_COMPLETE.md)** - What was built
5. **[FILES_GUIDE.md](FILES_GUIDE.md)** - This file

### 💻 **Core Application Files**
- **[safetybot.py](safetybot.py)** - Main bot application (1,043 lines)
- **[requirements.txt](requirements.txt)** - Python dependencies
- **[.env](/.env)** - Your configuration (create this)

### 🗂️ **Auto-Generated Files**
- **events_data/** - Event JSON storage (created when bot runs)
  - `events_2024-09-25.json` - Daily event records
  - etc.
- **safetybot.log** - Application logs
- **last_*_event_id.txt** - Event tracking files

### 🔧 **System Files**
- **safetybot.service** - systemd service file (Ubuntu/Linux)
- **start_bot.sh** - Startup script

---

## File Descriptions

### 📖 Documentation Files

#### START_HERE.md
**Read this first!**
- What you requested vs. what you got
- 3-step setup guide
- Testing procedures
- FAQ and common issues
- Quick learning path

#### QUICKSTART.md
**5-minute setup version**
- Minimal steps to get running
- Testing commands
- Quick troubleshooting

#### README.md
**Complete reference**
- Full feature list
- Installation guide
- Configuration details
- Service setup instructions
- Troubleshooting (detailed)
- Customization options
- Version history

#### EXCEL_SETUP_GUIDE.md
**Excel features deep dive**
- What's new in v2.2
- Excel file structure
- Installation steps
- Usage examples
- Debugging tips
- Customization options
- Performance considerations
- Security & privacy

#### CHANGES_SUMMARY.md
**Technical changes for v2.2**
- Code changes made
- New methods added
- Performance impact
- Backward compatibility
- Migration guide
- Storage examples
- Known limitations

#### IMPLEMENTATION_COMPLETE.md
**Complete overview**
- What was built
- How to deploy
- Testing procedures
- How to address performance event issues
- File structure after changes
- Verification checklist

#### FILES_GUIDE.md
**This file**
- Guide to all documentation
- File organization
- What each file does

---

### 💻 Application Files

#### safetybot.py
**The main bot application** (1,043 lines)

**What it does:**
- Fetches events from GoMotive APIs
- Sends alerts to Telegram
- Downloads and sends videos
- Stores events to JSON
- Generates Excel reports
- Handles /getexcel command
- Manages health checks
- Logs all operations

**New Methods Added (v2.2):**
- `store_event()` - Save events to JSON
- `generate_excel_report()` - Create Excel files
- `send_daily_excel_report()` - Send at 11:59 PM
- `handle_get_excel_command()` - Handle /getexcel

**Key Features:**
- 1,043 total lines (including comments)
- ~800 new lines for Excel functionality
- 100% backward compatible
- All existing features preserved

#### requirements.txt
**Python dependencies**

**Current packages:**
```
anyio==4.11.0
certifi==2025.8.3
cffi==2.0.0
... (other packages)
openpyxl==3.10.1  ← NEW for Excel
python-telegram-bot==22.5
requests==2.32.5
schedule==1.2.2
... (other packages)
```

**Install with:**
```bash
pip install -r requirements.txt
```

#### .env (Configuration)
**YOUR configuration file**

**Must contain:**
```env
API_KEY=your_gomotive_api_key
API_BASE_URL=https://api.gomotive.com/v2
TELEGRAM_BOT_TOKEN=your_telegram_token
TELEGRAM_CHAT_ID=your_chat_id
CHECK_INTERVAL=300
```

**Important:**
- Create this file manually
- Never commit to git
- Keep it secure
- Different per installation

---

### 📊 Auto-Generated Files

#### events_data/ Directory
**Event storage directory**

**What gets stored:**
- Daily JSON files: `events_2024-09-25.json`
- One file per day
- Contains all event details
- Used for Excel generation
- Kept as historical backup

**File structure:**
```json
[
  {
    "event_type": "Speeding",
    "driver_name": "John Smith",
    "date_time": "2024-09-25T12:37:00Z",
    "severity": "high",
    "speed_range": "62.1–72.5 mph",
    "exceeded_by": "+8.7 mph",
    "event_id": 12345
  }
]
```

#### safetybot.log
**Application log file**

**Contains:**
- All bot operations
- Errors and warnings
- Event fetching status
- Excel generation logs
- Command operations
- Timestamps for everything

**Log tags for filtering:**
- `[STORED]` - Event stored
- `[EXCEL]` - Excel operation
- `[EXCEL_SENT]` - Report sent
- `[COMMAND]` - /getexcel command
- `[ERROR]` - Error occurred
- `[SENT]` - Message sent to Telegram

**View logs:**
```bash
# Full log
tail -f safetybot.log

# Just Excel operations
tail -f safetybot.log | grep EXCEL

# Just errors
tail -f safetybot.log | grep ERROR
```

#### last_*_event_id.txt
**Event tracking files**

**Files created:**
- `last_speeding_event_id.txt`
- `last_hard_brake_event_id.txt`
- `last_crash_event_id.txt`
- `last_seat_belt_violation_event_id.txt`
- `last_distraction_event_id.txt`
- `last_unsafe_lane_change_event_id.txt`
- `last_stop_sign_violation_event_id.txt`

**Purpose:**
- Tracks last processed event for each type
- Prevents duplicate processing
- Persists across bot restarts
- Updated automatically

---

### 🔧 System Files

#### safetybot.service
**systemd service file for Ubuntu/Linux**

**What it does:**
- Defines bot as a system service
- Auto-start on system boot
- Manage with systemctl

**Install with:**
```bash
sudo cp safetybot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable safetybot.service
```

**Manage with:**
```bash
sudo systemctl start safetybot.service
sudo systemctl stop safetybot.service
sudo systemctl restart safetybot.service
sudo systemctl status safetybot.service
```

#### start_bot.sh
**Startup script**

**What it does:**
- Check for Python 3
- Create virtual environment
- Install dependencies
- Start the bot

**Run with:**
```bash
chmod +x start_bot.sh
./start_bot.sh
```

---

## File Organization

```
safetybot/
│
├── 📖 DOCUMENTATION (Read These)
│   ├── START_HERE.md                    ← Start here!
│   ├── QUICKSTART.md                    ← Fast setup
│   ├── README.md                        ← Complete guide
│   ├── EXCEL_SETUP_GUIDE.md            ← Excel details
│   ├── CHANGES_SUMMARY.md               ← Technical
│   ├── IMPLEMENTATION_COMPLETE.md      ← What was built
│   └── FILES_GUIDE.md                   ← This file
│
├── 💻 APPLICATION (Core Files)
│   ├── safetybot.py                     ← Main bot (1,043 lines)
│   ├── requirements.txt                 ← Dependencies
│   ├── .env                             ← YOUR config (create this)
│   ├── run_safetybot.py                 ← Alternative runner
│   └── ENHANCED_FEATURES.md             ← Previous features
│
├── 📊 DATA (Auto-Generated)
│   ├── events_data/
│   │   ├── events_2024-09-24.json
│   │   ├── events_2024-09-25.json
│   │   └── ... (one per day)
│   ├── safetybot.log                    ← Application logs
│   ├── last_speeding_event_id.txt
│   ├── last_hard_brake_event_id.txt
│   └── ... (tracking files)
│
├── 🔧 SYSTEM (System Integration)
│   ├── safetybot.service               ← Ubuntu systemd
│   ├── start_bot.sh                    ← Startup script
│   └── response_*.txt                  ← API responses (temp)
│
└── 🔧 ENVIRONMENT (Virtual Environment)
    ├── env/ or venv/                    ← Virtual environment
    │   ├── bin/ (Linux/Mac)
    │   ├── Scripts/ (Windows)
    │   └── lib/
    │       └── site-packages/
    │           └── ... (pip packages)
    └── env_example.txt                  ← Env template
```

---

## Reading Order

### For Quick Setup
1. **[START_HERE.md](START_HERE.md)** - 10 min read
2. **[QUICKSTART.md](QUICKSTART.md)** - 5 min read
3. Run setup, test with `/getexcel`

### For Complete Understanding
1. **[START_HERE.md](START_HERE.md)** - Overview
2. **[README.md](README.md)** - Complete reference
3. **[EXCEL_SETUP_GUIDE.md](EXCEL_SETUP_GUIDE.md)** - Deep dive
4. **[CHANGES_SUMMARY.md](CHANGES_SUMMARY.md)** - Technical details

### For Troubleshooting
1. Check **[QUICKSTART.md](QUICKSTART.md)** - Common fixes
2. Check **[EXCEL_SETUP_GUIDE.md](EXCEL_SETUP_GUIDE.md)** - Troubleshooting section
3. Check **[README.md](README.md)** - Full troubleshooting
4. Review **safetybot.log** for error details

### For Customization
1. **[EXCEL_SETUP_GUIDE.md](EXCEL_SETUP_GUIDE.md)** - Customization section
2. **[CHANGES_SUMMARY.md](CHANGES_SUMMARY.md)** - Code structure
3. Edit **safetybot.py** as needed

---

## Which File Do I Need?

| Question | Answer |
|----------|--------|
| How do I get started? | Read **START_HERE.md** |
| I want fast setup | Read **QUICKSTART.md** |
| What changed? | Read **CHANGES_SUMMARY.md** |
| How do I troubleshoot? | Read **EXCEL_SETUP_GUIDE.md** |
| I need complete docs | Read **README.md** |
| What gets stored? | Check **events_data/** |
| What went wrong? | Check **safetybot.log** |
| How do I customize? | See **EXCEL_SETUP_GUIDE.md** |

---

## File Sizes & Import Time

| File | Size | Purpose |
|------|------|---------|
| safetybot.py | 42 KB | Main application |
| README.md | 15 KB | Documentation |
| EXCEL_SETUP_GUIDE.md | 12 KB | Setup guide |
| START_HERE.md | 9 KB | Quick start |
| requirements.txt | <1 KB | Dependencies |

---

## Key Takeaways

**Documentation:**
- 5 comprehensive guides provided
- Each serves a different purpose
- Start with **START_HERE.md**

**Application:**
- Single **safetybot.py** file (1,043 lines)
- Fully backward compatible
- Includes all new Excel features

**Configuration:**
- Create **.env** file with your settings
- Never commit to git
- Used by all instances

**Storage:**
- **events_data/** created automatically
- Daily JSON files for backup
- Used for Excel generation

**Logs:**
- **safetybot.log** for debugging
- Contains all operations
- Use grep tags to filter

**System:**
- **safetybot.service** for Ubuntu/Linux
- **start_bot.sh** for quick setup
- Both optional but recommended

---

## Next Steps

1. **Read** → **START_HERE.md**
2. **Run** → `pip install openpyxl==3.10.1`
3. **Update** → Replace safetybot.py
4. **Restart** → `sudo systemctl restart safetybot.service`
5. **Test** → `/getexcel@nntexpressinc_safety_bot` in Telegram
6. **Monitor** → `tail -f safetybot.log`

---

**All files are ready. Begin with START_HERE.md!** 🚀
