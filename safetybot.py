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
from datetime import datetime, timedelta, time as dt_time
from typing import Dict, List, Optional, Any, Set, Tuple
from dotenv import load_dotenv
import schedule
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.error import TelegramError, NetworkError, TimedOut
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill
from collections import defaultdict

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
    """Main bot class for monitoring GoMotive APIs and sending Excel reports"""
    
    ALLOWED_EVENT_TYPES = [
        'hard_brake', 'crash', 'seat_belt_violation', 'stop_sign_violation',
        'distraction', 'unsafe_lane_change'
    ]
    
    # Event type display names
    EVENT_TYPE_NAMES = {
        'speeding': 'Speeding',
        'hard_brake': 'Hard Brake',
        'crash': 'Crash',
        'seat_belt_violation': 'Seat Belt Violation',
        'stop_sign_violation': 'Stop Sign Violation',
        'distraction': 'Distraction',
        'unsafe_lane_change': 'Unsafe Lane Change'
    }
    
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
        
        # Daily report time (default: 11:59 PM)
        self.daily_report_hour = int(os.getenv('DAILY_REPORT_HOUR', 23))
        self.daily_report_minute = int(os.getenv('DAILY_REPORT_MINUTE', 59))
        
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
        
        # Daily events storage - stores events for the current day
        # Structure: {date_str: [event_dict, ...]}
        self.daily_events: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.events_lock = threading.Lock()
        
        # Deduplication within current cycle
        self.processed_event_ids: Set[int] = set()
        
        # Concurrency and shutdown control
        self.is_processing = False
        self.running = True
        self.shutdown_lock = threading.Lock()
        
        # Validate and initialize
        self._validate_config()
        self.telegram_bot = Bot(token=self.telegram_token)
        self.application = None  # Will be initialized for command handling
        self._init_session()
        
        # Register cleanup handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        atexit.register(self._cleanup)
        
        logger.info("SafetyBot initialized successfully with Excel reporting")
    
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
            'User-Agent': 'SafetyBot/3.0'
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
        except Exception as e:
            logger.error(f"Could not save last {event_type} event ID: {e}")
    
    def get_last_specific_event_id(self, event_type: str) -> int:
        """Get last processed ID for specific event type"""
        try:
            file_path = self.performance_event_files.get(event_type)
            if file_path and os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    return int(f.read().strip())
        except (FileNotFoundError, ValueError) as e:
            logger.warning(f"Could not read last {event_type} event ID: {e}")
        return 0
    
    def save_last_specific_event_id(self, event_id: int, event_type: str):
        """Save last processed ID for specific event type"""
        try:
            file_path = self.performance_event_files.get(event_type)
            if file_path:
                with open(file_path, 'w') as f:
                    f.write(str(event_id))
        except Exception as e:
            logger.error(f"Could not save last {event_type} event ID: {e}")
    
    def store_event(self, event_data: Dict[str, Any]):
        """Store event data for daily report"""
        today = datetime.now().strftime('%Y-%m-%d')
        with self.events_lock:
            self.daily_events[today].append(event_data)
            logger.info(f"[STORE] Stored {event_data['event_type']} event. Total today: {len(self.daily_events[today])}")
    
    def get_today_events(self) -> List[Dict[str, Any]]:
        """Get all events for today"""
        today = datetime.now().strftime('%Y-%m-%d')
        with self.events_lock:
            return self.daily_events.get(today, []).copy()
    
    def clear_old_events(self):
        """Clear events older than today"""
        today = datetime.now().strftime('%Y-%m-%d')
        with self.events_lock:
            old_dates = [date for date in self.daily_events.keys() if date != today]
            for date in old_dates:
                del self.daily_events[date]
                logger.info(f"[CLEANUP] Cleared events for {date}")
    
    def create_excel_report(self, events: List[Dict[str, Any]], filename: str):
        """Create Excel report from events"""
        try:
            workbook = openpyxl.Workbook()
            sheet = workbook.active
            sheet.title = "Safety Events"
            
            # Define headers
            headers = ['Event Type', 'Driver Name', 'Date & Time', 'Speed Range', 'Exceeded By', 'Severity']
            
            # Style headers
            header_fill = PatternFill(start_color='366092', end_color='366092', fill_type='solid')
            header_font = Font(bold=True, color='FFFFFF', size=12)
            
            for col_num, header in enumerate(headers, 1):
                cell = sheet.cell(row=1, column=col_num, value=header)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal='center', vertical='center')
            
            # Add data rows
            for row_num, event in enumerate(events, 2):
                sheet.cell(row=row_num, column=1, value=event['event_type'])
                sheet.cell(row=row_num, column=2, value=event['driver_name'])
                sheet.cell(row=row_num, column=3, value=event['date_time'])
                sheet.cell(row=row_num, column=4, value=event.get('speed_range', ''))
                sheet.cell(row=row_num, column=5, value=event.get('exceeded_by', ''))
                sheet.cell(row=row_num, column=6, value=event['severity'])
                
                # Align cells
                for col in range(1, 7):
                    sheet.cell(row=row_num, column=col).alignment = Alignment(horizontal='left', vertical='center')
            
            # Adjust column widths
            column_widths = [20, 25, 20, 15, 15, 15]
            for col_num, width in enumerate(column_widths, 1):
                sheet.column_dimensions[openpyxl.utils.get_column_letter(col_num)].width = width
            
            # Save workbook
            workbook.save(filename)
            logger.info(f"[EXCEL] Created report with {len(events)} events: {filename}")
            return True
            
        except Exception as e:
            logger.error(f"[EXCEL] Failed to create Excel report: {e}")
            return False
    
    async def send_daily_report(self):
        """Generate and send daily Excel report"""
        try:
            logger.info("[REPORT] Generating daily report...")
            
            events = self.get_today_events()
            
            if not events:
                logger.info("[REPORT] No events to report today")
                await self.telegram_bot.send_message(
                    chat_id=self.chat_id,
                    text="📊 Daily Safety Report\n\n✅ No safety events recorded today.",
                    parse_mode='Markdown'
                )
                return
            
            # Create Excel file
            today = datetime.now().strftime('%Y-%m-%d')
            filename = f"/tmp/safety_report_{today}.xlsx"
            
            if self.create_excel_report(events, filename):
                # Send file to Telegram
                with open(filename, 'rb') as file:
                    await self.telegram_bot.send_document(
                        chat_id=self.chat_id,
                        document=file,
                        filename=f"Safety_Report_{today}.xlsx",
                        caption=f"📊 Daily Safety Report - {today}\n\nTotal Events: {len(events)}",
                        parse_mode='Markdown'
                    )
                
                logger.info(f"[REPORT] Daily report sent successfully with {len(events)} events")
                
                # Clean up file
                os.remove(filename)
                
                # Clear old events after sending report
                self.clear_old_events()
            else:
                logger.error("[REPORT] Failed to create Excel file")
                await self.telegram_bot.send_message(
                    chat_id=self.chat_id,
                    text="❌ Failed to generate daily report",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            logger.error(f"[REPORT] Failed to send daily report: {e}")
            try:
                await self.telegram_bot.send_message(
                    chat_id=self.chat_id,
                    text=f"❌ Error generating daily report: {str(e)[:100]}",
                    parse_mode='Markdown'
                )
            except:
                pass
    
    async def handle_getid_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /getid@nntexpressinc_safety_bot command"""
        try:
            logger.info(f"[COMMAND] Received /getid command from user {update.effective_user.id}")
            
            events = self.get_today_events()
            
            if not events:
                await update.message.reply_text(
                    "📊 Today's Safety Report\n\n✅ No safety events recorded today.",
                    parse_mode='Markdown'
                )
                return
            
            # Create Excel file
            today = datetime.now().strftime('%Y-%m-%d')
            filename = f"/tmp/safety_report_{today}_command.xlsx"
            
            if self.create_excel_report(events, filename):
                # Send file
                with open(filename, 'rb') as file:
                    await update.message.reply_document(
                        document=file,
                        filename=f"Safety_Report_{today}.xlsx",
                        caption=f"📊 Today's Safety Report - {today}\n\nTotal Events: {len(events)}",
                        parse_mode='Markdown'
                    )
                
                logger.info(f"[COMMAND] Report sent to user {update.effective_user.id}")
                
                # Clean up file
                os.remove(filename)
            else:
                await update.message.reply_text(
                    "❌ Failed to generate report",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            logger.error(f"[COMMAND] Error handling /getid command: {e}")
            try:
                await update.message.reply_text(
                    f"❌ Error: {str(e)[:100]}",
                    parse_mode='Markdown'
                )
            except:
                pass
    
    def fetch_speeding_events(self) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        """Fetch speeding events from GoMotive v1 API"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                params = {'per_page': '25', 'page_no': '1'}
                url = f"{self.api_base_url.replace('v2', 'v1')}/speeding_events"
                
                logger.info(f"[API] Fetching speeding events (attempt {attempt + 1}/{max_retries})")
                response = self.session.get(url, headers=self.headers, params=params, timeout=45)
                
                if response.status_code == 401:
                    logger.error("[API] Authentication failed (401)")
                    return None, "AUTH_ERROR"
                elif response.status_code == 403:
                    logger.error("[API] Permission denied (403)")
                    return None, "PERMISSION_ERROR"
                elif response.status_code == 404:
                    logger.error("[API] Endpoint not found (404)")
                    return None, "NOT_FOUND"
                
                response.raise_for_status()
                
                if not response.content:
                    logger.warning("[API] Empty response from speeding events")
                    return [], None
                
                data = response.json()
                events = data.get('speeding_events', [])
                
                if not isinstance(events, list):
                    logger.warning("[API] Unexpected data structure in response")
                    return [], None
                
                logger.info(f"[API] Fetched {len(events)} speeding events")
                return events, None
                
            except requests.exceptions.Timeout:
                logger.warning(f"[API] Timeout (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
            except Exception as e:
                logger.error(f"[API] Error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
        
        logger.error(f"[API] Failed after {max_retries} attempts")
        return None, "FETCH_ERROR"
    
    def fetch_driver_performance_events(self) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        """Fetch driver performance events from GoMotive v2 API"""
        all_events = []
        first_error = None
        
        for event_type in self.ALLOWED_EVENT_TYPES:
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    params = {
                        'event_types': event_type,
                        'media_required': 'true',
                        'per_page': '25',
                        'page_no': '1'
                    }
                    
                    url = f"{self.api_base_url}/driver_performance_events"
                    logger.info(f"[API] Fetching {event_type} events (attempt {attempt + 1}/{max_retries})")
                    response = self.session.get(url, headers=self.headers, params=params, timeout=45)
                    
                    if response.status_code == 401:
                        logger.error(f"[API] Authentication failed (401) for {event_type}")
                        if not first_error:
                            first_error = "AUTH_ERROR"
                        break
                    elif response.status_code == 403:
                        logger.error(f"[API] Permission denied (403) for {event_type}")
                        if not first_error:
                            first_error = "PERMISSION_ERROR"
                        break
                    elif response.status_code == 404:
                        logger.error(f"[API] Endpoint not found (404) for {event_type}")
                        if not first_error:
                            first_error = "NOT_FOUND"
                        break
                    
                    response.raise_for_status()
                    
                    if not response.content:
                        logger.warning(f"[API] Empty response for {event_type}")
                        break
                    
                    data = response.json()
                    events = data.get('driver_performance_events', [])
                    
                    if not isinstance(events, list):
                        logger.warning(f"[API] Unexpected data structure for {event_type}")
                        break
                    
                    logger.info(f"[API] Found {len(events)} {event_type} events")
                    all_events.extend(events)
                    break
                    
                except requests.exceptions.Timeout:
                    logger.warning(f"[API] Timeout for {event_type} (attempt {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                except Exception as e:
                    logger.error(f"[API] Error fetching {event_type}: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
            
            time.sleep(1)
        
        logger.info(f"[API] Fetched {len(all_events)} total performance events")
        return all_events, first_error
    
    def filter_new_speeding_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter speeding events to only return new ones"""
        if not events:
            return []
        
        last_id = self.get_last_processed_event_id('speeding')
        new_events = []
        
        for event_data in events:
            event = event_data.get('speeding_event', {})
            event_id = event.get('id', 0)
            
            if event_id <= last_id:
                continue
            
            if self._is_already_processed(event_id):
                continue
            
            if not self._has_allowed_severity(event):
                logger.debug(f"[FILTER] Skipping speeding event {event_id} - severity not allowed")
                continue
            
            new_events.append(event)
        
        if new_events:
            new_events.sort(key=lambda x: x.get('id', 0))
            max_id = max(e.get('id', 0) for e in new_events)
            self.save_last_processed_event_id(max_id, 'speeding')
            logger.info(f"[FILTER] Found {len(new_events)} new speeding events. Updated last ID to {max_id}")
        
        return new_events
    
    def filter_new_performance_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter performance events by type and return new ones"""
        if not events:
            return []
        
        new_events = []
        events_by_type = {}
        
        # Group events by type
        for event_data in events:
            event = event_data.get('driver_performance_event', {})
            event_type = event.get('type', '')
            if event_type in self.ALLOWED_EVENT_TYPES:
                if event_type not in events_by_type:
                    events_by_type[event_type] = []
                events_by_type[event_type].append(event)
        
        # Process each event type separately
        for event_type, type_events in events_by_type.items():
            last_id = self.get_last_specific_event_id(event_type)
            
            for event in type_events:
                event_id = event.get('id', 0)
                
                if event_id <= last_id:
                    continue
                
                if self._is_already_processed(event_id):
                    continue
                
                if not self._has_allowed_severity(event):
                    logger.debug(f"[FILTER] Skipping {event_type} event {event_id} - severity not allowed")
                    continue
                
                new_events.append(event)
            
            # Update last ID for this event type
            if type_events:
                type_events_sorted = sorted(type_events, key=lambda x: x.get('id', 0))
                max_id = type_events_sorted[-1].get('id', 0)
                if max_id > last_id:
                    self.save_last_specific_event_id(max_id, event_type)
                    logger.info(f"[FILTER] Updated last {event_type} ID to {max_id}")
        
        logger.info(f"[FILTER] Found {len(new_events)} new performance events across {len(events_by_type)} types")
        return new_events
    
    def format_speeding_event_for_storage(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Format speeding event data for storage"""
        try:
            metadata = event.get('metadata', {})
            driver = event.get('driver', {})
            
            # Get driver name
            driver_name = f"{driver.get('first_name', '')} {driver.get('last_name', '')}".strip() or 'Unknown Driver'
            
            # Get timestamp
            timestamp = event.get('start_time', '')
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                formatted_time = timestamp
            
            # Get speed info - convert from kph to mph
            min_speed_kph = event.get('min_vehicle_speed', 0)
            max_speed_kph = event.get('max_vehicle_speed', 0)
            avg_exceeded_kph = event.get('avg_over_speed_in_kph', 0)
            
            min_speed_mph = round(min_speed_kph * 0.621371, 1) if min_speed_kph else 0
            max_speed_mph = round(max_speed_kph * 0.621371, 1) if max_speed_kph else 0
            avg_exceeded_mph = round(avg_exceeded_kph * 0.621371, 1) if avg_exceeded_kph else 0
            
            speed_range = f"{min_speed_mph}–{max_speed_mph} mph"
            exceeded_by = f"+{avg_exceeded_mph} mph"
            
            severity = metadata.get('severity', 'unknown').capitalize()
            
            return {
                'event_type': 'Speeding',
                'driver_name': driver_name,
                'date_time': formatted_time,
                'speed_range': speed_range,
                'exceeded_by': exceeded_by,
                'severity': severity
            }
        except Exception as e:
            logger.error(f"[FORMAT] Error formatting speeding event: {e}")
            return None
    
    def format_performance_event_for_storage(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Format performance event data for storage"""
        try:
            metadata = event.get('metadata', {})
            driver = event.get('driver', {})
            event_type = event.get('type', 'unknown')
            
            # Get driver name
            driver_name = f"{driver.get('first_name', '')} {driver.get('last_name', '')}".strip() or 'Unknown Driver'
            
            # Get timestamp
            timestamp = event.get('end_time', '')
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                formatted_time = timestamp
            
            # Get severity
            severity = metadata.get('severity', 'unknown').capitalize()
            
            # Get display name for event type
            event_type_display = self.EVENT_TYPE_NAMES.get(event_type, event_type.replace('_', ' ').title())
            
            return {
                'event_type': event_type_display,
                'driver_name': driver_name,
                'date_time': formatted_time,
                'speed_range': '',  # Not applicable for performance events
                'exceeded_by': '',  # Not applicable for performance events
                'severity': severity
            }
        except Exception as e:
            logger.error(f"[FORMAT] Error formatting performance event: {e}")
            return None
    
    def process_new_events_sync(self):
        """Synchronous wrapper for event processing"""
        if self.is_processing:
            logger.warning("[PROCESS] Already processing events, skipping this cycle")
            return
        
        try:
            self.is_processing = True
            asyncio.run(self.process_new_events())
        finally:
            self.is_processing = False
    
    async def process_new_events(self):
        """Main event processing logic - stores events instead of sending them"""
        if not self.running:
            return
        
        start_time = datetime.now()
        logger.info("="*60)
        logger.info(f"Starting event check at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("="*60)
        
        try:
            self._reset_cycle_tracking()
            
            # Fetch and process speeding events
            logger.info("[FETCH] Fetching speeding events...")
            speeding_events, speed_error = self.fetch_speeding_events()
            
            if speed_error:
                logger.error(f"[ERROR] Speeding fetch error: {speed_error}")
                if speed_error in ["AUTH_ERROR", "PERMISSION_ERROR"]:
                    if not self.critical_alert_sent:
                        try:
                            await self.telegram_bot.send_message(
                                chat_id=self.chat_id,
                                text=f"🚨 CRITICAL: API Authentication/Permission Error\n\nError: {speed_error}\n\nCheck API key and permissions.",
                                parse_mode='Markdown'
                            )
                            self.critical_alert_sent = True
                            logger.error("[ALERT] Sent critical API error alert")
                        except Exception as e:
                            logger.error(f"[ERROR] Failed to send alert: {e}")
            
            if speeding_events is not None:
                new_speeding = self.filter_new_speeding_events(speeding_events)
                if new_speeding:
                    logger.info(f"[PROCESS] Storing {len(new_speeding)} speeding events")
                    for event in new_speeding:
                        self._mark_processed(event.get('id', 0))
                        event_data = self.format_speeding_event_for_storage(event)
                        if event_data:
                            self.store_event(event_data)
                else:
                    logger.info("[PROCESS] No new speeding events")
            else:
                logger.warning("[FETCH] Failed to fetch speeding events")
            
            # Fetch and process performance events
            logger.info("[FETCH] Fetching performance events...")
            performance_events, perf_error = self.fetch_driver_performance_events()
            
            if perf_error:
                logger.error(f"[ERROR] Performance fetch error: {perf_error}")
                if perf_error in ["AUTH_ERROR", "PERMISSION_ERROR"]:
                    if not self.critical_alert_sent:
                        try:
                            await self.telegram_bot.send_message(
                                chat_id=self.chat_id,
                                text=f"🚨 CRITICAL: API Authentication/Permission Error\n\nError: {perf_error}\n\nCheck API key and permissions.",
                                parse_mode='Markdown'
                            )
                            self.critical_alert_sent = True
                            logger.error("[ALERT] Sent critical API error alert")
                        except Exception as e:
                            logger.error(f"[ERROR] Failed to send alert: {e}")
            
            if performance_events is not None:
                new_performance = self.filter_new_performance_events(performance_events)
                if new_performance:
                    logger.info(f"[PROCESS] Storing {len(new_performance)} performance events")
                    for event in new_performance:
                        self._mark_processed(event.get('id', 0))
                        event_data = self.format_performance_event_for_storage(event)
                        if event_data:
                            self.store_event(event_data)
                else:
                    logger.info("[PROCESS] No new performance events")
            else:
                logger.warning("[FETCH] Failed to fetch performance events")
            
            # Update health
            self.last_successful_check = datetime.now()
            self.consecutive_failures = 0
            self.critical_alert_sent = False
            
            duration = (datetime.now() - start_time).total_seconds()
            logger.info("="*60)
            logger.info(f"Event check completed in {duration:.1f}s")
            logger.info(f"Total events stored today: {len(self.get_today_events())}")
            logger.info("="*60)
            
        except Exception as e:
            logger.error(f"[CRITICAL] Unhandled error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.consecutive_failures += 1
            logger.warning(f"[HEALTH] Consecutive failures: {self.consecutive_failures}/{self.max_consecutive_failures}")
            
            if self.consecutive_failures >= self.max_consecutive_failures and not self.critical_alert_sent:
                try:
                    await self.telegram_bot.send_message(
                        chat_id=self.chat_id,
                        text=f"🚨 CRITICAL: SafetyBot encountered {self.consecutive_failures} consecutive failures\n\nError: {str(e)[:100]}\n\nPlease check logs.",
                        parse_mode='Markdown'
                    )
                    self.critical_alert_sent = True
                    logger.error("[ALERT] Sent consecutive failures alert")
                except Exception as e2:
                    logger.error(f"[ERROR] Failed to send critical alert: {e2}")
    
    async def health_check(self):
        """Perform health check and send status"""
        try:
            logger.info("[HEALTH] Running health check...")
            
            # Test API connectivity
            speeding_test, _ = self.fetch_speeding_events()
            performance_test, _ = self.fetch_driver_performance_events()
            apis_ok = (speeding_test is not None and performance_test is not None)
            
            # Test Telegram connectivity
            telegram_ok = False
            try:
                await self.telegram_bot.get_me()
                telegram_ok = True
            except Exception as e:
                logger.error(f"[HEALTH] Telegram check failed: {e}")
            
            # Determine overall status
            overall_ok = apis_ok and telegram_ok
            status = "✅ Healthy" if overall_ok else "❌ Issues Detected"
            
            last_check_str = "Never" if not self.last_successful_check else f"{(datetime.now() - self.last_successful_check).total_seconds() / 60:.1f}m ago"
            
            today_events = len(self.get_today_events())
            
            health_msg = f"""📊 Health Report
Status: {status}
Last Check: {last_check_str}
Failures: {self.consecutive_failures}
API: {'✅ OK' if apis_ok else '❌ FAILED'}
Telegram: {'✅ OK' if telegram_ok else '❌ FAILED'}
Events Today: {today_events}
Interval: {self.check_interval // 60}m
Version: 3.0 Excel"""
            
            await self.telegram_bot.send_message(
                chat_id=self.chat_id,
                text=health_msg,
                parse_mode='Markdown'
            )
            
            logger.info(f"[HEALTH] Report sent - Status: {status}")
            
        except Exception as e:
            logger.error(f"[HEALTH] Health check failed: {e}")
    
    def schedule_daily_report(self):
        """Schedule the daily report to be sent"""
        schedule_time = f"{self.daily_report_hour:02d}:{self.daily_report_minute:02d}"
        schedule.every().day.at(schedule_time).do(lambda: asyncio.run(self.send_daily_report()))
        logger.info(f"[SCHEDULER] Daily report scheduled for {schedule_time}")
    
    async def setup_bot_commands(self):
        """Set up bot command handlers"""
        try:
            self.application = Application.builder().token(self.telegram_token).build()
            
            # Add command handler
            self.application.add_handler(CommandHandler("getid", self.handle_getid_command))
            
            # Initialize and start the application
            await self.application.initialize()
            await self.application.start()
            
            logger.info("[BOT] Command handlers set up successfully")
            
        except Exception as e:
            logger.error(f"[BOT] Failed to set up commands: {e}")
    
    def run_command_handler(self):
        """Run the command handler in a separate thread"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(self.setup_bot_commands())
            loop.run_until_complete(self.application.updater.start_polling())
            loop.run_forever()
        except Exception as e:
            logger.error(f"[BOT] Command handler error: {e}")
        finally:
            loop.close()
    
    def run_scheduler(self):
        """Main scheduler loop - runs in main thread"""
        # Schedule event checks
        schedule.every(self.check_interval).seconds.do(self.process_new_events_sync)
        logger.info(f"[SCHEDULER] Event check every {self.check_interval}s ({self.check_interval/60:.1f}m)")
        
        # Schedule daily report
        self.schedule_daily_report()
        
        # Schedule health checks
        schedule.every().hour.do(lambda: asyncio.run(self.health_check()))
        logger.info("[SCHEDULER] Health check every hour")
        
        # Start command handler in separate thread
        command_thread = threading.Thread(target=self.run_command_handler, daemon=True)
        command_thread.start()
        logger.info("[BOT] Command handler thread started")
        
        # Run initial check
        logger.info("[STARTUP] Running initial event check...")
        self.process_new_events_sync()
        
        # Main loop
        logger.info("[STARTUP] SafetyBot v3.0 Excel is now monitoring")
        print("\n" + "="*60)
        print("SafetyBot v3.0 - Excel Reporting")
        print(f"Check interval: {self.check_interval // 60} minutes")
        print(f"Daily report: {self.daily_report_hour:02d}:{self.daily_report_minute:02d}")
        print(f"Monitoring: Speeding & 6 Performance Events")
        print("Command: /getid@nntexpressinc_safety_bot")
        print("Press Ctrl+C to stop")
        print("="*60 + "\n")
        
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(10)  # Check scheduler every 10 seconds
            except KeyboardInterrupt:
                logger.info("[SHUTDOWN] Bot stopped by user")
                break
            except Exception as e:
                logger.error(f"[ERROR] Scheduler loop error: {e}")
                time.sleep(30)
    
    def start(self):
        """Start the bot"""
        try:
            logger.info("[STARTUP] Testing connections...")
            asyncio.run(self._test_connections())
            
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
                text=f"✅ SafetyBot v3.0 Excel Started\nCheck Interval: {self.check_interval // 60}m\nDaily Report: {self.daily_report_hour:02d}:{self.daily_report_minute:02d}\nCommand: /getid@nntexpressinc_safety_bot\nReady to monitor",
                parse_mode='Markdown'
            )
            logger.info("[TEST] Startup message sent")
            
        except Exception as e:
            logger.error(f"[TEST] Telegram connection failed: {e}")
            raise
        
        try:
            logger.info("[TEST] Testing API connections...")
            speeding, _ = self.fetch_speeding_events()
            performance, _ = self.fetch_driver_performance_events()
            
            s_count = len(speeding) if speeding else 0
            p_count = len(performance) if performance else 0
            
            logger.info(f"[TEST] API OK: {s_count} speeding, {p_count} performance events")
            
        except Exception as e:
            logger.error(f"[TEST] API connection failed: {e}")
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