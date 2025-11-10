#!/usr/bin/env python3
"""
GoMotive Login Test Script
Tests login functionality and Chrome setup
"""

import os
import sys
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException

# Login credentials
EMAIL = "accounting@ldubet.com"
PASSWORD = "Nnt2014$"
LOGIN_URL = "https://account.gomotive.com/log-in"

def setup_driver(headless=True):
    """Setup Chrome driver with options"""
    print("=" * 60)
    print("STEP 1: Setting up Chrome driver...")
    print("=" * 60)
    
    try:
        chrome_options = Options()
        
        if headless:
            chrome_options.add_argument('--headless')
            print("✓ Running in headless mode")
        else:
            print("✓ Running with visible browser")
        
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Enable verbose logging
        chrome_options.add_argument('--verbose')
        chrome_options.add_argument('--log-level=0')
        
        print("✓ Chrome options configured")
        print("\nAttempting to create Chrome driver...")
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(30)
        
        print("✓ Chrome driver created successfully!")
        print(f"✓ Chrome version: {driver.capabilities.get('browserVersion', 'unknown')}")
        print(f"✓ ChromeDriver version: {driver.capabilities.get('chrome', {}).get('chromedriverVersion', 'unknown')}")
        
        return driver
        
    except WebDriverException as e:
        print("\n❌ FAILED to create Chrome driver!")
        print(f"Error: {e}")
        print("\nPossible causes:")
        print("  1. Chrome/Chromium not installed")
        print("  2. ChromeDriver not found or incompatible")
        print("  3. Missing system libraries")
        print("  4. Insufficient memory/disk space")
        print("\nTry running:")
        print("  sudo apt install chromium-browser chromium-chromedriver -y")
        return None
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return None

def test_login(driver):
    """Test login to GoMotive"""
    print("\n" + "=" * 60)
    print("STEP 2: Testing login to GoMotive...")
    print("=" * 60)
    
    try:
        # Navigate to login page
        print(f"\n→ Navigating to: {LOGIN_URL}")
        driver.get(LOGIN_URL)
        
        # Wait longer for page to fully load
        print("→ Waiting for page to fully load...")
        time.sleep(3)
        
        print(f"✓ Page loaded: {driver.current_url}")
        print(f"✓ Page title: {driver.title}")
        
        # Wait for email field to be clickable (not just present)
        print("\n→ Looking for email field...")
        email_field = None
        
        # Try multiple selectors with proper wait for clickability
        # Based on actual GoMotive HTML: id="user_email", name="user[email]", type="text"
        selectors = [
            (By.ID, "user_email"),
            (By.NAME, "user[email]"),
            (By.CSS_SELECTOR, "input[name='user[email]']"),
            (By.XPATH, "//input[@id='user_email']")
        ]
        
        for by, selector in selectors:
            try:
                print(f"  Trying: {by}={selector}")
                email_field = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((by, selector))
                )
                print(f"✓ Email field found and clickable using: {by}={selector}")
                break
            except TimeoutException:
                continue
            except Exception as e:
                print(f"  Error with {by}={selector}: {e}")
                continue
        
        if not email_field:
            print("❌ Could not find clickable email field with any selector")
            return False
        
        # Scroll to element to ensure it's in view
        driver.execute_script("arguments[0].scrollIntoView(true);", email_field)
        time.sleep(0.5)
        
        # Enter email using JavaScript as fallback if needed
        print(f"\n→ Entering email: {EMAIL}")
        try:
            email_field.clear()
            email_field.send_keys(EMAIL)
            print("✓ Email entered")
        except Exception as e:
            print(f"⚠ Direct input failed, trying JavaScript: {e}")
            driver.execute_script(f"arguments[0].value = '{EMAIL}';", email_field)
            print("✓ Email entered via JavaScript")
        
        # Find password field
        print("\n→ Looking for password field...")
        password_field = None
        
        # Based on actual GoMotive HTML: id="user_password", name="user[password]", type="password"
        password_selectors = [
            (By.ID, "user_password"),
            (By.NAME, "user[password]"),
            (By.CSS_SELECTOR, "input[name='user[password]']"),
            (By.XPATH, "//input[@id='user_password']")
        ]
        
        for by, selector in password_selectors:
            try:
                print(f"  Trying: {by}={selector}")
                password_field = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((by, selector))
                )
                print(f"✓ Password field found and clickable using: {by}={selector}")
                break
            except TimeoutException:
                continue
            except Exception as e:
                print(f"  Error with {by}={selector}: {e}")
                continue
        
        if not password_field:
            print("❌ Could not find password field")
            return False
        
        # Scroll to element
        driver.execute_script("arguments[0].scrollIntoView(true);", password_field)
        time.sleep(0.5)
        
        # Enter password
        print(f"\n→ Entering password: {'*' * len(PASSWORD)}")
        try:
            password_field.clear()
            password_field.send_keys(PASSWORD)
            print("✓ Password entered")
        except Exception as e:
            print(f"⚠ Direct input failed, trying JavaScript: {e}")
            driver.execute_script(f"arguments[0].value = '{PASSWORD}';", password_field)
            print("✓ Password entered via JavaScript")
        
        # Find and click login button
        print("\n→ Looking for login button...")
        login_button = None
        
        # Based on actual GoMotive HTML: id="sign-in-button", type="submit"
        button_selectors = [
            (By.ID, "sign-in-button"),
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.XPATH, "//button[@id='sign-in-button']"),
            (By.XPATH, "//button[contains(text(), 'Log in')]")
        ]
        
        for by, selector in button_selectors:
            try:
                print(f"  Trying: {by}={selector}")
                login_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((by, selector))
                )
                print(f"✓ Login button found and clickable using: {by}={selector}")
                break
            except TimeoutException:
                continue
            except Exception as e:
                print(f"  Error with {by}={selector}: {e}")
                continue
        
        if not login_button:
            print("❌ Could not find login button")
            return False
        
        # Scroll to button
        driver.execute_script("arguments[0].scrollIntoView(true);", login_button)
        time.sleep(0.5)
        
        print("\n→ Clicking login button...")
        try:
            login_button.click()
            print("✓ Login button clicked")
        except Exception as e:
            print(f"⚠ Direct click failed, trying JavaScript: {e}")
            driver.execute_script("arguments[0].click();", login_button)
            print("✓ Login button clicked via JavaScript")
        
        # Wait for navigation
        print("\n→ Waiting for login to complete...")
        time.sleep(5)
        
        current_url = driver.current_url
        print(f"✓ Current URL: {current_url}")
        
        # Check if login was successful
        if "log-in" in current_url.lower():
            print("\n❌ LOGIN FAILED - Still on login page")
            print("\nPossible reasons:")
            print("  1. Incorrect credentials")
            print("  2. Account locked")
            print("  3. Captcha required")
            print("  4. JavaScript not loaded properly")
            
            # Try to get error messages
            try:
                error_elements = driver.find_elements(By.CSS_SELECTOR, ".error, .alert, [role='alert']")
                if error_elements:
                    print("\nError messages found on page:")
                    for elem in error_elements:
                        text = elem.text.strip()
                        if text:
                            print(f"  • {text}")
            except:
                pass
            
            return False
        else:
            print("\n✅ LOGIN SUCCESSFUL!")
            print(f"✓ Redirected to: {current_url}")
            return True
            
    except Exception as e:
        print(f"\n❌ Error during login: {e}")
        import traceback
        traceback.print_exc()
        return False

