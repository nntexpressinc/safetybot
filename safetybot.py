#!/usr/bin/env python3
"""
Safety Bot - GoMotive APIs to Telegram Bot with Excel Reporting
Monitors speeding and driver performance events and generates daily Excel reports
"""

import os
import sys
import time
import json
import asyncio
import logging
import requests
import tempfile
import uuid
import signal
import atexit
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set, Tuple
from dotenv import load_dotenv
import schedule
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.error import TelegramError, NetworkError, TimedOut
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# Load environment variables
load_dotenv()

# Configure logging with proper encoding
def setup_logging():
    """Set up logging with Unicode support and fallback"""
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    file_handler = logging.FileHandler('safetybot.log', encoding='utf-8')
    file_handler.setFormatter(formatter)
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass
    
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

logger = setup_logging()

def log_safe(level, message):
    """Safe logging function that handles Unicode issues"""
    try:
        getattr(logger, level)(message)
    except UnicodeEncodeError:
        safe_message = message.encode('ascii', 'ignore').decode('ascii')
        getattr(logger, level)(safe_message)

class SafetyBot:
    """Main bot class for monitoring GoMotive APIs and generating Excel reports"""
    
    ALLOWED_EVENT_TYPES = [
        'hard_brake', 'crash', 'seat_belt_violation', 'stop_sign_violation',
        'distraction', 'unsafe_lane_change'
    ]
    
    # Constraints
    MAX_VIDEO_SIZE_MB = 20
    VIDEO_DOWNLOAD_TIMEOUT = 90  # seconds
    TELEGRAM_SEND_TIMEOUT = 30  # seconds
    MAX_QUEUE_SIZE = 50
    
    def __init__(self):
        """Initialize the bot with configuration from environment variables"""
        self.api_key = os.getenv('API_KEY')
        self.api_base_url = os.getenv('API_BASE_URL')
        self.telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.check_interval = int(os.getenv('CHECK_INTERVAL', 300))
        
        # Health monitoring
        self.last_successful_check = None
        self.consecutive_failures = 0
        self.max_consecutive_failures = 5
        self.critical_alert_sent = False
        
        # Event tracking files
        self.last_performance_event_file = 'last_performance_event_id.txt'
        self.last_speeding_event_file = 'last_speeding_event_id.txt'
        
        self.performance_event_files = {
            event_type: f'last_{event_type}_event_id.txt'
            for event_type in self.ALLOWED_EVENT_TYPES
        }
        
        # Deduplication within current cycle
        self.processed_event_ids: Set[int] = set()
        
        # Excel data storage - stores events for the current day
        self.daily_events: List[Dict[str, Any]] = []
        self.current_date = datetime.now().date()
        
        # Concurrency and shutdown control
        self.is_processing = False
        self.running = True
        self.shutdown_lock = threading.Lock()
        
        # Validate and initialize
        self._validate_config()
        self.telegram_bot = Bot(token=self.telegram_token)
        self._init_session()
        
        # Register cleanup handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        atexit.register(self._cleanup)
        
        logger.info("SafetyBot with Excel reporting initialized successfully")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        log_safe('info', f"Received signal {signum}, initiating graceful shutdown...")
        with self.shutdown_lock:
            self.running = False
    
    def _cleanup(self):
        """Clean up resources on exit"""
        try:
            with self.shutdown_lock:
                self.running = False
            
            if hasattr(self, 'session'):
                self.session.close()
            logger.info("Cleanup completed successfully")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def _init_session(self):
        """Initialize requests session with retry strategy"""
        self.headers = {
            'accept': 'application/json',
            'x-api-key': self.api_key,
            'User-Agent': 'SafetyBot/3.0-Excel'
        }
        
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
    
    def _validate_config(self):
        """Validate required configuration"""
        required_vars = ['API_KEY', 'API_BASE_URL', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID']
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
    
    def _has_allowed_severity(self, event: Dict[str, Any]) -> bool:
        """Check if event has allowed severity"""
        metadata = event.get('metadata', {})
        severity = metadata.get('severity')
        return severity in ['medium', 'high', 'critical']
    
    def _is_already_processed(self, event_id: int) -> bool:
        """Check if event was already processed in this cycle"""
        return event_id in self.processed_event_ids
    
    def _mark_processed(self, event_id: int):
        """Mark event as processed in this cycle"""
        self.processed_event_ids.add(event_id)
    
    def _reset_cycle_tracking(self):
        """Reset deduplication tracking for new cycle"""
        self.processed_event_ids.clear()
    
    def get_last_processed_event_id(self, event_type='performance') -> int:
        """Get the ID of the last processed event"""
        try:
            file_path = self.last_performance_event_file if event_type == 'performance' else self.last_speeding_event_file
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    return int(f.read().strip())
        except (FileNotFoundError, ValueError) as e:
            logger.warning(f"Could not read last {event_type} event ID: {e}")
        return 0
    
    def save_last_processed_event_id(self, event_id: int, event_type='performance'):
        """Save the ID of the last processed event"""
        try:
            file_path = self.last_performance_event_file if event_type == 'performance' else self.last_speeding_event_file
            with open(file_path, 'w') as f:
                f.write(str(event_id))
            logger.info(f"[SAVE] Saved last {event_type} event ID: {event_id}")
        except Exception as e:
            logger.error(f"Failed to save last {event_type} event ID: {e}")
    
    def fetch_speeding_events(self) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """Fetch speeding events from API"""
        try:
            url = f"{self.api_base_url.replace('v2', 'v1')}/speeding_events"
            params = {
                'per_page': '25',
                'page_no': '1'
            }
            
            response = self.session.get(url, headers=self.headers, params=params, timeout=45)
            
            if response.status_code == 401:
                logger.error("[API] Authentication error - check API key")
                return None, "AUTH_ERROR"
            elif response.status_code == 403:
                logger.error("[API] Permission error - insufficient permissions")
                return None, "PERMISSION_ERROR"
            elif response.status_code == 404:
                logger.error("[API] Endpoint not found (404)")
                return None, "NOT_FOUND"
            elif response.status_code != 200:
                logger.error(f"[API] Speeding events error: {response.status_code}")
                return None, f"HTTP_{response.status_code}"
            
            data = response.json()
            events = data.get('speeding_events', [])
            logger.info(f"[API] Fetched {len(events)} speeding events")
            return events, None
            
        except requests.exceptions.Timeout:
            logger.error("[API] Timeout fetching speeding events")
            return None, "TIMEOUT"
        except requests.exceptions.RequestException as e:
            logger.error(f"[API] Request error: {e}")
            return None, "REQUEST_ERROR"
        except Exception as e:
            logger.error(f"[API] Unexpected error: {e}")
            return None, "UNEXPECTED_ERROR"
    
    def fetch_driver_performance_events(self) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """Fetch driver performance events from API"""
        all_events = []
        first_error = None
        
        for event_type in self.ALLOWED_EVENT_TYPES:
            try:
                params = {
                    'event_types': event_type,
                    'media_required': 'true',
                    'per_page': '25',
                    'page_no': '1'
                }
                
                url = f"{self.api_base_url}/driver_performance_events"
                logger.info(f"[API] Fetching {event_type} events")
                response = self.session.get(url, headers=self.headers, params=params, timeout=45)
                
                if response.status_code == 401:
                    logger.error(f"[API] Authentication error for {event_type}")
                    if not first_error:
                        first_error = "AUTH_ERROR"
                    continue
                elif response.status_code == 403:
                    logger.error(f"[API] Permission error for {event_type}")
                    if not first_error:
                        first_error = "PERMISSION_ERROR"
                    continue
                elif response.status_code == 404:
                    logger.error(f"[API] Endpoint not found for {event_type}")
                    if not first_error:
                        first_error = "NOT_FOUND"
                    continue
                elif response.status_code != 200:
                    logger.error(f"[API] Error fetching {event_type}: {response.status_code}")
                    continue
                
                data = response.json()
                events = data.get('driver_performance_events', [])
                logger.info(f"[API] Found {len(events)} {event_type} events")
                all_events.extend(events)
                
            except requests.exceptions.Timeout:
                logger.error(f"[API] Timeout fetching {event_type}")
            except requests.exceptions.RequestException as e:
                logger.error(f"[API] Request error for {event_type}: {e}")
            except Exception as e:
                logger.error(f"[API] Unexpected error for {event_type}: {e}")
            
            time.sleep(1)  # Rate limiting between event types
        
        logger.info(f"[API] Fetched {len(all_events)} total performance events")
        return all_events, first_error
    
    def filter_new_speeding_events(self, events: List[Dict]) -> List[Dict]:
        """Filter speeding events for new ones only"""
        if not events:
            return []
        
        last_id = self.get_last_processed_event_id('speeding')
        new_events = []
        max_id = last_id
        
        for event in events:
            event_id = event.get('id', 0)
            
            if event_id > last_id and not self._is_already_processed(event_id):
                if self._has_allowed_severity(event):
                    new_events.append(event)
                    max_id = max(max_id, event_id)
        
        if max_id > last_id:
            self.save_last_processed_event_id(max_id, 'speeding')
        
        return new_events
    
    def filter_new_performance_events(self, events: List[Dict]) -> List[Dict]:
        """Filter performance events for new ones with separate ID tracking per event type"""
        if not events:
            return []
        
        new_events = []
        event_type_max_ids = {}
        
        for event in events:
            event_id = event.get('id', 0)
            event_type = event.get('event_type', '')
            
            if event_type not in self.ALLOWED_EVENT_TYPES:
                continue
            
            last_id_file = self.performance_event_files.get(event_type)
            if not last_id_file:
                continue
            
            try:
                last_id = 0
                if os.path.exists(last_id_file):
                    with open(last_id_file, 'r') as f:
                        last_id = int(f.read().strip())
            except (FileNotFoundError, ValueError):
                last_id = 0
            
            if event_id > last_id and not self._is_already_processed(event_id):
                if self._has_allowed_severity(event):
                    new_events.append(event)
                    
                    if event_type not in event_type_max_ids:
                        event_type_max_ids[event_type] = event_id
                    else:
                        event_type_max_ids[event_type] = max(event_type_max_ids[event_type], event_id)
        
        for event_type, max_id in event_type_max_ids.items():
            last_id_file = self.performance_event_files.get(event_type)
            if last_id_file:
                try:
                    with open(last_id_file, 'w') as f:
                        f.write(str(max_id))
                    logger.info(f"[SAVE] Updated last {event_type} event ID: {max_id}")
                except Exception as e:
                    logger.error(f"[ERROR] Failed to save {event_type} event ID: {e}")
        
        return new_events
    
    def store_event_for_excel(self, event: Dict[str, Any], event_category: str):
        """Store event data for Excel report generation"""
        try:
            # Extract common fields
            event_id = event.get('id', 0)
            timestamp = event.get('timestamp', '')
            driver = event.get('driver', {})
            driver_name = driver.get('name', 'Unknown')
            vehicle = event.get('vehicle', {})
            vehicle_name = vehicle.get('name', 'Unknown')
            metadata = event.get('metadata', {})
            severity = metadata.get('severity', 'unknown')
            
            # Parse timestamp
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                formatted_time = timestamp
            
            # Prepare event data based on category
            if event_category == 'speeding':
                event_type = 'Speeding'
                speed_range = metadata.get('speed_range', '')
                exceeded_by = metadata.get('exceeded_by', '')
            else:
                # Performance events
                event_type_raw = event.get('event_type', '')
                # Convert event_type to human-readable format
                event_type = event_type_raw.replace('_', ' ').title()
                speed_range = ''
                exceeded_by = ''
            
            # Store event data
            event_data = {
                'event_type': event_type,
                'vehicle': vehicle_name,
                'driver_name': driver_name,
                'datetime': formatted_time,
                'speed_range': speed_range,
                'exceeded_by': exceeded_by,
                'severity': severity.title()
            }
            
            self.daily_events.append(event_data)
            logger.info(f"[EXCEL] Stored {event_type} event for {driver_name} in {vehicle_name}")
            
        except Exception as e:
            logger.error(f"[EXCEL] Error storing event: {e}")
    
    def generate_excel_report(self, filename: str = None) -> Optional[str]:
        """Generate Excel report from stored events"""
        try:
            if not self.daily_events:
                logger.info("[EXCEL] No events to report")
                return None
            
            # Create filename if not provided
            if not filename:
                date_str = datetime.now().strftime('%Y-%m-%d')
                filename = f"/mnt/user-data/outputs/safety_report_{date_str}.xlsx"
            
            # Create workbook
            wb = Workbook()
            ws = wb.active
            ws.title = "Safety Events"
            
            # Define headers
            headers = ['Event Type', 'Vehicle', 'Driver Name', 'Date & Time', 'Speed Range', 'Exceeded By', 'Severity']
            
            # Style for header row
            header_font = Font(bold=True, color='FFFFFF')
            header_fill = PatternFill(start_color='366092', end_color='366092', fill_type='solid')
            header_alignment = Alignment(horizontal='center', vertical='center')
            border = Border(
                left=Side(style='thin'),
                right=Side(style='thin'),
                top=Side(style='thin'),
                bottom=Side(style='thin')
            )
            
            # Write headers
            for col_idx, header in enumerate(headers, start=1):
                cell = ws.cell(row=1, column=col_idx, value=header)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = header_alignment
                cell.border = border
            
            # Write data rows
            for row_idx, event in enumerate(self.daily_events, start=2):
                ws.cell(row=row_idx, column=1, value=event['event_type']).border = border
                ws.cell(row=row_idx, column=2, value=event['vehicle']).border = border
                ws.cell(row=row_idx, column=3, value=event['driver_name']).border = border
                ws.cell(row=row_idx, column=4, value=event['datetime']).border = border
                ws.cell(row=row_idx, column=5, value=event['speed_range']).border = border
                ws.cell(row=row_idx, column=6, value=event['exceeded_by']).border = border
                ws.cell(row=row_idx, column=7, value=event['severity']).border = border
            
            # Adjust column widths
            ws.column_dimensions['A'].width = 20
            ws.column_dimensions['B'].width = 20
            ws.column_dimensions['C'].width = 25
            ws.column_dimensions['D'].width = 20
            ws.column_dimensions['E'].width = 15
            ws.column_dimensions['F'].width = 15
            ws.column_dimensions['G'].width = 12
            
            # Save workbook
            wb.save(filename)
            logger.info(f"[EXCEL] Report generated: {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"[EXCEL] Error generating report: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    async def send_daily_report(self):
        """Generate and send daily Excel report"""
        try:
            logger.info("[REPORT] Generating daily report...")
            
            # Check if there are events to report
            if not self.daily_events:
                logger.info("[REPORT] No events today, skipping report")
                # Send notification that no events occurred
                await self.telegram_bot.send_message(
                    chat_id=self.chat_id,
                    text=f"📊 Daily Safety Report - {datetime.now().strftime('%Y-%m-%d')}\n\nNo safety events recorded today. ✅"
                )
                return
            
            # Generate Excel file
            filename = self.generate_excel_report()
            
            if filename and os.path.exists(filename):
                # Send file to Telegram
                event_count = len(self.daily_events)
                caption = f"📊 Daily Safety Report - {datetime.now().strftime('%Y-%m-%d')}\n\nTotal Events: {event_count}"
                
                with open(filename, 'rb') as f:
                    await self.telegram_bot.send_document(
                        chat_id=self.chat_id,
                        document=f,
                        filename=os.path.basename(filename),
                        caption=caption
                    )
                
                logger.info(f"[REPORT] Daily report sent with {event_count} events")
                
                # Clear daily events for next day
                self.daily_events.clear()
                self.current_date = datetime.now().date()
            else:
                logger.error("[REPORT] Failed to generate report file")
                
        except Exception as e:
            logger.error(f"[REPORT] Error sending daily report: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def handle_getid_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /getid command to send today's report"""
        try:
            logger.info("[COMMAND] Received /getid command")
            
            # Check if there are events for today
            if not self.daily_events:
                await update.message.reply_text(
                    "📊 No safety events recorded today yet."
                )
                return
            
            # Generate temporary Excel file for today
            date_str = datetime.now().strftime('%Y-%m-%d')
            temp_filename = f"/tmp/safety_report_{date_str}_{uuid.uuid4().hex[:8]}.xlsx"
            
            # Generate report
            filename = self.generate_excel_report(temp_filename)
            
            if filename and os.path.exists(filename):
                event_count = len(self.daily_events)
                caption = f"📊 Safety Report (Today) - {date_str}\n\nTotal Events: {event_count}"
                
                with open(filename, 'rb') as f:
                    await update.message.reply_document(
                        document=f,
                        filename=f"safety_report_{date_str}.xlsx",
                        caption=caption
                    )
                
                # Clean up temp file
                os.remove(filename)
                logger.info(f"[COMMAND] Sent report with {event_count} events")
            else:
                await update.message.reply_text("❌ Failed to generate report")
                
        except Exception as e:
            logger.error(f"[COMMAND] Error handling /getid command: {e}")
            await update.message.reply_text("❌ Error generating report")
    
    def check_new_day(self):
        """Check if it's a new day and reset if needed"""
        today = datetime.now().date()
        if today != self.current_date:
            logger.info(f"[DAY] New day detected: {today}")
            self.daily_events.clear()
            self.current_date = today
    
    def process_new_events_sync(self):
        """Synchronous wrapper for event processing"""
        if self.is_processing:
            logger.warning("[SKIP] Previous check still running")
            return
        
        self.is_processing = True
        try:
            asyncio.run(self.process_new_events())
        finally:
            self.is_processing = False
    
    async def process_new_events(self):
        """Process new events from APIs and store them"""
        try:
            start_time = datetime.now()
            logger.info("="*60)
            logger.info(f"Starting event check at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("="*60)
            
            # Check if it's a new day
            self.check_new_day()
            
            # Reset cycle tracking
            self._reset_cycle_tracking()
            
            # Fetch and process speeding events
            logger.info("[FETCH] Fetching speeding events...")
            speeding_events, speed_error = self.fetch_speeding_events()
            
            if speed_error:
                logger.error(f"[ERROR] Speeding fetch error: {speed_error}")
            
            if speeding_events is not None:
                new_speeding = self.filter_new_speeding_events(speeding_events)
                if new_speeding:
                    logger.info(f"[PROCESS] Processing {len(new_speeding)} speeding events")
                    for event in new_speeding:
                        self._mark_processed(event.get('id', 0))
                        self.store_event_for_excel(event, 'speeding')
                        await asyncio.sleep(0.5)
                else:
                    logger.info("[PROCESS] No new speeding events")
            else:
                logger.warning("[FETCH] Failed to fetch speeding events")
            
            # Fetch and process performance events
            logger.info("[FETCH] Fetching performance events...")
            performance_events, perf_error = self.fetch_driver_performance_events()
            
            if perf_error:
                logger.error(f"[ERROR] Performance fetch error: {perf_error}")
            
            if performance_events is not None:
                new_performance = self.filter_new_performance_events(performance_events)
                if new_performance:
                    logger.info(f"[PROCESS] Processing {len(new_performance)} performance events")
                    for event in new_performance:
                        self._mark_processed(event.get('id', 0))
                        self.store_event_for_excel(event, 'performance')
                        await asyncio.sleep(0.5)
                else:
                    logger.info("[PROCESS] No new performance events")
            else:
                logger.warning("[FETCH] Failed to fetch performance events")
            
            # Update health
            self.last_successful_check = datetime.now()
            self.consecutive_failures = 0
            
            duration = (datetime.now() - start_time).total_seconds()
            logger.info("="*60)
            logger.info(f"Event check completed in {duration:.1f}s")
            logger.info(f"Total events stored today: {len(self.daily_events)}")
            logger.info("="*60)
            
        except Exception as e:
            logger.error(f"[CRITICAL] Unhandled error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.consecutive_failures += 1
    
    def run_scheduler(self):
        """Main scheduler loop"""
        # Schedule event checks
        schedule.every(self.check_interval).seconds.do(self.process_new_events_sync)
        logger.info(f"[SCHEDULER] Event check every {self.check_interval}s ({self.check_interval/60:.1f}m)")
        
        # Schedule daily report at 11:59 PM
        schedule.every().day.at("23:59").do(lambda: asyncio.run(self.send_daily_report()))
        logger.info("[SCHEDULER] Daily report scheduled for 23:59")
        
        # Run initial check
        logger.info("[STARTUP] Running initial event check...")
        self.process_new_events_sync()
        
        # Main loop
        logger.info("[STARTUP] SafetyBot v3.0 with Excel reporting is now monitoring")
        print("\n" + "="*60)
        print("SafetyBot v3.0 - Excel Reporting Edition")
        print(f"Check interval: {self.check_interval // 60} minutes")
        print(f"Daily report time: 23:59")
        print(f"Command: /getid@nntexpressinc_safety_bot")
        print("Press Ctrl+C to stop")
        print("="*60 + "\n")
        
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(10)
            except KeyboardInterrupt:
                logger.info("[SHUTDOWN] Bot stopped by user")
                break
            except Exception as e:
                logger.error(f"[ERROR] Scheduler loop error: {e}")
                time.sleep(30)
    
    async def setup_bot_commands(self):
        """Set up Telegram bot command handlers"""
        try:
            application = Application.builder().token(self.telegram_token).build()
            
            # Add command handler
            application.add_handler(CommandHandler("getid", self.handle_getid_command))
            
            # Start polling in background
            await application.initialize()
            await application.start()
            await application.updater.start_polling()
            
            logger.info("[BOT] Command handlers registered")
            
            # Keep the application running
            while self.running:
                await asyncio.sleep(1)
            
            # Cleanup
            await application.updater.stop()
            await application.stop()
            await application.shutdown()
            
        except Exception as e:
            logger.error(f"[BOT] Error setting up commands: {e}")
    
    def start(self):
        """Start the bot"""
        try:
            logger.info("[STARTUP] Testing connections...")
            asyncio.run(self._test_connections())
            
            # Start command handler in separate thread
            bot_thread = threading.Thread(target=lambda: asyncio.run(self.setup_bot_commands()), daemon=True)
            bot_thread.start()
            
            # Start the scheduler
            self.run_scheduler()
            
        except Exception as e:
            logger.error(f"[CRITICAL] Fatal error during startup: {e}")
            sys.exit(1)
    
    async def _test_connections(self):
        """Test API and Telegram connections"""
        try:
            logger.info("[TEST] Testing Telegram connection...")
            bot_info = await self.telegram_bot.get_me()
            logger.info(f"[TEST] Telegram OK: @{bot_info.username}")
            
            await self.telegram_bot.send_message(
                chat_id=self.chat_id,
                text="✅ SafetyBot v3.0 Excel Edition Started\nDaily reports at 23:59\nUse /getid@nntexpressinc_safety_bot for today's report",
                parse_mode='Markdown'
            )
            logger.info("[TEST] Startup message sent")
            
        except Exception as e:
            logger.error(f"[TEST] Connection test failed: {e}")
            raise

def main():
    """Main entry point"""
    try:
        bot = SafetyBot()
        bot.start()
    except KeyboardInterrupt:
        logger.info("[MAIN] Bot stopped by user")
    except Exception as e:
        logger.error(f"[MAIN] Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()