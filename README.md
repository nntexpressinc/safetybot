# SafetyBot - GoMotive APIs to Telegram Monitor with Excel Reports

A Python bot that monitors both GoMotive Speeding Events (v1) and Driver Performance Events (v2) APIs and sends alerts to Telegram with videos AND automatically generates daily Excel reports.

## Features

- Monitors two GoMotive APIs every 5 minutes:
  - **Speeding Events API (v1)**: Vehicle speed violations with speed range and exceeded amounts
  - **Driver Performance Events API (v2)**: Safety events with camera videos
- Sends formatted alerts to Telegram
- **NEW: Automatically stores event data to JSON** for later reporting
- **NEW: Generates professional Excel reports daily at 11:59 PM** with:
  - Event type (Speeding, Hard Brake, Crash, etc.)
  - Driver's full name
  - Date & time of event
  - Speed range (for speeding events)
  - Exceeded by value (for speeding events)
  - Severity level
- **NEW: /getexcel command** - send today's report on-demand from Telegram
- Downloads and sends both front-facing and driver-facing camera videos
- Tracks last processed event IDs separately for each API to avoid duplicates
- Comprehensive logging and error handling
- Designed to run as a service on Ubuntu

## Supported Event Types

### Speeding Events (v1 API)
- Vehicle speed violations with detailed speed information

### Driver Performance Events (v2 API)  
- hard_brake
- crash
- seat_belt_violation
- stop_sign_violation
- distraction
- unsafe_lane_change

## Excel Report Structure

Each daily Excel report contains:

| Column | Content | Example |
|--------|---------|---------|
| 1 | Event Type | Speeding, Hard Brake, Crash, etc. |
| 2 | Driver Name | John Smith |
| 3 | Date & Time | 09/25/2024 12:37 PM |
| 4 | Speed Range | 62.1–72.5 mph (speeding only) |
| 5 | Exceeded By | +8.7 mph (speeding only) |
| 6 | Severity | medium, high, critical |

Reports are automatically sent to Telegram at 11:59 PM each day and can be requested on-demand using `/getexcel`.

## Message Formats

### Speeding Events (Telegram)
```
Speeding Alert
Driver: John Smith
Vehicle: 086
09/25/2024 12:37 PM
Speed Range: 62.1–72.5 mph
Exceeded By: +8.7 mph
Severity: high
```

### Driver Performance Events (Telegram)
```
Hard Brake
Driver: John Smith
Vehicle: 118
09/25/2024 12:37 PM
Severity: medium
```
*(Sent as caption under both front-facing and driver-facing videos)*

## Prerequisites

- Ubuntu 18.04+ (or any Linux distribution with systemd)
- Python 3.8+
- Internet connection
- GoMotive API key
- Telegram Bot token and chat ID

## Installation

1. **Upload files to your Ubuntu server:**
   ```bash
   # Copy all files to your server, e.g., /home/ubuntu/safetybot/
   ```

2. **Make the startup script executable:**
   ```bash
   chmod +x start_bot.sh
   ```

3. **Run the setup script:**
   ```bash
   ./start_bot.sh
   ```

The startup script will:
- Check for Python 3 and pip
- Create a virtual environment
- Install all required dependencies (including openpyxl for Excel generation)
- Start the bot

## Configuration

The bot is configured through the `.env` file:

```env
# GoMotive API Configuration
API_KEY=your_gomotive_api_key_here
API_BASE_URL=https://api.gomotive.com/v2

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here

# Bot Configuration
CHECK_INTERVAL=300  # 5 minutes in seconds
```

### Getting Telegram Credentials

1. **Create a Telegram Bot:**
   - Message @BotFather on Telegram
   - Send `/newbot` and follow instructions
   - Save the bot token

2. **Get Chat ID:**
   - Add your bot to a group or start a private chat
   - Send a message to the bot
   - Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   - Find your chat ID in the response

## Running as a Service

To run the bot as a systemd service:

1. **Edit the service file:**
   ```bash
   sudo nano safetybot.service
   ```
   
   Update the paths to match your installation directory:
   ```ini
   WorkingDirectory=/home/ubuntu/safetybot
   Environment=PATH=/home/ubuntu/safetybot/venv/bin
   ExecStart=/home/ubuntu/safetybot/venv/bin/python /home/ubuntu/safetybot/safetybot.py
   ```

