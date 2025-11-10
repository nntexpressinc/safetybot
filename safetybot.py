#!/usr/bin/env python3
"""
Safety Bot - Enhanced with Screenshot Functionality
Monitors speeding and driver performance events with production-grade reliability
Now includes automated web screenshots from GoMotive platform
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
from telegram import Bot, InputMediaVideo, InputMediaPhoto
from telegram.error import TelegramError, NetworkError, TimedOut

# Selenium imports for screenshot functionality
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, WebDriverException

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

class GoMotiveScreenshotManager:
    """Manages browser automation and screenshots for GoMotive platform"""
    
    LOGIN_URL = "https://account.gomotive.com/log-in"
    SPEEDING_URL_TEMPLATE = "https://app.gomotive.com/en-US/#/safety/speeding/{id};start_time={start_time}"
    
    def __init__(self, email: str, password: str):
        """Initialize screenshot manager with login credentials"""
        self.email = email
        self.password = password
        self.driver = None
        self.is_logged_in = False
        self.last_login_time = None
        self.session_timeout = timedelta(hours=2)  # Re-login after 2 hours
        
    def _setup_driver(self):
        """Set up Chrome driver with headless options"""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # Try to create driver
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.set_page_load_timeout(30)
            logger.info("[SCREENSHOT] Chrome driver initialized")
            return True
            
        except Exception as e:
            logger.error(f"[SCREENSHOT] Failed to initialize driver: {e}")
            return False
    
    def _check_session_valid(self) -> bool:
        """Check if current session is still valid"""
        if not self.is_logged_in or not self.last_login_time:
            return False
        
        if datetime.now() - self.last_login_time > self.session_timeout:
            logger.info("[SCREENSHOT] Session expired, need to re-login")
            return False
        
        return True
    
    async def login(self) -> bool:
        """Login to GoMotive platform"""
        max_retries = 2
        
        for attempt in range(max_retries):
            try:
                logger.info(f"[SCREENSHOT] Logging in (attempt {attempt + 1}/{max_retries})...")
                
                # Setup driver if needed
                if not self.driver:
                    if not self._setup_driver():
                        return False
                
                # Navigate to login page
                self.driver.get(self.LOGIN_URL)
                await asyncio.sleep(3)  # Wait for page to fully load
                
                # Wait for email field to be clickable (not just present)
                # Based on actual GoMotive HTML: id="user_email", name="user[email]"
                email_field = None
                selectors = [
                    (By.ID, "user_email"),
                    (By.NAME, "user[email]"),
                    (By.CSS_SELECTOR, "input[name='user[email]']")
                ]
                
                for by, selector in selectors:
                    try:
                        email_field = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable((by, selector))
                        )
                        logger.info(f"[SCREENSHOT] Email field found using: {by}={selector}")
                        break
                    except TimeoutException:
                        continue
                
                if not email_field:
                    logger.error("[SCREENSHOT] Could not find email field")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(3)
                        continue
                    return False
                
                # Scroll to element and enter email
                self.driver.execute_script("arguments[0].scrollIntoView(true);", email_field)
                await asyncio.sleep(0.5)
                
                try:
                    email_field.clear()
                    email_field.send_keys(self.email)
                except:
                    # Fallback to JavaScript
                    self.driver.execute_script(f"arguments[0].value = '{self.email}';", email_field)
                
                logger.info("[SCREENSHOT] Email entered")
                
                # Find password field - Based on actual HTML: id="user_password", name="user[password]"
                password_field = None
                password_selectors = [
                    (By.ID, "user_password"),
                    (By.NAME, "user[password]"),
                    (By.CSS_SELECTOR, "input[name='user[password]']")
                ]
                
                for by, selector in password_selectors:
                    try:
                        password_field = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable((by, selector))
                        )
                        logger.info(f"[SCREENSHOT] Password field found using: {by}={selector}")
                        break
                    except TimeoutException:
                        continue
                
                if not password_field:
                    logger.error("[SCREENSHOT] Could not find password field")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(3)
                        continue
                    return False
                
                # Scroll and enter password
                self.driver.execute_script("arguments[0].scrollIntoView(true);", password_field)
                await asyncio.sleep(0.5)
                
                try:
                    password_field.clear()
                    password_field.send_keys(self.password)
                except:
                    # Fallback to JavaScript
                    self.driver.execute_script(f"arguments[0].value = '{self.password}';", password_field)
                
                logger.info("[SCREENSHOT] Password entered")
                
                # Find and click login button - Based on actual HTML: id="sign-in-button"
                login_button = None
                button_selectors = [
                    (By.ID, "sign-in-button"),
                    (By.CSS_SELECTOR, "button[type='submit']"),
                    (By.XPATH, "//button[@id='sign-in-button']")
                ]
                
                for by, selector in button_selectors:
                    try:
                        login_button = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable((by, selector))
                        )
                        logger.info(f"[SCREENSHOT] Login button found using: {by}={selector}")
                        break
                    except TimeoutException:
                        continue
                
                if not login_button:
                    logger.error("[SCREENSHOT] Could not find login button")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(3)
                        continue
                    return False
                
                # Scroll to button and click
                self.driver.execute_script("arguments[0].scrollIntoView(true);", login_button)
                await asyncio.sleep(0.5)
                
                try:
                    login_button.click()
                except:
                    # Fallback to JavaScript click
                    self.driver.execute_script("arguments[0].click();", login_button)
                
                logger.info("[SCREENSHOT] Login button clicked")
                
                # Wait for successful login (dashboard or main page)
                await asyncio.sleep(5)
                
                # Check if we're logged in by looking for URL change
                if "log-in" not in self.driver.current_url.lower():
                    self.is_logged_in = True
                    self.last_login_time = datetime.now()
                    logger.info(f"[SCREENSHOT] Login successful - Current URL: {self.driver.current_url}")
                    return True
                else:
                    logger.warning(f"[SCREENSHOT] Login may have failed - still on login page: {self.driver.current_url}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(3)
                        continue
                
            except TimeoutException:
                logger.error(f"[SCREENSHOT] Timeout during login (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(3)
            except Exception as e:
                logger.error(f"[SCREENSHOT] Error during login: {e}")
                import traceback
                logger.error(traceback.format_exc())
                if attempt < max_retries - 1:
                    await asyncio.sleep(3)
        
        return False
    
    async def capture_speeding_event_screenshot(self, event_id: int, start_time: str) -> Optional[str]:
        """
        Capture screenshot of speeding event page
        Returns path to screenshot file or None if failed
        """
        try:
            # Ensure we're logged in
            if not self._check_session_valid():
                logger.info("[SCREENSHOT] Session invalid, logging in...")
                login_success = await self.login()
                if not login_success:
                    logger.error("[SCREENSHOT] Failed to login, cannot capture screenshot")
                    return None
            
            # Build URL
            url = self.SPEEDING_URL_TEMPLATE.format(id=event_id, start_time=start_time)
            logger.info(f"[SCREENSHOT] Navigating to: {url}")
            
            # Navigate to speeding event page
            self.driver.get(url)
            
            # Wait for initial page load
            logger.info("[SCREENSHOT] Waiting for page to load...")
            await asyncio.sleep(5)
            
            # Wait for map/content to be visible - Angular app takes time to render
            logger.info("[SCREENSHOT] Waiting for content to render...")
            try:
                # Wait for map container or main content
                WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div[class*='map'], canvas, svg"))
                )
                logger.info("[SCREENSHOT] Map/content detected")
            except TimeoutException:
                logger.warning("[SCREENSHOT] Map/content not found, continuing anyway...")
            
            # Additional wait for Angular to finish rendering
            logger.info("[SCREENSHOT] Waiting for data to populate (15 seconds)...")
            await asyncio.sleep(15)
            
            # Scroll to top to ensure we capture from beginning
            self.driver.execute_script("window.scrollTo(0, 0);")
            await asyncio.sleep(1)
            
            # Take screenshot
            screenshot_filename = f"speeding_event_{event_id}_{uuid.uuid4().hex}.png"
            screenshot_path = os.path.join(tempfile.gettempdir(), screenshot_filename)
            
            # Capture full page screenshot (no JavaScript manipulation)
            logger.info("[SCREENSHOT] Capturing screenshot...")
            self.driver.save_screenshot(screenshot_path)
            
            # Verify screenshot was created
            if os.path.exists(screenshot_path) and os.path.getsize(screenshot_path) > 0:
                size_kb = os.path.getsize(screenshot_path) / 1024
                logger.info(f"[SCREENSHOT] Screenshot captured ({size_kb:.1f}KB): {screenshot_path}")
                return screenshot_path
            else:
                logger.error("[SCREENSHOT] Screenshot file is empty or not created")
                return None
                
        except Exception as e:
            logger.error(f"[SCREENSHOT] Error capturing screenshot: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def cleanup(self):
        """Clean up browser resources"""
        try:
            if self.driver:
                self.driver.quit()
                self.driver = None
                self.is_logged_in = False
                logger.info("[SCREENSHOT] Browser cleaned up")
        except Exception as e:
            logger.error(f"[SCREENSHOT] Error during cleanup: {e}")


class SafetyBot:
    """Main bot class for monitoring GoMotive APIs and sending Telegram alerts"""
    
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
        
        # GoMotive web credentials for screenshots
        self.gomotive_email = os.getenv('GOMOTIVE_EMAIL', 'accounting@ldubet.com')
        self.gomotive_password = os.getenv('GOMOTIVE_PASSWORD', 'Nnt2014$')
        self.enable_screenshots = os.getenv('ENABLE_SCREENSHOTS', 'true').lower() == 'true'
        
        # Health monitoring
        self.last_successful_check = None
        self.consecutive_failures = 0
        self.max_consecutive_failures = 5
        self.critical_alert_sent = False
        
        # Event tracking files
        self.processed_speeding_ids_file = 'processed_speeding_event_ids.json'
        self.processed_performance_ids_file = 'processed_performance_event_ids.json'
        
        # Load processed IDs from files
        self.processed_speeding_ids = self._load_processed_ids(self.processed_speeding_ids_file)
        self.processed_performance_ids = self._load_processed_ids(self.processed_performance_ids_file)
        
        # Deduplication within current cycle
        self.processed_event_ids: Set[int] = set()
        
        # Concurrency and shutdown control
        self.is_processing = False
        self.running = True
        self.shutdown_lock = threading.Lock()
        
        # Screenshot manager
        self.screenshot_manager = None
        if self.enable_screenshots:
            try:
                self.screenshot_manager = GoMotiveScreenshotManager(
                    self.gomotive_email,
                    self.gomotive_password
                )
                logger.info("[INIT] Screenshot functionality enabled")
            except Exception as e:
                logger.error(f"[INIT] Failed to initialize screenshot manager: {e}")
                self.enable_screenshots = False
        
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
            
            if self.screenshot_manager:
                self.screenshot_manager.cleanup()
            
            logger.info("Cleanup completed successfully")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def _init_session(self):
        """Initialize requests session with retry strategy"""
        self.headers = {
            'accept': 'application/json',
            'x-api-key': self.api_key,
            'User-Agent': 'SafetyBot/2.2'
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
    
    def _load_processed_ids(self, filename: str) -> Set[int]:
        """Load processed event IDs from JSON file"""
        try:
            if os.path.exists(filename):
                with open(filename, 'r') as f:
                    data = json.load(f)
                    # Keep only recent IDs (last 1000 to prevent file from growing too large)
                    ids = set(data) if isinstance(data, list) else set()
                    if len(ids) > 1000:
                        # Keep only the highest 1000 IDs
                        ids = set(sorted(ids, reverse=True)[:1000])
                    logger.info(f"[INIT] Loaded {len(ids)} processed IDs from {filename}")
                    return ids
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Could not read processed IDs from {filename}: {e}")
        return set()
    
    def _save_processed_ids(self, ids: Set[int], filename: str):
        """Save processed event IDs to JSON file"""
        try:
            # Keep only recent IDs (last 1000)
            ids_to_save = sorted(ids, reverse=True)[:1000]
            with open(filename, 'w') as f:
                json.dump(ids_to_save, f)
            logger.debug(f"[ID_SAVED] Saved {len(ids_to_save)} IDs to {filename}")
        except Exception as e:
            logger.error(f"Could not save processed IDs to {filename}: {e}")
    
    def _has_allowed_severity(self, event: Dict[str, Any]) -> bool:
        """Check if event has allowed severity"""
        metadata = event.get('metadata', {})
        severity = metadata.get('severity')
        return severity in ['medium', 'high', 'critical']
    
    def _is_event_processed(self, event_id: int, event_type: str = 'speeding') -> bool:
        """Check if event was already processed and sent"""
        if event_type == 'speeding':
            return event_id in self.processed_speeding_ids
        else:
            return event_id in self.processed_performance_ids
    
    def _mark_event_processed(self, event_id: int, event_type: str = 'speeding'):
        """Mark event as processed and save to file"""
        if event_type == 'speeding':
            self.processed_speeding_ids.add(event_id)
            self._save_processed_ids(self.processed_speeding_ids, self.processed_speeding_ids_file)
        else:
            self.processed_performance_ids.add(event_id)
            self._save_processed_ids(self.processed_performance_ids, self.processed_performance_ids_file)
        
        logger.info(f"[ID_MARKED] {event_type} event {event_id} marked as processed")
    
    def _is_already_processed(self, event_id: int) -> bool:
        """Check if event was already processed in this cycle (legacy method for compatibility)"""
        return event_id in self.processed_event_ids
    
    def _mark_processed(self, event_id: int):
        """Mark event as processed in this cycle (legacy method for compatibility)"""
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
            logger.info(f"[ID_SAVED] {event_type}: {event_id}")
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
            logger.info(f"[ID_SAVED] {event_type}: {event_id}")
        except IOError as e:
            logger.error(f"Error saving last {event_type} event ID: {e}")
    
    def fetch_speeding_events(self) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        """Fetch speeding events from GoMotive v1 API. Returns (events, error_code)"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                params = {'per_page': '25', 'page_no': '1'}
                url = f"{self.api_base_url.replace('v2', 'v1')}/speeding_events"
                
                logger.info(f"Fetching speeding events (attempt {attempt + 1}/{max_retries})")
                response = self.session.get(url, headers=self.headers, params=params, timeout=45)
                
                if response.status_code == 401:
                    logger.error("API Authentication failed (401) - Invalid API key")
                    return None, "AUTH_ERROR"
                elif response.status_code == 403:
                    logger.error("API Permission denied (403)")
                    return None, "PERMISSION_ERROR"
                elif response.status_code == 404:
                    logger.error("API Endpoint not found (404)")
                    return None, "NOT_FOUND"
                
                response.raise_for_status()
                
                if not response.content:
                    logger.warning("Empty response from speeding events API")
                    return [], None
                
                data = response.json()
                events = data.get('speeding_events', [])
                
                if not isinstance(events, list):
                    logger.warning("Unexpected data structure in speeding events response")
                    return [], None
                
                logger.info(f"Successfully fetched {len(events)} speeding events")
                return events, None
                
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
        return None, "FETCH_ERROR"
    
    def fetch_driver_performance_events(self) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        """Fetch driver performance events from GoMotive v2 API. Returns (events, error_code)"""
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
                    logger.info(f"Fetching {event_type} events (attempt {attempt + 1}/{max_retries})")
                    response = self.session.get(url, headers=self.headers, params=params, timeout=45)
                    
                    if response.status_code == 401:
                        logger.error(f"API Authentication failed (401) for {event_type}")
                        if not first_error:
                            first_error = "AUTH_ERROR"
                        break
                    elif response.status_code == 403:
                        logger.error(f"API Permission denied (403) for {event_type}")
                        if not first_error:
                            first_error = "PERMISSION_ERROR"
                        break
                    
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
                    logger.error(f"Request error fetching {event_type} events: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                except Exception as e:
                    logger.error(f"Unexpected error fetching {event_type} events: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
            
            time.sleep(1)
        
        logger.info(f"Successfully fetched {len(all_events)} total performance events")
        return all_events, first_error
    
    def filter_new_speeding_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter speeding events that haven't been processed yet"""
        new_events = []
        
        for event_data in events:
            event = event_data.get('speeding_event', {})
            event_id = event.get('id', 0)
            
            # Check if event has allowed severity and hasn't been processed
            if self._has_allowed_severity(event) and not self._is_event_processed(event_id, 'speeding'):
                new_events.append(event)
        
        new_events.sort(key=lambda x: x.get('id', 0))
        logger.info(f"Found {len(new_events)} new speeding events to process")
        
        return new_events
    
    def filter_new_performance_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter performance events that haven't been processed yet"""
        new_events = []
        
        for event_data in events:
            event = event_data.get('driver_performance_event', {})
            event_id = event.get('id', 0)
            event_type = event.get('type', '')
            
            # Check if event type is allowed, has allowed severity, and hasn't been processed
            if (event_type in self.ALLOWED_EVENT_TYPES and 
                self._has_allowed_severity(event) and 
                not self._is_event_processed(event_id, 'performance')):
                new_events.append(event)
        
        new_events.sort(key=lambda x: x.get('id', 0))
        logger.info(f"Found {len(new_events)} new performance events to process")
        
        return new_events
    
    def format_time(self, time_str: str, latitude: Optional[float] = None, longitude: Optional[float] = None) -> str:
        """Format time string to readable format with timezone conversion using longitude offset"""
        try:
            import pytz
            
            dt_utc = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
            dt_utc = dt_utc.astimezone(pytz.UTC)
            
            tz_local = None
            if longitude is not None:
                if longitude >= -125 and longitude < -120:
                    tz_local = pytz.timezone('America/Los_Angeles')
                elif longitude >= -120 and longitude < -104:
                    tz_local = pytz.timezone('America/Denver')
                elif longitude >= -104 and longitude < -87:
                    tz_local = pytz.timezone('America/Chicago')
                elif longitude >= -87 and longitude <= -60:
                    tz_local = pytz.timezone('America/New_York')
                else:
                    tz_local = pytz.timezone('America/Los_Angeles')
            else:
                tz_local = pytz.timezone('America/Los_Angeles')
            
            dt_local = dt_utc.astimezone(tz_local)
            dt_local = dt_local - timedelta(hours=1)
            
            formatted = dt_local.strftime('%m/%d/%Y %I:%M %p')
            return formatted
            
        except Exception as e:
            logger.error(f"[TZ_ERROR] Error formatting time '{time_str}': {e}")
            return time_str
    
    def format_speeding_message(self, event: Dict[str, Any]) -> Optional[str]:
        """Format speeding event message. Returns None if formatting fails."""
        try:
            vehicle_number = event.get('vehicle', {}).get('number', 'N/A')
            driver = event.get('driver', {})
            driver_name = f"{driver.get('first_name', '')} {driver.get('last_name', '')}".strip() or 'Unknown'
            
            start_lat = event.get('start_lat')
            start_lon = event.get('start_lon')
            date_time = self.format_time(event.get('start_time', ''), start_lat, start_lon)
            
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
            logger.error(f"[FORMAT_ERROR] Error formatting speeding message: {e}")
            return None
    
    def format_performance_message(self, event: Dict[str, Any]) -> Optional[str]:
        """Format performance event message. Returns None if formatting fails."""
        try:
            event_type = event.get('type', 'Unknown').replace('_', ' ').title()
            vehicle_number = event.get('vehicle', {}).get('number', 'N/A')
            driver = event.get('driver', {})
            driver_name = f"{driver.get('first_name', '')} {driver.get('last_name', '')}".strip() or 'Unknown'
            
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
            logger.error(f"[FORMAT_ERROR] Error formatting performance message: {e}")
            return None
    
    async def download_video_to_temp_file(self, video_url: str, video_type: str = "video") -> Optional[str]:
        """Download video and save to temporary file. Returns path or None."""
        max_retries = 2
        for attempt in range(max_retries):
            try:
                logger.info(f"Downloading {video_type} (attempt {attempt + 1}/{max_retries})")
                
                response = self.session.get(video_url, timeout=self.VIDEO_DOWNLOAD_TIMEOUT, stream=True)
                response.raise_for_status()
                video_data = response.content
                
                if not video_data:
                    logger.warning(f"[VIDEO] Empty video data for {video_type}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(3)
                    continue
                
                size_mb = len(video_data) / (1024 * 1024)
                logger.info(f"[VIDEO] {video_type} size: {size_mb:.1f}MB")
                
                if size_mb > self.MAX_VIDEO_SIZE_MB:
                    logger.warning(f"[VIDEO] {video_type} exceeds max size ({size_mb:.1f}MB > {self.MAX_VIDEO_SIZE_MB}MB)")
                    return None
                
                if size_mb < 0.01:
                    logger.warning(f"[VIDEO] {video_type} too small ({size_mb:.3f}MB)")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(3)
                    continue
                
                temp_filename = f"{video_type}_{uuid.uuid4().hex}.mp4"
                temp_file_path = os.path.join(tempfile.gettempdir(), temp_filename)
                
                with open(temp_file_path, 'wb') as temp_file:
                    temp_file.write(video_data)
                
                if os.path.exists(temp_file_path) and os.path.getsize(temp_file_path) > 0:
                    logger.info(f"[VIDEO] {video_type} ({size_mb:.1f}MB) saved successfully")
                    return temp_file_path
                else:
                    logger.error(f"[VIDEO] Failed to create {video_type} file")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(3)
                
            except requests.exceptions.Timeout:
                logger.warning(f"[VIDEO] Timeout downloading {video_type}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
            except requests.exceptions.RequestException as e:
                logger.error(f"[VIDEO] Request error: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"[VIDEO] Unexpected error: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
        
        logger.error(f"[VIDEO] Failed to download {video_type}")
        return None
    
    async def send_speeding_event_to_telegram(self, event: Dict[str, Any]) -> bool:
        """Send speeding event to Telegram with screenshot. Returns True if sent."""
        event_id = event.get('id', 0)
        message = self.format_speeding_message(event)
        
        if message is None:
            logger.warning(f"[SKIP] Speeding event {event_id} - formatting failed")
            return False
        
        max_retries = 3
        screenshot_path = None
        
        try:
            # Capture screenshot if enabled
            if self.enable_screenshots and self.screenshot_manager:
                start_time = event.get('start_time', '')
                screenshot_path = await self.screenshot_manager.capture_speeding_event_screenshot(
                    event_id, start_time
                )
            
            # Send with screenshot if available
            if screenshot_path and os.path.exists(screenshot_path):
                for attempt in range(max_retries):
                    try:
                        with open(screenshot_path, 'rb') as photo:
                            await self.telegram_bot.send_photo(
                                chat_id=self.chat_id,
                                photo=photo,
                                caption=message,
                                parse_mode='Markdown',
                                read_timeout=self.TELEGRAM_SEND_TIMEOUT,
                                write_timeout=self.TELEGRAM_SEND_TIMEOUT
                            )
                        logger.info(f"[SENT] Speeding event {event_id} with screenshot")
                        self._mark_event_processed(event_id, 'speeding')
                        
                        # Clean up screenshot immediately after successful send
                        if screenshot_path and os.path.exists(screenshot_path):
                            try:
                                os.remove(screenshot_path)
                                logger.debug(f"[CLEANUP] Removed screenshot: {screenshot_path}")
                                screenshot_path = None  # Mark as cleaned
                            except Exception as e:
                                logger.error(f"[CLEANUP] Error removing screenshot: {e}")
                        
                        return True
                    except (NetworkError, TimedOut) as e:
                        logger.warning(f"[RETRY] Network error (attempt {attempt + 1}/{max_retries}): {e}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2 ** attempt)
                    except TelegramError as e:
                        logger.error(f"[ERROR] Telegram API error: {e}")
                        break
            else:
                # Send without screenshot
                for attempt in range(max_retries):
                    try:
                        await self.telegram_bot.send_message(
                            chat_id=self.chat_id,
                            text=message,
                            parse_mode='Markdown',
                            read_timeout=self.TELEGRAM_SEND_TIMEOUT,
                            write_timeout=self.TELEGRAM_SEND_TIMEOUT
                        )
                        logger.info(f"[SENT] Speeding event {event_id} (no screenshot)")
                        self._mark_event_processed(event_id, 'speeding')
                        return True
                    except (NetworkError, TimedOut) as e:
                        logger.warning(f"[RETRY] Network error (attempt {attempt + 1}/{max_retries}): {e}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2 ** attempt)
                    except TelegramError as e:
                        logger.error(f"[ERROR] Telegram API error: {e}")
                        return False
                    except Exception as e:
                        logger.error(f"[ERROR] Unexpected error (attempt {attempt + 1}/{max_retries}): {e}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2 ** attempt)
            
        finally:
            # Clean up screenshot
            if screenshot_path and os.path.exists(screenshot_path):
                try:
                    os.remove(screenshot_path)
                    logger.debug(f"[CLEANUP] Removed screenshot: {screenshot_path}")
                except Exception as e:
                    logger.error(f"[CLEANUP] Error removing screenshot: {e}")
        
        logger.error(f"[FAILED] Could not send speeding event {event_id}")
        return False
    
    async def send_performance_event_to_telegram(self, event: Dict[str, Any]) -> bool:
        """Send performance event to Telegram with video. Returns True if sent."""
        event_id = event.get('id', 0)
        message = self.format_performance_message(event)
        
        if message is None:
            logger.warning(f"[SKIP] Performance event {event_id} - formatting failed")
            return False
        
        max_retries = 3
        for attempt in range(max_retries):
            temp_files = []
            try:
                camera_media = event.get('camera_media', {})
                
                if camera_media and camera_media.get('available'):
                    downloadable_videos = camera_media.get('downloadable_videos', {})
                    front_facing_url = downloadable_videos.get('front_facing_plain_url')
                    driver_facing_url = downloadable_videos.get('driver_facing_plain_url')
                    
                    videos_for_group = []
                    
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
                    
                    if videos_for_group and len(videos_for_group) > 1:
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
                                read_timeout=self.TELEGRAM_SEND_TIMEOUT * 2,
                                write_timeout=self.TELEGRAM_SEND_TIMEOUT * 2
                            )
                            logger.info(f"[SENT] Media group for event {event_id}")
                            self._mark_event_processed(event_id, 'performance')
                            
                            # Clean up video files immediately after successful send
                            for temp_file in temp_files:
                                try:
                                    if os.path.exists(temp_file):
                                        os.remove(temp_file)
                                        logger.debug(f"[CLEANUP] Removed temp file: {temp_file}")
                                except Exception as e:
                                    logger.error(f"[CLEANUP] Error removing file: {e}")
                            temp_files.clear()  # Mark as cleaned
                            
                            for vf in video_files:
                                try:
                                    vf.close()
                                except:
                                    pass
                            
                            return True
                            
                        except Exception as media_error:
                            logger.warning(f"[RETRY] Media group failed, trying individual videos: {media_error}")
                            
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
                                            read_timeout=self.TELEGRAM_SEND_TIMEOUT,
                                            write_timeout=self.TELEGRAM_SEND_TIMEOUT
                                        )
                                    logger.info(f"[SENT] Video {video_name} for event {event_id}")
                                    await asyncio.sleep(2)
                                except Exception as e:
                                    logger.error(f"[ERROR] Individual video send failed: {e}")
                            
                            # Clean up video files after individual sends
                            for temp_file in temp_files:
                                try:
                                    if os.path.exists(temp_file):
                                        os.remove(temp_file)
                                        logger.debug(f"[CLEANUP] Removed temp file: {temp_file}")
                                except Exception as e:
                                    logger.error(f"[CLEANUP] Error removing file: {e}")
                            temp_files.clear()
                            
                            self._mark_event_processed(event_id, 'performance')
                            return True
                    
                    elif videos_for_group:
                        for i, (video_name, video_path) in enumerate(videos_for_group):
                            try:
                                with open(video_path, 'rb') as vf:
                                    cap = f"{message}\nVideo: {video_name}" if i == 0 else f"Video: {video_name}"
                                    await self.telegram_bot.send_video(
                                        chat_id=self.chat_id,
                                        video=vf,
                                        caption=cap,
                                        parse_mode='Markdown',
                                        read_timeout=self.TELEGRAM_SEND_TIMEOUT,
                                        write_timeout=self.TELEGRAM_SEND_TIMEOUT
                                    )
                                logger.info(f"[SENT] Video {video_name} for event {event_id}")
                                await asyncio.sleep(2)
                            except Exception as e:
                                logger.error(f"[ERROR] Video send failed: {e}")
                        
                        # Clean up video files after sending
                        for temp_file in temp_files:
                            try:
                                if os.path.exists(temp_file):
                                    os.remove(temp_file)
                                    logger.debug(f"[CLEANUP] Removed temp file: {temp_file}")
                            except Exception as e:
                                logger.error(f"[CLEANUP] Error removing file: {e}")
                        temp_files.clear()
                        
                        self._mark_event_processed(event_id, 'performance')
                        return True
                    else:
                        await self.telegram_bot.send_message(
                            chat_id=self.chat_id,
                            text=f"{message}\n\n❌ Videos unavailable",
                            parse_mode='Markdown',
                            read_timeout=self.TELEGRAM_SEND_TIMEOUT,
                            write_timeout=self.TELEGRAM_SEND_TIMEOUT
                        )
                        logger.info(f"[SENT] Event {event_id} without videos")
                        self._mark_event_processed(event_id, 'performance')
                        return True
                else:
                    await self.telegram_bot.send_message(
                        chat_id=self.chat_id,
                        text=f"{message}\n\n❌ No camera media",
                        parse_mode='Markdown',
                        read_timeout=self.TELEGRAM_SEND_TIMEOUT,
                        write_timeout=self.TELEGRAM_SEND_TIMEOUT
                    )
                    logger.info(f"[SENT] Event {event_id} without camera")
                    self._mark_event_processed(event_id, 'performance')
                    return True
                
            except (NetworkError, TimedOut) as e:
                logger.warning(f"[RETRY] Network error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
            except TelegramError as e:
                if "file too large" in str(e).lower():
                    logger.warning(f"[ERROR] File too large for event {event_id}")
                    try:
                        await self.telegram_bot.send_message(
                            chat_id=self.chat_id,
                            text=f"{message}\n\n⚠️ Files too large to upload",
                            parse_mode='Markdown',
                            read_timeout=self.TELEGRAM_SEND_TIMEOUT,
                            write_timeout=self.TELEGRAM_SEND_TIMEOUT
                        )
                        logger.info(f"[SENT] Event {event_id} with fallback (files too large)")
                        self._mark_event_processed(event_id, 'performance')
                        return True
                    except Exception as e2:
                        logger.error(f"[ERROR] Fallback message failed: {e2}")
                        return False
                else:
                    logger.error(f"[ERROR] Telegram error: {e}")
                    return False
            except Exception as e:
                logger.error(f"[ERROR] Unexpected error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
            
            finally:
                for temp_file in temp_files:
                    try:
                        if os.path.exists(temp_file):
                            os.remove(temp_file)
                            logger.debug(f"[CLEANUP] Removed temp file: {temp_file}")
                    except Exception as e:
                        logger.error(f"[CLEANUP] Error removing file: {e}")
        
        logger.error(f"[FAILED] Could not send performance event {event_id}")
        return False
    
    def process_new_events_sync(self):
        """Synchronous wrapper for async event processing"""
        try:
            asyncio.run(self._process_new_events_async())
        except Exception as e:
            logger.error(f"[CRITICAL] Error in event processing: {e}")
            self.consecutive_failures += 1
        finally:
            self.is_processing = False
    
    async def _process_new_events_async(self):
        """Main async event processing logic"""
        if self.is_processing:
            logger.warning("[SKIP] Previous check still running")
            return
        
        self.is_processing = True
        self._reset_cycle_tracking()
        start_time = datetime.now()
        
        try:
            logger.info("="*60)
            logger.info("Starting event check cycle")
            logger.info("="*60)
            
            # Process speeding events
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
                    logger.info(f"[PROCESS] Processing {len(new_speeding)} speeding events")
                    for event in new_speeding:
                        await self.send_speeding_event_to_telegram(event)
                        await asyncio.sleep(2)
                else:
                    logger.info("[PROCESS] No new speeding events")
            else:
                logger.warning("[FETCH] Failed to fetch speeding events")
            
            # Process performance events
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
                    logger.info(f"[PROCESS] Processing {len(new_performance)} performance events")
                    for event in new_performance:
                        await self.send_performance_event_to_telegram(event)
                        await asyncio.sleep(2)
                else:
                    logger.info("[PROCESS] No new performance events")
            else:
                logger.warning("[FETCH] Failed to fetch performance events")
            
            self.last_successful_check = datetime.now()
            self.consecutive_failures = 0
            self.critical_alert_sent = False
            
            duration = (datetime.now() - start_time).total_seconds()
            logger.info("="*60)
            logger.info(f"Event check completed in {duration:.1f}s")
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
            
            speeding_test, _ = self.fetch_speeding_events()
            performance_test, _ = self.fetch_driver_performance_events()
            apis_ok = (speeding_test is not None and performance_test is not None)
            
            telegram_ok = False
            try:
                await self.telegram_bot.get_me()
                telegram_ok = True
            except Exception as e:
                logger.error(f"[HEALTH] Telegram check failed: {e}")
            
            screenshot_status = "✅ Enabled" if self.enable_screenshots else "⚠️ Disabled"
            
            overall_ok = apis_ok and telegram_ok
            status = "✅ Healthy" if overall_ok else "❌ Issues Detected"
            
            last_check_str = "Never" if not self.last_successful_check else f"{(datetime.now() - self.last_successful_check).total_seconds() / 60:.1f}m ago"
            
            health_msg = f"""Health Report
Status: {status}
Last Check: {last_check_str}
Failures: {self.consecutive_failures}
API: {'✅ OK' if apis_ok else '❌ FAILED'}
Telegram: {'✅ OK' if telegram_ok else '❌ FAILED'}
Screenshots: {screenshot_status}
Interval: {self.check_interval // 60}m
Version: 2.2 Enhanced"""
            
            await self.telegram_bot.send_message(
                chat_id=self.chat_id,
                text=health_msg,
                parse_mode='Markdown'
            )
            
            logger.info(f"[HEALTH] Report sent - Status: {status}")
            
        except Exception as e:
            logger.error(f"[HEALTH] Health check failed: {e}")
    
    def run_scheduler(self):
        """Main scheduler loop - runs in main thread"""
        schedule.every(self.check_interval).seconds.do(self.process_new_events_sync)
        logger.info(f"[SCHEDULER] Event check every {self.check_interval}s ({self.check_interval/60:.1f}m)")
        
        schedule.every().hour.do(lambda: asyncio.run(self.health_check()))
        logger.info("[SCHEDULER] Health check every hour")
        
        logger.info("[STARTUP] Running initial event check...")
        self.process_new_events_sync()
        
        logger.info("[STARTUP] SafetyBot v2.2 Enhanced is now monitoring")
        print("\n" + "="*60)
        print("SafetyBot v2.2 Enhanced - Production Ready")
        print(f"Check interval: {self.check_interval // 60} minutes")
        print(f"Monitoring: Speeding & 6 Performance Events")
        print(f"Screenshots: {'Enabled' if self.enable_screenshots else 'Disabled'}")
        print("Separate ID tracking for each event type")
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
    
    def start(self):
        """Start the bot"""
        try:
            logger.info("[STARTUP] Testing connections...")
            asyncio.run(self._test_connections())
            
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
            
            screenshot_status = "📸 Enabled" if self.enable_screenshots else "⚠️ Disabled"
            
            await self.telegram_bot.send_message(
                chat_id=self.chat_id,
                text=f"✅ SafetyBot v2.2 Enhanced Started\nCheck Interval: {self.check_interval // 60}m\nScreenshots: {screenshot_status}\nReady to monitor",
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