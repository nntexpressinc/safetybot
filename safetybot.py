#!/usr/bin/env python3
"""
Safety Bot - GoMotive APIs to Telegram Bot
Monitors both speeding events and driver performance events and sends alerts to Telegram
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
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv
import schedule
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from telegram import Bot, InputMediaVideo
from telegram.error import TelegramError, NetworkError, TimedOut

# Load environment variables
load_dotenv()

# Configure logging with proper encoding
def setup_logging():
    """Set up logging with Unicode support and fallback"""
    
    # Create formatters
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # File handler with UTF-8 encoding
    file_handler = logging.FileHandler('safetybot.log', encoding='utf-8')
    file_handler.setFormatter(formatter)
    
    # Console handler with error handling
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    # Try to set UTF-8 encoding for console if possible
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass
    
    # Set up logger
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

logger = setup_logging()

def log_safe(level, message):
    """Safe logging function that handles Unicode issues"""
    try:
        if level == 'info':
            logger.info(message)
        elif level == 'warning':
            logger.warning(message)
        elif level == 'error':
            logger.error(message)
        elif level == 'debug':
            logger.debug(message)
    except UnicodeEncodeError:
        # Fallback: remove problematic characters
        safe_message = message.encode('ascii', 'ignore').decode('ascii')
        if level == 'info':
            logger.info(safe_message)
        elif level == 'warning':
            logger.warning(safe_message)
        elif level == 'error':
            logger.error(safe_message)
        elif level == 'debug':
            logger.debug(safe_message)

class SafetyBot:
    """Main bot class for monitoring GoMotive APIs and sending Telegram alerts"""
    
    # Allowed event types for driver performance events
    ALLOWED_EVENT_TYPES = [
        'hard_brake',
        'crash',
        'seat_belt_violation',
        'stop_sign_violation',
        'distraction',
        'unsafe_lane_change'
    ]
    
    def __init__(self):
        """Initialize the bot with configuration from environment variables"""
        self.api_key = os.getenv('API_KEY')
        self.api_base_url = os.getenv('API_BASE_URL')
        self.telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.check_interval = int(os.getenv('CHECK_INTERVAL', 300))  # Every 5 minutes by default
        
        # Health monitoring
        self.last_successful_check = None
        self.consecutive_failures = 0
        self.max_consecutive_failures = 5
        
        # Last event files for both APIs
        self.last_performance_event_file = 'last_performance_event_id.txt'
        self.last_speeding_event_file = 'last_speeding_event_id.txt'
        
        # Separate tracking files for each performance event type
        self.performance_event_files = {
            'hard_brake': 'last_hard_brake_event_id.txt',
            'crash': 'last_crash_event_id.txt',
            'seat_belt_violation': 'last_seat_belt_violation_event_id.txt',
            'stop_sign_violation': 'last_stop_sign_violation_event_id.txt',
            'distraction': 'last_distraction_event_id.txt',
            'unsafe_lane_change': 'last_unsafe_lane_change_event_id.txt'
        }
        
        # Add a flag to prevent concurrent executions
        self.is_processing = False
        
        # Validate configuration
        self._validate_config()
        
        # Initialize Telegram bot
        self.telegram_bot = Bot(token=self.telegram_token)
        
        # Headers for API requests
        self.headers = {
            'accept': 'application/json',
            'x-api-key': self.api_key,
            'User-Agent': 'SafetyBot/1.0'
        }
        
        # Configure requests session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        logger.info("SafetyBot initialized successfully")
    
    def _validate_config(self):
        """Validate that all required configuration is present"""
        required_vars = ['API_KEY', 'API_BASE_URL', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID']
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
    
    def _has_allowed_severity(self, event: Dict[str, Any]) -> bool:
        """Check if event has allowed severity (medium, high, or critical)"""
        metadata = event.get('metadata', {})
        severity = metadata.get('severity')
        return severity in ['medium', 'high', 'critical']
    
    def get_last_processed_event_id(self, event_type='performance') -> int:
        """Get the ID of the last processed event from file"""
        try:
            file_path = self.last_performance_event_file if event_type == 'performance' else self.last_speeding_event_file
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    return int(f.read().strip())
        except (FileNotFoundError, ValueError) as e:
            logger.warning(f"Could not read last {event_type} event ID: {e}")
        return 0
    
    def save_last_processed_event_id(self, event_id: int, event_type='performance'):
        """Save the ID of the last processed event to file"""
        try:
            file_path = self.last_performance_event_file if event_type == 'performance' else self.last_speeding_event_file
            with open(file_path, 'w') as f:
                f.write(str(event_id))
        except Exception as e:
            logger.error(f"Could not save last {event_type} event ID: {e}")
    
    def get_last_processed_event_id_for_type(self, event_type: str) -> int:
        """Get the last processed event ID for a specific performance event type"""
        # Map event types to their tracking files
        type_files = {
            'hard_brake': 'last_hard_brake_event_id.txt',
            'crash': 'last_crash_event_id.txt',
            'seat_belt_violation': 'last_seat_belt_violation_event_id.txt',
            'stop_sign_violation': 'last_stop_sign_violation_event_id.txt',
            'distraction': 'last_distraction_event_id.txt',
            'unsafe_lane_change': 'last_unsafe_lane_change_event_id.txt'
        }
        
        file_path = type_files.get(event_type, self.last_performance_event_file)
        
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    return int(f.read().strip())
        except (FileNotFoundError, ValueError) as e:
            logger.warning(f"Could not read last {event_type} event ID: {e}")
        return 0
    
    def save_last_processed_event_id_for_type(self, event_id: int, event_type: str):
        """Save the last processed event ID for a specific performance event type"""
        # Map event types to their tracking files
        type_files = {
            'hard_brake': 'last_hard_brake_event_id.txt',
            'crash': 'last_crash_event_id.txt',
            'seat_belt_violation': 'last_seat_belt_violation_event_id.txt',
            'stop_sign_violation': 'last_stop_sign_violation_event_id.txt',
            'distraction': 'last_distraction_event_id.txt',
            'unsafe_lane_change': 'last_unsafe_lane_change_event_id.txt'
        }
        
        file_path = type_files.get(event_type, self.last_performance_event_file)
        
        try:
            with open(file_path, 'w') as f:
                f.write(str(event_id))
            logger.debug(f"Saved last {event_type} event ID: {event_id}")
        except IOError as e:
            logger.error(f"Error saving last {event_type} event ID: {e}")
    
    def fetch_speeding_events(self) -> List[Dict[str, Any]]:
        """Fetch speeding events from GoMotive v1 API with robust error handling"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                params = {
                    'per_page': '25',
                    'page_no': '1'
                }
                
                url = f"{self.api_base_url.replace('v2', 'v1')}/speeding_events"
                
                logger.info(f"Fetching speeding events from: {url} (attempt {attempt + 1}/{max_retries})")
                response = self.session.get(url, headers=self.headers, params=params, timeout=45)
                response.raise_for_status()
                
                # Validate response content
                if not response.content:
                    logger.warning("Empty response from speeding events API")
                    return []
                
                data = response.json()
                events = data.get('speeding_events', [])
                
                # Validate data structure
                if not isinstance(events, list):
                    logger.warning(f"Unexpected data structure in speeding events response: {type(events)}")
                    return []
                
                logger.info(f"Successfully fetched {len(events)} speeding events from API")
                return events
                
            except requests.exceptions.Timeout as e:
                logger.warning(f"Timeout fetching speeding events (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
            except requests.exceptions.RequestException as e:
                logger.error(f"Request error fetching speeding events (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error in speeding events response (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
            except Exception as e:
                logger.error(f"Unexpected error fetching speeding events (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
        
        logger.error(f"Failed to fetch speeding events after {max_retries} attempts")
        return []
    
    def fetch_driver_performance_events(self) -> List[Dict[str, Any]]:
        """Fetch driver performance events from GoMotive v2 API with robust error handling per event type"""
        all_events = []
        
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
                    
                    logger.info(f"Fetching {event_type} events from: {url} (attempt {attempt + 1}/{max_retries})")
                    response = self.session.get(url, headers=self.headers, params=params, timeout=45)
                    response.raise_for_status()
                    
                    # Validate response content
                    if not response.content:
                        logger.warning(f"Empty response from {event_type} events API")
                        break
                    
                    data = response.json()
                    events = data.get('driver_performance_events', [])
                    
                    # Validate data structure
                    if not isinstance(events, list):
                        logger.warning(f"Unexpected data structure in {event_type} events response: {type(events)}")
                        break
                    
                    logger.info(f"Successfully found {len(events)} {event_type} events")
                    all_events.extend(events)
                    break  # Success, move to next event type
                    
                except requests.exceptions.Timeout as e:
                    logger.warning(f"Timeout fetching {event_type} events (attempt {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                except requests.exceptions.RequestException as e:
                    logger.error(f"Request error fetching {event_type} events (attempt {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error in {event_type} events response (attempt {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                except Exception as e:
                    logger.error(f"Unexpected error fetching {event_type} events (attempt {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
            
            # Add a small delay between different event type requests
            time.sleep(1)
        
        logger.info(f"Successfully fetched total of {len(all_events)} performance events from all event types")
        return all_events
    
    def filter_new_speeding_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter speeding events to only include new ones since last check with allowed severity"""
        last_event_id = self.get_last_processed_event_id('speeding')
        new_events = []
        
        for event_data in events:
            event = event_data.get('speeding_event', {})
            event_id = event.get('id', 0)
            if event_id > last_event_id and self._has_allowed_severity(event):
                new_events.append(event)
        
        # Sort by ID to process in chronological order
        new_events.sort(key=lambda x: x.get('id', 0))
        
        logger.info(f"Found {len(new_events)} new speeding events with allowed severity (last processed ID: {last_event_id})")
        return new_events
    
    def filter_new_performance_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter performance events to only include new ones since last check - PER EVENT TYPE"""
        new_events = []
        
        # Group events by type first
        events_by_type = {}
        for event_data in events:
            event = event_data.get('driver_performance_event', {})
            event_type = event.get('type', '')
            if event_type in self.ALLOWED_EVENT_TYPES:
                if event_type not in events_by_type:
                    events_by_type[event_type] = []
                events_by_type[event_type].append(event)
        
        # Process each event type separately with its own last processed ID
        for event_type, type_events in events_by_type.items():
            # Get last processed ID for this specific event type
            last_event_id = self.get_last_processed_event_id_for_type(event_type)
            
            # Find new events for this type with allowed severity
            type_new_events = []
            for event in type_events:
                event_id = event.get('id', 0)
                if event_id > last_event_id and self._has_allowed_severity(event):
                    type_new_events.append(event)
            
            # Sort by ID for this type
            type_new_events.sort(key=lambda x: x.get('id', 0))
            
            logger.info(f"Found {len(type_new_events)} new {event_type} events with allowed severity (last processed ID: {last_event_id})")
            new_events.extend(type_new_events)
        
        # Sort all new events by ID to process in chronological order
        new_events.sort(key=lambda x: x.get('id', 0))
        
        logger.info(f"Total: {len(new_events)} new performance events with allowed severity across all types")
        return new_events
    
    def format_time(self, time_str: str) -> str:
        """Format time string to readable format"""
        try:
            dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
            return dt.strftime('%b %d %I:%M %p')
        except:
            return time_str
    
    def format_speeding_message(self, event: Dict[str, Any]) -> str:
        """Format a speeding event into a readable message"""
        try:
            vehicle_number = event.get('vehicle', {}).get('number', 'N/A')
            end_time = self.format_time(event.get('end_time', ''))
            
            # Speed info - convert to mph if needed
            min_speed = event.get('min_vehicle_speed', 0)
            max_speed = event.get('max_vehicle_speed', 0)
            avg_exceeded = event.get('avg_over_speed_in_kph', 0)
            
            # Convert km/h to mph
            min_speed_mph = round(min_speed * 0.621371, 1) if min_speed else 0
            max_speed_mph = round(max_speed * 0.621371, 1) if max_speed else 0
            avg_exceeded_mph = round(avg_exceeded * 0.621371, 1) if avg_exceeded else 0
            
            # Get severity
            severity = event.get('metadata', {}).get('severity', 'unknown')
            
            message = f"""Speeding
🚚: {vehicle_number}
{end_time}
Vehicle speed range: {min_speed_mph}–{max_speed_mph} mph
Avg. exceeded: +{avg_exceeded_mph} mph
Severity: {severity}"""
            
            return message
            
        except Exception as e:
            logger.error(f"Error formatting speeding message: {e}")
            return f"Error formatting speeding event: {str(e)}"
    
    def format_performance_message(self, event: Dict[str, Any]) -> str:
        """Format a performance event into a readable message"""
        try:
            event_type = event.get('type', 'Unknown').replace('_', ' ').title()
            vehicle_number = event.get('vehicle', {}).get('number', 'N/A')
            end_time = self.format_time(event.get('end_time', ''))
            
            # Get severity
            severity = event.get('metadata', {}).get('severity', 'unknown')
            
            message = f"""{event_type}
🚚: {vehicle_number}
{end_time}
Severity: {severity}"""
            
            return message
            
        except Exception as e:
            logger.error(f"Error formatting performance message: {e}")
            return f"Error formatting performance event: {str(e)}"
    
    async def verify_video_url(self, video_url: str, video_type: str) -> bool:
        """Simple video URL verification"""
        try:
            # Simple HEAD request to check accessibility
            head_response = self.session.head(video_url, timeout=10)
            if head_response.status_code == 200:
                log_safe('info', f"[VIDEO] {video_type} URL accessible: {video_url}")
                return True
            else:
                log_safe('warning', f"[WARNING] {video_type} URL returned status {head_response.status_code}")
                # Still try to download even if HEAD fails
                return True
        except Exception as e:
            log_safe('warning', f"[WARNING] Error verifying {video_type} URL, but will still try to download: {e}")
            # Continue anyway - sometimes HEAD requests fail but GET works
            return True
    
    async def download_video_to_temp_file(self, video_url: str, video_type: str = "video") -> Optional[str]:
        """Download video from URL and save to temporary file - simplified and more reliable"""
        temp_file_path = None
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                log_safe('info', f"[VIDEO] Downloading {video_type} from: {video_url} (attempt {attempt + 1}/{max_retries})")
                
                # Download video with longer timeout
                response = self.session.get(video_url, timeout=180, stream=True)
                response.raise_for_status()
                
                # Read content
                video_data = response.content
                
                if not video_data:
                    log_safe('warning', f"[WARNING] Empty video data for {video_type}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(3)
                        continue
                    return None
                
                # Check size (Telegram limit is 50MB)
                size_mb = len(video_data) / (1024 * 1024)
                log_safe('info', f"[VIDEO] {video_type} size: {size_mb:.1f}MB")
                
                if size_mb > 50:
                    log_safe('warning', f"[WARNING] {video_type} too large ({size_mb:.1f}MB), skipping")
                    return None
                
                if size_mb < 0.01:  # Less than 10KB
                    log_safe('warning', f"[WARNING] {video_type} too small ({size_mb:.3f}MB), skipping")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(3)
                        continue
                    return None
                
                # Create temporary file
                temp_filename = f"{video_type}_{uuid.uuid4().hex}.mp4"
                temp_file_path = os.path.join(tempfile.gettempdir(), temp_filename)
                
                # Save video to file
                with open(temp_file_path, 'wb') as temp_file:
                    temp_file.write(video_data)
                
                # Verify file was created correctly
                if os.path.exists(temp_file_path) and os.path.getsize(temp_file_path) > 0:
                    log_safe('info', f"[OK] {video_type} ({size_mb:.1f}MB) saved to: {temp_file_path}")
                    return temp_file_path
                else:
                    log_safe('error', f"[ERROR] Failed to create {video_type} file")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(3)
                        continue
                    return None
                
            except requests.exceptions.Timeout as e:
                log_safe('warning', f"[WARNING] Timeout downloading {video_type} (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
                    continue
            except requests.exceptions.RequestException as e:
                log_safe('error', f"[ERROR] Request error downloading {video_type} (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
                    continue
            except Exception as e:
                log_safe('error', f"[ERROR] Unexpected error downloading {video_type} (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
                    continue
        
        log_safe('error', f"[ERROR] Failed to download {video_type} after {max_retries} attempts: {video_url}")
        return None
        """Download video from URL and send to Telegram with caption, then clean up local file"""
        temp_file_path = None
        try:
            logger.info(f"Downloading {video_type} from: {video_url}")
            
            # Download video
            response = requests.get(video_url, timeout=60)
            response.raise_for_status()
            
            video_data = response.content
            
            if len(video_data) > 50 * 1024 * 1024:  # 50MB limit for Telegram
                logger.warning(f"{video_type} too large for Telegram, skipping")
                return False
            
            # Create a unique filename
            temp_filename = f"{video_type}_{uuid.uuid4().hex}.mp4"
            temp_file_path = os.path.join(tempfile.gettempdir(), temp_filename)
            
            # Save video to temporary file
            with open(temp_file_path, 'wb') as temp_file:
                temp_file.write(video_data)
            
            logger.info(f"{video_type} saved to temporary file: {temp_file_path}")
            
            # Send video to Telegram with caption
            with open(temp_file_path, 'rb') as video_file:
                await self.telegram_bot.send_video(
                    chat_id=self.chat_id,
                    video=video_file,
                    caption=caption,
                    parse_mode='Markdown'
                )
            
            logger.info(f"{video_type} with caption sent successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error downloading/sending {video_type}: {e}")
            return False
        
        finally:
            # Clean up temporary file
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                    logger.info(f"Temporary {video_type} file deleted: {temp_file_path}")
                except Exception as cleanup_error:
                    logger.error(f"Error deleting temporary file {temp_file_path}: {cleanup_error}")
    
    async def send_speeding_event_to_telegram(self, event: Dict[str, Any]):
        """Send a speeding event to Telegram with retry logic"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                message = self.format_speeding_message(event)
                
                # Send text message for speeding events (no videos for speeding)
                await self.telegram_bot.send_message(
                    chat_id=self.chat_id,
                    text=message,
                    parse_mode='Markdown'
                )
                
                logger.info(f"Speeding event {event.get('id')} sent successfully")
                return  # Success, exit retry loop
                    
            except (NetworkError, TimedOut) as e:
                logger.warning(f"Network error sending speeding event {event.get('id')} (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
            except TelegramError as e:
                logger.error(f"Telegram API error sending speeding event {event.get('id')}: {e}")
                break  # Don't retry on API errors
            except Exception as e:
                logger.error(f"Unexpected error sending speeding event {event.get('id')} (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
        
        logger.error(f"Failed to send speeding event {event.get('id')} after {max_retries} attempts")
    
    async def send_performance_event_to_telegram(self, event: Dict[str, Any]):
        """Send a performance event to Telegram with comprehensive video verification and robust error handling"""
        event_id = event.get('id', 0)
        event_type = event.get('type', 'unknown')
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                message = self.format_performance_message(event)
                
                # Check for camera media
                camera_media = event.get('camera_media', {})
                if camera_media and camera_media.get('available'):
                    downloadable_videos = camera_media.get('downloadable_videos', {})
                    
                    front_facing_url = downloadable_videos.get('front_facing_plain_url')
                    driver_facing_url = downloadable_videos.get('driver_facing_plain_url')
                    
                    log_safe('info', f"[VIDEO] Event {event_id} video URLs - Front: {bool(front_facing_url)}, Driver: {bool(driver_facing_url)}")
                    
                    temp_files = []
                    videos_to_send = []
                    
                    try:
                        # Try to download videos - simplified approach
                        if front_facing_url:
                            log_safe('info', f"[VIDEO] Downloading front-facing video for event {event_id}")
                            front_file_path = await self.download_video_to_temp_file(front_facing_url, "front_facing")
                            if front_file_path:
                                temp_files.append(front_file_path)
                                videos_to_send.append(('front_facing', front_file_path))
                                log_safe('info', f"[OK] Front-facing video ready for event {event_id}")
                            else:
                                log_safe('warning', f"[WARNING] Front-facing video download failed for event {event_id}")
                        
                        if driver_facing_url:
                            log_safe('info', f"[VIDEO] Downloading driver-facing video for event {event_id}")
                            driver_file_path = await self.download_video_to_temp_file(driver_facing_url, "driver_facing")
                            if driver_file_path:
                                temp_files.append(driver_file_path)
                                videos_to_send.append(('driver_facing', driver_file_path))
                                log_safe('info', f"[OK] Driver-facing video ready for event {event_id}")
                            else:
                                log_safe('warning', f"[WARNING] Driver-facing video download failed for event {event_id}")
                        
                        # Send videos if we have any
                        if videos_to_send:
                            if len(videos_to_send) == 1:
                                # Send single video
                                video_type, video_path = videos_to_send[0]
                                try:
                                    with open(video_path, 'rb') as video_file:
                                        await self.telegram_bot.send_video(
                                            chat_id=self.chat_id,
                                            video=video_file,
                                            caption=f"{message}\n\n[VIDEO] {video_type.replace('_', ' ').title()}",
                                            parse_mode='Markdown',
                                            read_timeout=180,
                                            write_timeout=180
                                        )
                                    log_safe('info', f"[OK] Single video sent for {event_type} event {event_id}")
                                except Exception as send_error:
                                    log_safe('error', f"[ERROR] Failed to send single video: {send_error}")
                                    # Fallback to text message
                                    await self.telegram_bot.send_message(
                                        chat_id=self.chat_id,
                                        text=f"{message}\n\n[WARNING] Video upload failed",
                                        parse_mode='Markdown'
                                    )
                            else:
                                # Send multiple videos one by one (more reliable than media group)
                                for i, (video_type, video_path) in enumerate(videos_to_send):
                                    try:
                                        with open(video_path, 'rb') as video_file:
                                            caption = f"{message}\n\n[VIDEO] {video_type.replace('_', ' ').title()}" if i == 0 else f"[VIDEO] {video_type.replace('_', ' ').title()}"
                                            await self.telegram_bot.send_video(
                                                chat_id=self.chat_id,
                                                video=video_file,
                                                caption=caption,
                                                parse_mode='Markdown',
                                                read_timeout=180,
                                                write_timeout=180
                                            )
                                        log_safe('info', f"[OK] {video_type} video sent for event {event_id}")
                                        await asyncio.sleep(2)  # Small delay between videos
                                    except Exception as send_error:
                                        log_safe('error', f"[ERROR] Failed to send {video_type} video: {send_error}")
                        else:
                            # No videos could be downloaded, send text message
                            await self.telegram_bot.send_message(
                                chat_id=self.chat_id,
                                text=f"{message}\n\n[WARNING] Videos could not be downloaded",
                                parse_mode='Markdown'
                            )
                            log_safe('warning', f"[WARNING] No videos could be downloaded for event {event_id}")
                    
                    finally:
                        # Clean up temporary files
                        for temp_file in temp_files:
                            try:
                                if os.path.exists(temp_file):
                                    os.remove(temp_file)
                                    log_safe('debug', f"[DELETE] Cleaned up temp file: {temp_file}")
                            except Exception as cleanup_error:
                                log_safe('error', f"[ERROR] Cleanup failed for {temp_file}: {cleanup_error}")
                else:
                    # No camera media available, send text message only
                    await self.telegram_bot.send_message(
                        chat_id=self.chat_id,
                        text=f"{message}\n\n[INFO] No camera media available",
                        parse_mode='Markdown'
                    )
                    log_safe('info', f"[INFO] No camera media for event {event_id}")
                    logger.info(f"✅ Text-only message sent for {event_type} event {event_id} (no media)")
                
                return  # Success, exit retry loop
                
            except (NetworkError, TimedOut) as e:
                logger.warning(f"⚠️ Network error sending {event_type} event {event_id} (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
            except TelegramError as e:
                if "file too large" in str(e).lower():
                    logger.warning(f"⚠️ File too large for {event_type} event {event_id}, sending text only")
                    try:
                        message = self.format_performance_message(event)
                        await self.telegram_bot.send_message(
                            chat_id=self.chat_id,
                            text=f"{message}\n\n⚠️ Videos too large for Telegram",
                            parse_mode='Markdown'
                        )
                        return
                    except Exception as fallback_error:
                        logger.error(f"❌ Fallback message also failed for {event_type} event {event_id}: {fallback_error}")
                
                logger.error(f"❌ Telegram API error sending {event_type} event {event_id}: {e}")
                break  # Don't retry on API errors
            except Exception as e:
                logger.error(f"❌ Unexpected error sending {event_type} event {event_id} (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
        
        logger.error(f"❌ Failed to send {event_type} event {event_id} after {max_retries} attempts")
    
    async def process_new_events(self):
        """Main function to check for and process new events from both APIs with comprehensive monitoring"""
        start_time = datetime.now()
        
        try:
            log_safe('info', "[SEARCH] Starting comprehensive check for new events from both APIs...")
            
            # Initialize counters for monitoring
            total_speeding_processed = 0
            total_performance_processed = 0
            speeding_errors = 0
            performance_errors = 0
            
            # Process speeding events with detailed monitoring
            log_safe('info', "[STATS] Fetching speeding events...")
            speeding_events = self.fetch_speeding_events()
            
            if speeding_events is not None:  # Check for None vs empty list
                new_speeding_events = self.filter_new_speeding_events(speeding_events)
                if new_speeding_events:
                    log_safe('info', f"[ALERT] Processing {len(new_speeding_events)} new speeding events with medium/high/critical severity")
                    
                    latest_speeding_id = 0
                    for event in new_speeding_events:
                        event_id = event.get('id', 0)
                        severity = event.get('metadata', {}).get('severity', 'unknown')
                        
                        try:
                            log_safe('info', f"[SEND] Processing speeding event {event_id} (severity: {severity})")
                            await self.send_speeding_event_to_telegram(event)
                            latest_speeding_id = max(latest_speeding_id, event_id)
                            total_speeding_processed += 1
                            
                            # Delay between messages
                            await asyncio.sleep(3)
                            
                        except Exception as e:
                            logger.error(f"❌ Failed to process speeding event {event_id}: {e}")
                            speeding_errors += 1
                            continue
                    
                    if latest_speeding_id > 0:
                        self.save_last_processed_event_id(latest_speeding_id, 'speeding')
                        log_safe('info', f"[OK] Updated last processed speeding event ID to: {latest_speeding_id}")
                else:
                    log_safe('info', "[OK] No new speeding events with qualifying severity found")
            else:
                log_safe('warning', "[WARNING] Failed to fetch speeding events")
            
            # Process performance events with detailed monitoring
            log_safe('info', "[TARGET] Fetching driver performance events...")
            performance_events = self.fetch_driver_performance_events()
            
            if performance_events is not None:  # Check for None vs empty list
                new_performance_events = self.filter_new_performance_events(performance_events)
                if new_performance_events:
                    log_safe('info', f"[ALERT] Processing {len(new_performance_events)} new performance events with medium/high/critical severity")
                    
                    # Track latest event ID per event type
                    latest_ids_by_type = {}
                    
                    for event in new_performance_events:
                        event_id = event.get('id', 0)
                        event_type = event.get('type', '')
                        severity = event.get('metadata', {}).get('severity', 'unknown')
                        
                        try:
                            log_safe('info', f"[SEND] Processing {event_type} event {event_id} (severity: {severity})")
                            await self.send_performance_event_to_telegram(event)
                            
                            # Track the latest ID for this event type
                            if event_type not in latest_ids_by_type:
                                latest_ids_by_type[event_type] = event_id
                            else:
                                latest_ids_by_type[event_type] = max(latest_ids_by_type[event_type], event_id)
                            
                            total_performance_processed += 1
                            
                            # Delay between messages
                            await asyncio.sleep(3)
                            
                        except Exception as e:
                            logger.error(f"❌ Failed to process {event_type} event {event_id}: {e}")
                            performance_errors += 1
                            continue
                    
                    # Save the latest ID for each event type separately
                    for event_type, latest_id in latest_ids_by_type.items():
                        self.save_last_processed_event_id_for_type(latest_id, event_type)
                        log_safe('info', f"[OK] Updated last processed {event_type} event ID to: {latest_id}")
                else:
                    log_safe('info', "[OK] No new performance events with qualifying severity found")
            else:
                log_safe('warning', "[WARNING] Failed to fetch performance events")
            
            # Update health monitoring
            self.last_successful_check = datetime.now()
            self.consecutive_failures = 0
            
            # Log comprehensive summary
            duration = (datetime.now() - start_time).total_seconds()
            log_safe('info', f"[REPORT] Check completed in {duration:.1f}s - Processed: {total_speeding_processed} speeding, {total_performance_processed} performance events. Errors: {speeding_errors + performance_errors}")
            
            # Send health report if there were significant errors
            if speeding_errors + performance_errors > 0:
                try:
                    await self.telegram_bot.send_message(
                        chat_id=self.chat_id,
                        text=f"⚠️ SafetyBot Health Report\n\nProcessed: {total_speeding_processed + total_performance_processed} events\nErrors: {speeding_errors + performance_errors}\nDuration: {duration:.1f}s",
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Failed to send health report: {e}")
                
        except Exception as e:
            logger.error(f"❌ Critical error in process_new_events: {e}")
            self.consecutive_failures += 1
            
            # Send critical error alert if too many consecutive failures
            if self.consecutive_failures >= self.max_consecutive_failures:
                try:
                    await self.telegram_bot.send_message(
                        chat_id=self.chat_id,
                        text=f"🚨 CRITICAL: SafetyBot has failed {self.consecutive_failures} consecutive times.\n\nLast error: {str(e)[:200]}\n\nPlease check the system immediately!",
                        parse_mode='Markdown'
                    )
                except Exception as telegram_error:
                    logger.error(f"Failed to send critical error alert: {telegram_error}")
    
    async def health_check(self):
        """Perform comprehensive health check and send status report"""
        try:
            health_status = {
                'timestamp': datetime.now().isoformat(),
                'last_successful_check': self.last_successful_check.isoformat() if self.last_successful_check else None,
                'consecutive_failures': self.consecutive_failures,
                'apis_accessible': False,
                'telegram_accessible': False
            }
            
            # Test API connectivity
            try:
                log_safe('info', "[SEARCH] Testing API connectivity...")
                speeding_test = self.fetch_speeding_events()
                performance_test = self.fetch_driver_performance_events()
                health_status['apis_accessible'] = (speeding_test is not None and performance_test is not None)
                log_safe('info', f"[NETWORK] API connectivity: {'[OK]' if health_status['apis_accessible'] else '[FAILED]'}")
            except Exception as e:
                logger.error(f"❌ API health check failed: {e}")
                health_status['api_error'] = str(e)
            
            # Test Telegram connectivity
            try:
                log_safe('info', "[MOBILE] Testing Telegram connectivity...")
                await self.telegram_bot.get_me()
                health_status['telegram_accessible'] = True
                log_safe('info', "[MOBILE] Telegram connectivity: [OK]")
            except Exception as e:
                logger.error(f"❌ Telegram health check failed: {e}")
                health_status['telegram_error'] = str(e)
            
            # Determine overall health
            overall_health = health_status['apis_accessible'] and health_status['telegram_accessible']
            
            # Send health report
            status_emoji = "✅" if overall_health else "❌"
            last_check_str = "Never" if not self.last_successful_check else f"{(datetime.now() - self.last_successful_check).total_seconds() / 60:.1f} minutes ago"
            
            health_message = f"""🏥 SafetyBot Health Report

{status_emoji} Overall Status: {'Healthy' if overall_health else 'Issues Detected'}
📊 Last Successful Check: {last_check_str}
🔄 Consecutive Failures: {self.consecutive_failures}
🌐 API Access: {'✅' if health_status['apis_accessible'] else '❌'}
📱 Telegram Access: {'✅' if health_status['telegram_accessible'] else '❌'}
⏰ Check Interval: {self.check_interval//60} minutes

📅 Report Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
            
            await self.telegram_bot.send_message(
                chat_id=self.chat_id,
                text=health_message,
                parse_mode='Markdown'
            )
            
            logger.info(f"🏥 Health check completed - Status: {'Healthy' if overall_health else 'Issues'}")
            
        except Exception as e:
            logger.error(f"❌ Health check failed: {e}")
    
    def run_check(self):
        """Synchronous wrapper for the async check function"""
        if self.is_processing:
            logger.warning("Previous check still running, skipping this execution")
            return
            
        try:
            self.is_processing = True
            asyncio.run(self.process_new_events())
        except Exception as e:
            logger.error(f"Error running check: {e}")
        finally:
            self.is_processing = False
    
    async def test_connection(self):
        """Test both API and Telegram connections with comprehensive validation"""
        logger.info("🔍 Testing all connections...")
        
        # Test Telegram first
        try:
            bot_info = await self.telegram_bot.get_me()
            await self.telegram_bot.send_message(
                chat_id=self.chat_id,
                text=f"🤖 SafetyBot v2.0 Started Successfully!\n\n\n🔄 Check Interval: {self.check_interval//60} minutes\n📊 Monitoring: Speeding & Performance Events\n🎯 Severity Filter: Medium, High, Critical\n\n🚀 Ready to monitor for safety events...",
                parse_mode='Markdown'
            )
            logger.info("📱 Telegram connection test: ✅ SUCCESS")
        except Exception as e:
            logger.error(f"❌ Telegram connection test FAILED: {e}")
            raise
        
        # Test both APIs
        try:
            logger.info("🌐 Testing API connections...")
            speeding_events = self.fetch_speeding_events()
            performance_events = self.fetch_driver_performance_events()
            
            speeding_count = len(speeding_events) if speeding_events else 0
            performance_count = len(performance_events) if performance_events else 0
            
            logger.info(f"🌐 API connection test: ✅ SUCCESS - Fetched {speeding_count} speeding events and {performance_count} performance events")
            
            # Send API test summary
            
            
        except Exception as e:
            logger.error(f"❌ API connection test FAILED: {e}")
            raise
    
    def start(self):
        """Start the bot monitoring loop with comprehensive health monitoring"""
        log_safe('info', "[START] Starting SafetyBot v2.0 with enhanced monitoring...")
        
        # Test connections first
        try:
            asyncio.run(self.test_connection())
        except Exception as e:
            log_safe('error', f"[ERROR] Connection test failed: {e}")
            return
        
        # Schedule the main check
        schedule.every(self.check_interval).seconds.do(self.run_check)
        log_safe('info', f"[SCHEDULE] Scheduled to check APIs every {self.check_interval} seconds ({self.check_interval/60:.1f} minutes)")
        
        # Schedule health checks every hour
        schedule.every().hour.do(lambda: asyncio.run(self.health_check()))
        log_safe('info', "[HEALTH] Scheduled health checks every hour")
        
        # Run initial check
        log_safe('info', "[SEARCH] Running initial event check...")
        self.run_check()
        
        # Start the scheduler loop
        log_safe('info', "[REFRESH] Starting monitoring loop - Bot is now actively monitoring!")
        print(f"\n[BOT] SafetyBot v2.0 is running!")
        print(f"[STATS] Checking every {self.check_interval//60} minutes for events with medium/high/critical severity")
        print(f"[MOBILE] Sending alerts to Telegram chat: {self.chat_id}")
        print(f"[HEALTH] Health reports every hour")
        print(f"\n[STOP] Press Ctrl+C to stop\n")
        
        while True:
            try:
                schedule.run_pending()
                time.sleep(30)  # Check schedule every 30 seconds for better responsiveness
            except KeyboardInterrupt:
                log_safe('info', "[STOPPED] Bot stopped by user")
                print("\n[STOPPED] SafetyBot stopped by user")
                break
            except Exception as e:
                log_safe('error', f"[ERROR] Error in main loop: {e}")
                time.sleep(60)  # Wait before continuing

def main():
    """Main entry point"""
    try:
        bot = SafetyBot()
        bot.start()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()