def send_to_telegram(screenshot_path):
    """Send screenshot to Telegram (optional)"""
    try:
        # Read your bot token and chat ID from environment or hardcode for test
        import requests
        
        # You can get these from your .env file or set manually for testing
        BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
        CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
        
        if not BOT_TOKEN or not CHAT_ID:
            print("⚠ Telegram credentials not set, skipping telegram upload")
            return False
        
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        
        with open(screenshot_path, 'rb') as photo:
            files = {'photo': photo}
            data = {
                'chat_id': CHAT_ID,
                'caption': '🧪 GoMotive Login Test Screenshot'
            }
            response = requests.post(url, files=files, data=data)
        
        if response.status_code == 200:
            print("✅ Screenshot sent to Telegram!")
            return True
        else:
            print(f"❌ Failed to send to Telegram: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Telegram send error: {e}")
        return False

def test_screenshot(driver):
    """Test screenshot capability"""
    print("\n" + "=" * 60)
    print("STEP 3: Testing screenshot capability...")
    print("=" * 60)
    
    try:
        # Save to safetybot directory (same as script location)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        screenshot_path = os.path.join(script_dir, "gomotive_test_screenshot.png")
        print(f"\n→ Attempting to save screenshot to: {screenshot_path}")
        
        driver.save_screenshot(screenshot_path)
        
        if os.path.exists(screenshot_path):
            size = os.path.getsize(screenshot_path)
            print(f"✅ Screenshot saved successfully!")
            print(f"✓ File size: {size / 1024:.1f} KB")
            print(f"✓ Location: {screenshot_path}")
            
            # Keep the screenshot (don't delete for manual inspection)
            print("✓ Screenshot kept for inspection")
            
            # Try to send to Telegram if configured
            print("\n→ Attempting to send screenshot to Telegram...")
            send_to_telegram(screenshot_path)
            
            return True
        else:
            print("❌ Screenshot file was not created")
            return False
            
    except Exception as e:
        print(f"❌ Screenshot failed: {e}")
        return False

def main():
    """Main test function"""
    print("\n" + "=" * 60)
    print("GOMOTIVE LOGIN TEST")
    print("=" * 60)
    print(f"Testing login for: {EMAIL}")
    print("=" * 60)
    
    # Test with headless first
    print("\n[TEST 1] Headless mode (production mode)...")
    driver = setup_driver(headless=True)
    
    if not driver:
        print("\n" + "=" * 60)
        print("RESULT: Chrome driver setup failed")
        print("=" * 60)
        return
    
    try:
        # Test login
        login_success = test_login(driver)
        
        if login_success:
            # Test screenshot
            screenshot_success = test_screenshot(driver)
            
            print("\n" + "=" * 60)
            print("FINAL RESULTS")
            print("=" * 60)
            print(f"✅ Chrome Driver: SUCCESS")
            print(f"✅ Login: SUCCESS")
            print(f"{'✅' if screenshot_success else '❌'} Screenshot: {'SUCCESS' if screenshot_success else 'FAILED'}")
            print("=" * 60)
            
            if screenshot_success:
                print("\n🎉 All tests passed! Screenshot functionality should work.")
            else:
                print("\n⚠️  Login works but screenshots failed. Bot will send text-only alerts.")
        else:
            print("\n" + "=" * 60)
            print("FINAL RESULTS")
            print("=" * 60)
            print(f"✅ Chrome Driver: SUCCESS")
            print(f"❌ Login: FAILED")
            print("=" * 60)
            print("\n⚠️  Chrome works but login failed. Check credentials or GoMotive portal.")
            
    except Exception as e:
        print(f"\n❌ Unexpected error during testing: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            driver.quit()
            print("\n✓ Browser closed")
        except:
            pass
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)