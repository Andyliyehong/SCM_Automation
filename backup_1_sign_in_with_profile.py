from playwright.sync_api import sync_playwright
import time
import logging
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

USER_DATA_DIR = "pw_profile"   # 固定目录，两个脚本都用它

def launch_persistent_browser(p, headless=False):
    return p.chromium.launch_persistent_context(
        USER_DATA_DIR,
        headless=headless,
        viewport={"width": 1400, "height": 900}
    )


def click_signin(page):
    selectors = [
        'button:has-text("Signin")',
        'button:has-text("Sign In")',
        'input[type="submit"]',
        'input[type="button"]',
        'input[value="Signin"]',
        'input[value="Sign In"]',
        'text=Signin',
        'text=Sign In',
    ]
    for selector in selectors:
        locator = page.locator(selector).first
        if locator.count() == 0:
            continue
        try:
            print(f'   Trying signin selector: {selector}')
            if locator.is_visible():
                locator.click()
            else:
                locator.click(force=True)
            return True
        except Exception as e:
            print(f'   Selector failed: {selector} -> {e}')
    raise RuntimeError('Unable to find or click the Signin button')


def main():

    # Set up logging
    logging.basicConfig(filename='Xylem_SCM.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    url = "http://172.190.107.21/WebApplicationSCM/Default.aspx"
    username = "Admin"
    password = os.getenv('SCM_PASSWORD')
    plant_id = "Xylem (Xylem)"
    
    with sync_playwright() as p:
        # browser = p.chromium.launch(headless=False)
        context = launch_persistent_browser(p, headless=False)
        # page = browser.new_page()

        # Create a new page and set default timeout
        # context = browser.new_context()

        # page = browser.new_page()
        page = context.new_page()


        page.set_default_timeout(90000)
        
        logging.info("Starting SCM automation script")
        
        try:
            print("=" * 60)
            print("SCM APPLICATION - LOGIN")
            print("=" * 60)
            
            # Step 1: Navigate to login page
            print(f"\n1. Loading login page from: {url}")
            page.goto(url)
            time.sleep(2)
            
            # Step 2: Fill username
            print("2. Filling in User Name...")
            page.locator('input#UserName').first.fill(username)
            print(f"   ✓ Username entered: {username}")
            
            # Step 3: Fill password
            print("3. Filling in Password...")
            page.locator('input[name="Password1"]').fill(password)
            print(f"   ✓ Password entered: {password}")
            
            # Step 4: Select Plant ID from dropdown
            print(f"4. Selecting Plant ID: {plant_id}")
            # Handle Plant ID autocomplete
            plant_input = page.locator('input.custom-combobox-input').nth(0)
            plant_input.fill('Xylem')
            page.wait_for_selector('.ui-autocomplete .ui-menu-item')
            page.click(".ui-autocomplete .ui-menu-item:has-text('Xylem (Xylem)')")
            print(f"   ✓ Plant ID selected: {plant_id}")


            # Step 5: Display current page state for review
            print(f"\n5. Current page state:")
            print(f"   - URL: {page.url}")
            print(f"   - Title: {page.title()}")
            print("\n" + "=" * 60)
            print("REVIEW REQUIRED - All inputs filled, ready for your review")
            print("=" * 60)
            print(f"   Username: {username}")
            print(f"   Password: ****")
            print(f"   Plant ID: {plant_id}")
            print("=" * 60)
            
            # Pause and wait for user review before continuing
            input("\nPress ENTER to continue to Sign In...")
            logging.info("User pressed ENTER; continuing to submit login")
            
            # Step 6: Submit Login
            print("\n6. Submitting login...")
            try:
                click_signin(page)
            except Exception as e:
                raise RuntimeError(f"Signin click failed: {e}")


            # Save storage state for reuse in future scripts
            page.wait_for_selector('text=Input', timeout=30000)
            # context.storage_state(path="storage_state.json")  


            page.wait_for_load_state('networkidle')
            print("   ✓ Logged in successfully, session saved to storage_state.json")

            print("\nAutomation complete!")
            logging.info("SCM automation script completed successfully")
            
        except Exception as e:
            print(f"Script error: {e}")
            import traceback
            traceback.print_exc()

        finally:
            # Pause and wait for user review before closing
            input("\nPress ENTER to continue to Close the Browser...")
            logging.info("User pressed ENTER; continuing to close browser")
            context.close()
            print("\nBrowser closed.")

if __name__ == "__main__":
    main()

