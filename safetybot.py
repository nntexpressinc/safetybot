#!/usr/bin/env python3
"""
Safety Bot - GoMotive APIs to Telegram Bot
Monitors speeding and driver performance events with production-grade reliability
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
    """Main bot class for monitoring GoMotive APIs and sending Telegram alerts"""
    
    ALLOWED_EVENT_TYPES = [
        'hard_brake', 'crash', 'seat_belt_violation', 'stop_sign_violation',
        'distraction', 'unsafe_lane_change'
    ]
    
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
        
        # Event tracking files
        self.last_performance_event_file = 'last_performance_event_id.txt'
        self.last_speeding_event_file = 'last_speeding_event_id.txt'
        
        self.performance_event_files = {
            event_type: f'last_{event_type}_event_id.txt'
            for event_type in self.ALLOWED_EVENT_TYPES
        }
        
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
        
        logger.info("SafetyBot initialized successfully")
    
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
            'User-Agent': 'SafetyBot/2.0'
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
    
    def get_last_processed_event_id_for_type(self, event_type: str) -> int:
        """Get the last processed event ID for a specific performance event type"""
        file_path = self.performance_event_files.get(event_type, self.last_performance_event_file)
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    return int(f.read().strip())
        except (FileNotFoundError, ValueError) as e:
            logger.warning(f"Could not read last {event_type} event ID: {e}")
        return 0
    
    def save_last_processed_event_id_for_type(self, event_id: int, event_type: str):
        """Save the last processed event ID for a specific performance event type"""
        file_path = self.performance_event_files.get(event_type, self.last_performance_event_file)
        try:
            with open(file_path, 'w') as f:
                f.write(str(event_id))
        except IOError as e:
            logger.error(f"Error saving last {event_type} event ID: {e}")
    
    def fetch_speeding_events(self) -> Optional[List[Dict[str, Any]]]:
        """Fetch speeding events from GoMotive v1 API"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                params = {'per_page': '25', 'page_no': '1'}
                url = f"{self.api_base_url.replace('v2', 'v1')}/speeding_events"
                
                logger.info(f"Fetching speeding events (attempt {attempt + 1}/{max_retries})")
                response = self.session.get(url, headers=self.headers, params=params, timeout=45)
                response.raise_for_status()
                
                if not response.content:
                    logger.warning("Empty response from speeding events API")
                    return []
                
                data = response.json()
                events = data.get('speeding_events', [])
                
                if not isinstance(events, list):
                    logger.warning("Unexpected data structure in speeding events response")
                    return []
                
                logger.info(f"Successfully fetched {len(events)} speeding events")
                return events
                
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout fetching speeding events (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
            except requests.exceptions.RequestException as e:
                logger.error(f"Request error fetching speeding events (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error in speeding events response: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
            except Exception as e:
                logger.error(f"Unexpected error fetching speeding events: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
        
        logger.error(f"Failed to fetch speeding events after {max_retries} attempts")
        return None
    
    def fetch_driver_performance_events(self) -> Optional[List[Dict[str, Any]]]:
        """Fetch driver performance events from GoMotive v2 API"""
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
                    logger.info(f"Fetching {event_type} events (attempt {attempt + 1}/{max_retries})")
                    response = self.session.get(url, headers=self.headers, params=params, timeout=45)
                    response.raise_for_status()
                    
                    if not response.content:
                        logger.warning(f"Empty response from {event_type} events API")
                        break
                    
                    data = response.json()
                    events = data.get('driver_performance_events', [])
                    
                    if not isinstance(events, list):
                        logger.warning(f"Unexpected data structure in {event_type} events response")
                        break
                    
                    logger.info(f"Found {len(events)} {event_type} events")
                    all_events.extend(events)
                    break
                    
                except requests.exceptions.Timeout:
                    logger.warning(f"Timeout fetching {event_type} events (attempt {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                except requests.exceptions.RequestException as e:
                    logger.error(f"Request error fetching {event_type} events (attempt {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error in {event_type} events response: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                except Exception as e:
                    logger.error(f"Unexpected error fetching {event_type} events: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
            
            time.sleep(1)
        
        logger.info(f"Successfully fetched {len(all_events)} total performance events")
        return all_events
    
    def filter_new_speeding_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter new speeding events with allowed severity"""
        last_event_id = self.get_last_processed_event_id('speeding')
        new_events = []
        
        for event_data in events:
            event = event_data.get('speeding_event', {})
            event_id = event.get('id', 0)
            if event_id > last_event_id and self._has_allowed_severity(event):
                new_events.append(event)
        
        new_events.sort(key=lambda x: x.get('id', 0))
        logger.info(f"Found {len(new_events)} new speeding events (last ID: {last_event_id})")
        return new_events
    
    def filter_new_performance_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter new performance events per event type"""
        new_events = []
        events_by_type = {}
        
        for event_data in events:
            event = event_data.get('driver_performance_event', {})
            event_type = event.get('type', '')
            if event_type in self.ALLOWED_EVENT_TYPES:
                if event_type not in events_by_type:
                    events_by_type[event_type] = []
                events_by_type[event_type].append(event)
        
        for event_type, type_events in events_by_type.items():
            last_event_id = self.get_last_processed_event_id_for_type(event_type)
            type_new_events = [
                event for event in type_events
                if event.get('id', 0) > last_event_id and self._has_allowed_severity(event)
            ]
            type_new_events.sort(key=lambda x: x.get('id', 0))
            logger.info(f"Found {len(type_new_events)} new {event_type} events (last ID: {last_event_id})")
            new_events.extend(type_new_events)
        
        new_events.sort(key=lambda x: x.get('id', 0))
        return new_events
    
    def format_time(self, time_str: str, latitude: Optional[float] = None, longitude: Optional[float] = None) -> str:
        """Format time string to readable format with timezone conversion using longitude offset"""
        try:
            import pytz
            
            # Parse UTC time string
            dt_utc = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
            
            # Ensure it's in UTC
            dt_utc = dt_utc.astimezone(pytz.UTC)
            
            # Calculate timezone offset from longitude (most reliable method)
            # Each 15 degrees of longitude = 1 hour of timezone difference
            tz_local = None
            
            if longitude is not None:
                # Map longitude ranges to US timezones (works for your fleet data)
                if longitude >= -124 and longitude <= -115:  # Pacific: UTC-8/-7
                    tz_local = pytz.timezone('America/Los_Angeles')
                    logger.info(f"[TZ] Using America/Los_Angeles for longitude {longitude}")
                elif longitude >= -115 and longitude <= -102:  # Mountain: UTC-7/-6
                    tz_local = pytz.timezone('America/Denver')
                    logger.info(f"[TZ] Using America/Denver for longitude {longitude}")
                elif longitude >= -102 and longitude <= -90:  # Central: UTC-6/-5
                    tz_local = pytz.timezone('America/Chicago')
                    logger.info(f"[TZ] Using America/Chicago for longitude {longitude}")
                elif longitude >= -90 and longitude <= -75:  # Eastern: UTC-5/-4
                    tz_local = pytz.timezone('America/New_York')
                    logger.info(f"[TZ] Using America/New_York for longitude {longitude}")
                else:
                    tz_local = pytz.timezone('America/Los_Angeles')
                    logger.info(f"[TZ] Using default America/Los_Angeles")
            else:
                tz_local = pytz.timezone('America/Los_Angeles')
                logger.info(f"[TZ] Using default America/Los_Angeles (no coordinates)")
            
            # Convert to local timezone - automatically handles DST
            dt_local = dt_utc.astimezone(tz_local)
            
            logger.info(f"[TIME] {time_str} UTC -> {dt_local.strftime('%m/%d/%Y %I:%M %p %Z')} ({tz_local})")
            
            # Format as: 10/17/2025 06:37 AM
            formatted = dt_local.strftime('%m/%d/%Y %I:%M %p')
            return formatted
            
        except Exception as e:
            logger.error(f"[TZ_ERROR] Error formatting time '{time_str}' with coords ({latitude}, {longitude}): {e}")
            import traceback
            logger.error(traceback.format_exc())
            return time_str
    
    def format_speeding_message(self, event: Dict[str, Any]) -> str:
        """Format speeding event message with localized time"""
        try:
            vehicle_number = event.get('vehicle', {}).get('number', 'N/A')
            driver = event.get('driver', {})
            driver_name = f"{driver.get('first_name', '')} {driver.get('last_name', '')}".strip() or 'Unknown'
            
            # Get coordinates for timezone detection
            end_lat = event.get('end_lat')
            end_lon = event.get('end_lon')
            date_time = self.format_time(event.get('end_time', ''), end_lat, end_lon)
            
            min_speed = event.get('min_vehicle_speed', 0)
            max_speed = event.get('max_vehicle_speed', 0)
            avg_exceeded = event.get('avg_over_speed_in_kph', 0)
            
            min_speed_mph = round(min_speed * 0.621371, 1) if min_speed else 0
            max_speed_mph = round(max_speed * 0.621371, 1) if max_speed else 0
            avg_exceeded_mph = round(avg_exceeded * 0.621371, 1) if avg_exceeded else 0
            
            severity = event.get('metadata', {}).get('severity', 'unknown')
            
            return f"""Speeding Alert
Driver: {driver_name}
Vehicle: {vehicle_number}
{date_time}
Speed Range: {min_speed_mph}–{max_speed_mph} mph
Exceeded By: +{avg_exceeded_mph} mph
Severity: {severity}"""
            
        except Exception as e:
            logger.error(f"Error formatting speeding message: {e}")
            return "Error formatting speeding event"
    
    def format_performance_message(self, event: Dict[str, Any]) -> str:
        """Format performance event message with localized time"""
        try:
            event_type = event.get('type', 'Unknown').replace('_', ' ').title()
            vehicle_number = event.get('vehicle', {}).get('number', 'N/A')
            driver = event.get('driver', {})
            driver_name = f"{driver.get('first_name', '')} {driver.get('last_name', '')}".strip() or 'Unknown'
            
            # Get coordinates for timezone detection
            end_lat = event.get('end_lat')
            end_lon = event.get('end_lon')
            end_time = self.format_time(event.get('end_time', ''), end_lat, end_lon)
            
            severity = event.get('metadata', {}).get('severity', 'unknown')
            
            return f"""{event_type}
Driver: {driver_name}
Vehicle: {vehicle_number}
{end_time}
Severity: {severity}"""
            
        except Exception as e:
            logger.error(f"Error formatting performance message: {e}")
            return "Error formatting performance event"
    
    async def download_video_to_temp_file(self, video_url: str, video_type: str = "video") -> Optional[str]:
        """Download video and save to temporary file with timeout handling"""
        max_retries = 2
        for attempt in range(max_retries):
            try:
                logger.info(f"Downloading {video_type} (attempt {attempt + 1}/{max_retries})")
                
                response = self.session.get(video_url, timeout=180, stream=True)
                response.raise_for_status()
                video_data = response.content
                
                if not video_data:
                    logger.warning(f"Empty video data for {video_type}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(3)
                    continue
                
                size_mb = len(video_data) / (1024 * 1024)
                logger.info(f"{video_type} size: {size_mb:.1f}MB")
                
                if size_mb > 50:
                    logger.warning(f"{video_type} too large ({size_mb:.1f}MB)")
                    return None
                
                if size_mb < 0.01:
                    logger.warning(f"{video_type} too small ({size_mb:.3f}MB)")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(3)
                    continue
                
                temp_filename = f"{video_type}_{uuid.uuid4().hex}.mp4"
                temp_file_path = os.path.join(tempfile.gettempdir(), temp_filename)
                
                with open(temp_file_path, 'wb') as temp_file:
                    temp_file.write(video_data)
                
                if os.path.exists(temp_file_path) and os.path.getsize(temp_file_path) > 0:
                    logger.info(f"{video_type} ({size_mb:.1f}MB) saved successfully")
                    return temp_file_path
                else:
                    logger.error(f"Failed to create {video_type} file")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(3)
                
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout downloading {video_type} (attempt {attempt + 1})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
            except requests.exceptions.RequestException as e:
                logger.error(f"Request error downloading {video_type}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Unexpected error downloading {video_type}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
        
        logger.error(f"Failed to download {video_type}")
        return None
    
    async def send_speeding_event_to_telegram(self, event: Dict[str, Any]):
        """Send speeding event to Telegram with retry logic"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                message = self.format_speeding_message(event)
                await self.telegram_bot.send_message(
                    chat_id=self.chat_id,
                    text=message,
                    parse_mode='Markdown'
                )
                logger.info(f"Speeding event {event.get('id')} sent successfully")
                return
                    
            except (NetworkError, TimedOut) as e:
                logger.warning(f"Network error sending speeding event (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
            except TelegramError as e:
                logger.error(f"Telegram API error: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected error sending speeding event (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        
        logger.error(f"Failed to send speeding event {event.get('id')}")
    
    async def send_performance_event_to_telegram(self, event: Dict[str, Any]):
        """Send performance event to Telegram with comprehensive handling"""
        event_id = event.get('id', 0)
        event_type = event.get('type', 'unknown')
        
        max_retries = 3
        for attempt in range(max_retries):
            temp_files = []
            try:
                message = self.format_performance_message(event)
                camera_media = event.get('camera_media', {})
                
                if camera_media and camera_media.get('available'):
                    downloadable_videos = camera_media.get('downloadable_videos', {})
                    front_facing_url = downloadable_videos.get('front_facing_plain_url')
                    driver_facing_url = downloadable_videos.get('driver_facing_plain_url')
                    
                    videos_for_group = []
                    
                    # Download videos
                    if front_facing_url:
                        front_file = await self.download_video_to_temp_file(front_facing_url, "front_facing")
                        if front_file:
                            temp_files.append(front_file)
                            videos_for_group.append(('Front', front_file))
                    
                    if driver_facing_url:
                        driver_file = await self.download_video_to_temp_file(driver_facing_url, "driver_facing")
                        if driver_file:
                            temp_files.append(driver_file)
                            videos_for_group.append(('Driver', driver_file))
                    
                    # Send videos as media group
                    if videos_for_group:
                        try:
                            media_group = []
                            video_files = []
                            
                            for i, (video_name, video_path) in enumerate(videos_for_group):
                                video_file = open(video_path, 'rb')
                                video_files.append(video_file)
                                
                                caption = f"{message}\nVideos: {', '.join([n for n, _ in videos_for_group])}" if i == 0 else None
                                
                                media_group.append(InputMediaVideo(
                                    media=video_file,
                                    caption=caption,
                                    parse_mode='Markdown' if caption else None
                                ))
                            
                            await self.telegram_bot.send_media_group(
                                chat_id=self.chat_id,
                                media=media_group,
                                read_timeout=240,
                                write_timeout=240
                            )
                            logger.info(f"Media group sent for event {event_id}")
                            
                            for vf in video_files:
                                try:
                                    vf.close()
                                except:
                                    pass
                            
                        except Exception as media_error:
                            logger.warning(f"Media group failed, trying individual videos: {media_error}")
                            
                            for vf in video_files:
                                try:
                                    vf.close()
                                except:
                                    pass
                            
                            for i, (video_name, video_path) in enumerate(videos_for_group):
                                try:
                                    with open(video_path, 'rb') as vf:
                                        cap = f"{message}\nVideo: {video_name}" if i == 0 else f"Video: {video_name}"
                                        await self.telegram_bot.send_video(
                                            chat_id=self.chat_id,
                                            video=vf,
                                            caption=cap,
                                            parse_mode='Markdown',
                                            read_timeout=180,
                                            write_timeout=180
                                        )
                                    logger.info(f"Video sent for event {event_id}")
                                    await asyncio.sleep(2)
                                except Exception as e:
                                    logger.error(f"Video send failed: {e}")
                    else:
                        await self.telegram_bot.send_message(
                            chat_id=self.chat_id,
                            text=f"{message}\n\nVideos unavailable",
                            parse_mode='Markdown'
                        )
                else:
                    await self.telegram_bot.send_message(
                        chat_id=self.chat_id,
                        text=f"{message}\n\nNo camera media",
                        parse_mode='Markdown'
                    )
                
                return  # Success
                
            except (NetworkError, TimedOut) as e:
                logger.warning(f"Network error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
            except TelegramError as e:
                if "file too large" in str(e).lower():
                    try:
                        await self.telegram_bot.send_message(
                            chat_id=self.chat_id,
                            text=f"{message}\n\nFiles too large",
                            parse_mode='Markdown'
                        )
                    except Exception as e2:
                        logger.error(f"Fallback failed: {e2}")
                else:
                    logger.error(f"Telegram error: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
            
            finally:
                # Clean up temporary files
                for temp_file in temp_files:
                    try:
                        if os.path.exists(temp_file):
                            os.remove(temp_file)
                    except Exception as e:
                        logger.error(f"Cleanup error: {e}")
    
    def process_new_events_sync(self):
        """Synchronous wrapper for async event processing"""
        try:
            asyncio.run(self._process_new_events_async())
        except Exception as e:
            logger.error(f"Error in event processing: {e}")
            self.consecutive_failures += 1
        finally:
            self.is_processing = False
    
    async def _process_new_events_async(self):
        """Main async event processing logic"""
        if self.is_processing:
            logger.warning("Previous check still running, skipping")
            return
        
        self.is_processing = True
        start_time = datetime.now()
        
        try:
            logger.info("Starting event check...")
            
            # Process speeding events
            speeding_events = self.fetch_speeding_events()
            if speeding_events is not None:
                new_speeding = self.filter_new_speeding_events(speeding_events)
                if new_speeding:
                    logger.info(f"Processing {len(new_speeding)} speeding events")
                    latest_id = 0
                    for event in new_speeding:
                        await self.send_speeding_event_to_telegram(event)
                        latest_id = max(latest_id, event.get('id', 0))
                        await asyncio.sleep(2)
                    
                    if latest_id > 0:
                        self.save_last_processed_event_id(latest_id, 'speeding')
            
            # Process performance events
            performance_events = self.fetch_driver_performance_events()
            if performance_events is not None:
                new_performance = self.filter_new_performance_events(performance_events)
                if new_performance:
                    logger.info(f"Processing {len(new_performance)} performance events")
                    latest_by_type = {}
                    
                    for event in new_performance:
                        await self.send_performance_event_to_telegram(event)
                        event_type = event.get('type', '')
                        event_id = event.get('id', 0)
                        latest_by_type[event_type] = max(latest_by_type.get(event_type, 0), event_id)
                        await asyncio.sleep(2)
                    
                    for event_type, latest_id in latest_by_type.items():
                        self.save_last_processed_event_id_for_type(latest_id, event_type)
            
            # Update health
            self.last_successful_check = datetime.now()
            self.consecutive_failures = 0
            
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"Event check completed in {duration:.1f}s")
            
        except Exception as e:
            logger.error(f"Critical error in event processing: {e}")
            self.consecutive_failures += 1
            if self.consecutive_failures >= self.max_consecutive_failures:
                try:
                    await self.telegram_bot.send_message(
                        chat_id=self.chat_id,
                        text=f"CRITICAL: SafetyBot has failed {self.consecutive_failures} times.\n\nError: {str(e)[:100]}",
                        parse_mode='Markdown'
                    )
                except Exception as e2:
                    logger.error(f"Failed to send alert: {e2}")
    
    async def health_check(self):
        """Perform health check and send status"""
        try:
            logger.info("Running health check...")
            
            # Test API connectivity
            speeding_test = self.fetch_speeding_events()
            performance_test = self.fetch_driver_performance_events()
            apis_ok = (speeding_test is not None and performance_test is not None)
            
            # Test Telegram connectivity
            telegram_ok = False
            try:
                await self.telegram_bot.get_me()
                telegram_ok = True
            except Exception as e:
                logger.error(f"Telegram health check failed: {e}")
            
            # Determine overall status
            overall_ok = apis_ok and telegram_ok
            status = "Healthy" if overall_ok else "Issues Detected"
            
            last_check_str = "Never" if not self.last_successful_check else f"{(datetime.now() - self.last_successful_check).total_seconds() / 60:.1f}m ago"
            
            health_msg = f"""Health Report
Status: {status}
Last Check: {last_check_str}
Failures: {self.consecutive_failures}
API: {'OK' if apis_ok else 'FAILED'}
Telegram: {'OK' if telegram_ok else 'FAILED'}
Interval: {self.check_interval // 60}m"""
            
            await self.telegram_bot.send_message(
                chat_id=self.chat_id,
                text=health_msg,
                parse_mode='Markdown'
            )
            
            logger.info(f"Health check completed - Status: {status}")
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
    
    def run_scheduler(self):
        """Main scheduler loop - runs in main thread"""
        # Schedule event checks
        schedule.every(self.check_interval).seconds.do(self.process_new_events_sync)
        logger.info(f"Scheduled event check every {self.check_interval}s ({self.check_interval/60:.1f}m)")
        
        # Schedule health checks
        schedule.every().hour.do(lambda: asyncio.run(self.health_check()))
        logger.info("Scheduled health check every hour")
        
        # Run initial check
        logger.info("Running initial event check...")
        self.process_new_events_sync()
        
        # Main loop
        logger.info("SafetyBot v2.0 is now monitoring")
        print("\n" + "="*50)
        print("SafetyBot v2.0 is running")
        print(f"Check interval: {self.check_interval // 60} minutes")
        print(f"Monitoring: Speeding & Performance Events")
        print("Press Ctrl+C to stop")
        print("="*50 + "\n")
        
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(10)  # Check scheduler every 10 seconds
            except KeyboardInterrupt:
                logger.info("Bot stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                time.sleep(30)
    
    def start(self):
        """Start the bot"""
        try:
            # Test connections first
            logger.info("Testing connections...")
            asyncio.run(self._test_connections())
            
            # Start the scheduler
            self.run_scheduler()
            
        except Exception as e:
            logger.error(f"Fatal error during startup: {e}")
            sys.exit(1)
    
    async def _test_connections(self):
        """Test API and Telegram connections"""
        try:
            logger.info("Testing Telegram connection...")
            bot_info = await self.telegram_bot.get_me()
            logger.info(f"Telegram connected: {bot_info.username}")
            
            await self.telegram_bot.send_message(
                chat_id=self.chat_id,
                text="SafetyBot v2.0 Started\nCheck Interval: " + str(self.check_interval // 60) + "m\nReady to monitor",
                parse_mode='Markdown'
            )
            logger.info("Telegram startup message sent")
            
        except Exception as e:
            logger.error(f"Telegram connection test failed: {e}")
            raise
        
        try:
            logger.info("Testing API connections...")
            speeding = self.fetch_speeding_events()
            performance = self.fetch_driver_performance_events()
            
            s_count = len(speeding) if speeding else 0
            p_count = len(performance) if performance else 0
            
            logger.info(f"API test successful: {s_count} speeding, {p_count} performance events")
            
        except Exception as e:
            logger.error(f"API connection test failed: {e}")
            raise

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