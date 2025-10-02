# SafetyBot - GoMotive APIs to Telegram Monitor

A Python bot that monitors both GoMotive Speeding Events (v1) and Driver Performance Events (v2) APIs and sends alerts to Telegram with videos.

## Features

- Monitors two GoMotive APIs every 5 minutes:
  - **Speeding Events API (v1)**: Vehicle speed violations with speed range and exceeded amounts
  - **Driver Performance Events API (v2)**: Safety events with camera videos
- Sends formatted alerts to Telegram
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

## Message Formats

### Speeding Events
```
Speeding
🚚: 086
Sep 25 12:37 AM
Vehicle speed range: 62.1–72.5 mph
Avg. exceeded: +8.7 mph
```

### Driver Performance Events  
```
Hard Braking
🚚: 118
Sep 25 12:37 AM
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
- Install all required dependencies
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
LAST_EVENT_FILE=last_event_id.txt
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

## Monitoring

The bot creates detailed logs in:
- `safetybot.log` - Application logs
- Console output - Real-time status
- systemd journal (if running as service)

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

4. **Permission Issues:**
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

## File Structure

```
safetybot/
├── safetybot.py          # Main bot application
├── requirements.txt      # Python dependencies
├── .env                  # Configuration file
├── start_bot.sh         # Ubuntu startup script
├── safetybot.service    # Systemd service file
├── README.md            # This file
├── safetybot.log        # Application logs (created when running)
├── last_event_id.txt    # Last processed event ID (created when running)
└── venv/                # Virtual environment (created by setup)
```

## Security Notes

- Keep your `.env` file secure and never commit it to version control
- The API key and bot token should be treated as sensitive credentials
- Consider running the bot with a dedicated user account
- Regularly monitor the logs for any suspicious activity

## Customization

You can modify the bot behavior by editing `safetybot.py`:

- Change message formatting in `format_event_message()`
- Adjust event filtering in `filter_new_events()`
- Modify check interval in `.env` file
- Add additional event processing logic

## Support

For issues or questions:
1. Check the logs for error details
2. Verify configuration in `.env` file
3. Test API connectivity manually
4. Ensure all dependencies are installed correctly