2. **Install the service:**
   ```bash
   sudo cp safetybot.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable safetybot.service
   ```

3. **Start the service:**
   ```bash
   sudo systemctl start safetybot.service
   ```

4. **Check service status:**
   ```bash
   sudo systemctl status safetybot.service
   ```

5. **View logs:**
   ```bash
   sudo journalctl -u safetybot.service -f
   ```

## Manual Operation

To run the bot manually:

```bash
# Activate virtual environment
source venv/bin/activate

# Run the bot
python3 safetybot.py
```

## Commands

### /getexcel

In Telegram, type `/getexcel@nntexpressinc_safety_bot` (or `@your_bot_name`) to get today's Excel report on-demand.

The bot will:
1. Generate an Excel file with all events from today
2. Send it to the Telegram group/chat
3. Automatically clean up the temporary file

## Monitoring

The bot creates detailed logs in:
- `safetybot.log` - Application logs
- `events_data/` directory - Daily JSON files with event data (e.g., `events_2024-09-25.json`)
- Console output - Real-time status
- systemd journal (if running as service)

## File Structure

```
safetybot/
├── safetybot.py              # Main bot application
├── requirements.txt          # Python dependencies
├── .env                      # Configuration file (create manually)
├── start_bot.sh             # Ubuntu startup script
├── safetybot.service        # Systemd service file
├── README.md                # This file
├── safetybot.log            # Application logs (created when running)
├── events_data/             # Daily event data in JSON format (created when running)
│   ├── events_2024-09-25.json
│   ├── events_2024-09-26.json
│   └── ...
├── last_*_event_id.txt      # Event tracking files (created when running)
└── venv/                    # Virtual environment (created by setup)
```

## Troubleshooting

### Common Issues

1. **Import Errors:**
   - Ensure virtual environment is activated
   - Install requirements: `pip install -r requirements.txt`

2. **API Connection Issues:**
   - Verify API key is correct
   - Check internet connectivity
   - Ensure GoMotive API is accessible

3. **Telegram Issues:**
   - Verify bot token and chat ID
   - Ensure bot has permission to send messages
   - Check Telegram API connectivity

4. **Performance Events Not Showing:**
   - Check if events have medium/high/critical severity (events with low severity are filtered)
   - Verify the API is returning data: check `safetybot.log` for fetch status
   - Ensure media_required=true is being honored by the API

5. **Excel Generation Issues:**
   - Ensure `openpyxl` is installed: `pip install openpyxl==3.10.1`
   - Check file permissions in the `events_data/` directory
   - Verify temp directory has sufficient space

6. **Permission Issues:**
   - Ensure proper file permissions
   - Run with appropriate user privileges

### Logs

Check the logs for detailed error information:
```bash
tail -f safetybot.log
```

For systemd service:
```bash
sudo journalctl -u safetybot.service -f
```

### Debugging Event Issues

To see what events are being stored:
```bash
# View today's events
cat events_data/events_$(date +%Y-%m-%d).json

# View events with pretty formatting
cat events_data/events_$(date +%Y-%m-%d).json | python -m json.tool
```

## Security Notes

- Keep your `.env` file secure and never commit it to version control
- The API key and bot token should be treated as sensitive credentials
- Consider running the bot with a dedicated user account
- Regularly monitor the logs for any suspicious activity
- Excel files are stored in system temp directory and automatically deleted after sending

## Customization

You can modify the bot behavior by editing `safetybot.py`:

- Change message formatting in `format_speeding_message()` and `format_performance_message()`
- Adjust event filtering in `filter_new_performance_events()`
- Modify check interval in `.env` file
- Change daily report time from 11:59 PM: edit `schedule.every().day.at("23:59")` in `run_scheduler()`
- Add additional event processing logic in `store_event()`

## Version History

### v2.2 - Excel Reports Edition (Current)
- Added Excel report generation
- Added daily 11:59 PM automatic reports
- Added `/getexcel` command for on-demand reports
- Added JSON event storage system
- Enhanced event tracking per event type

### v2.1 - Production Ready
- Separate ID tracking for each event type
- Improved error handling

## Support

For issues or questions:
1. Check the logs for error details
2. Verify configuration in `.env` file
3. Test API connectivity manually
4. Ensure all dependencies are installed correctly
5. Review the "Troubleshooting" section above