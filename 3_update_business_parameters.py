from playwright.sync_api import sync_playwright
import time
import logging
import os
from dotenv import load_dotenv
import re
# Load environment variables from .env file
load_dotenv()

# Used for Sign_in process
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

# Find Input, XylemParameters
def click_menu_item(page, label: str):
    selectors = [
        f'button:has-text("{label}")',
        f'a:has-text("{label}")',
        f'span:has-text("{label}")',
        f'div:has-text("{label}")',
        f'text={label}',
    ]
    for selector in selectors:
        locator = page.locator(selector).first
        if locator.count() == 0:
            continue
        try:
            print(f'   Trying menu selector: {selector}')
            locator.wait_for(state='visible', timeout=20000)
            locator.click()
            return True
        except Exception as e:
            print(f'   Menu selector failed: {selector} -> {e}')
    raise RuntimeError(f'Unable to find or click menu item "{label}"')

# Get Business Rule Parameter values
def clean_value_text(raw_text: str, field_label: str) -> str | None:
    if not raw_text:
        return None
    text = re.sub(r'\s+', ' ', raw_text).strip()
    # Remove repeated label text and common UI noise.
    text = re.sub(re.escape(field_label), '', text, flags=re.IGNORECASE).strip()
    text = re.sub(r'Low \(0%\)|High \(100%\)|Select|Choose|Submit|Cancel', '', text, flags=re.IGNORECASE).strip()
    text = re.sub(r'\b(?:\d+\s*%\b)', '', text).strip()
    text = re.sub(r'\s{2,}', ' ', text)
    # Extract the first number if present, otherwise return cleaned text.
    match = re.search(r'\b(\d+)\b', text)
    if match:
        return match.group(1)
    if not text:
        return None
    return text

def get_field_value(page, field_name: str, field_label: str):
    # Try direct form controls by name or id.
    candidates = [
        f'input[name="{field_name}"]',
        f'select[name="{field_name}"]',
        f'textarea[name="{field_name}"]',
        f'input[id="{field_name}"]',
        f'select[id="{field_name}"]',
        f'textarea[id="{field_name}"]',
        f'input[id="{field_label}"]',
        f'select[id="{field_label}"]',
        f'textarea[id="{field_label}"]',
        f'#{field_name}',
    ]
    for selector in candidates:
        locator = page.locator(selector)
        if locator.count() > 0:
            try:
                value = locator.first.get_attribute('value')
                if value:
                    return value
            except Exception:
                pass
    # Try label-based lookups and adjacent display fields.
    label = page.locator(f'label:has-text("{field_label}")')
    if label.count() == 0:
        label = page.locator(f'xpath=//*[contains(normalize-space(.), "{field_label}")]')
    if label.count() > 0:
        nearby = [
            'xpath=following-sibling::input[1]',
            'xpath=following-sibling::select[1]',
            'xpath=following-sibling::textarea[1]',
            'xpath=following-sibling::span[1]',
            'xpath=following-sibling::td[1]',
            'xpath=following-sibling::div[1]',
        ]
        for expr in nearby:
            locator = label.locator(expr)
            if locator.count() > 0:
                try:
                    value = locator.first.get_attribute('value')
                    if value:
                        return value
                except Exception:
                    text = locator.first.text_content()
                    cleaned = clean_value_text(text, field_label)
                    if cleaned:
                        return cleaned

    # Fallback to row-based table extraction.
    row_locator = page.locator(f'xpath=//tr[td[contains(normalize-space(.), "{field_label}")]]')
    if row_locator.count() > 0:
        value_cell = row_locator.locator('xpath=./td[2]').first
        if value_cell.count() > 0:
            text = value_cell.text_content()
            print(f"Debug {field_name}: raw text from table td[2]: '{text}'")
            cleaned = clean_value_text(text, field_label)
            if cleaned:
                return cleaned

    return None


# Update Business Rule Parameter values

def edit_and_update_values_and_save(page: Page, customer_priority: str, due_date: str, revenue: str):
    # Click Edit (icon button)
    edit_btn = page.locator("#OPTParams_edit")
    edit_btn.wait_for(state="visible")
    edit_btn.click(force=True)

    # Fill values (prefer visible inputs; avoids hidden/template matches)
    page.locator('input[id="Customer Priority"]:visible').first.wait_for(state="visible")
    page.locator('input[id="Customer Priority"]:visible').first.fill(str(customer_priority))
    page.locator('input[id="Due Date"]:visible').first.fill(str(due_date))
    page.locator('input[id="Revenue"]:visible').first.fill(str(revenue))

    save_btn = page.locator("#OPTParams_save")
    save_btn.wait_for(state="visible")
    save_btn.click(force=True)

    page.wait_for_load_state('networkidle')
    time.sleep(2)  # Additional wait for changes to save and reflect
    # Click OK on confirmation dialog (jQuery UI style)
    # ok_btn = page.locator('span.ui-button-text:has-text("Ok")').first.locator("xpath=ancestor::button[1]")
    # ok_btn.wait_for(state="visible")
    # ok_btn.click(force=True)

    dialog = page.locator('div.ui-dialog[role="dialog"]:visible')
    dialog.wait_for(state="visible")

    ok_btn = dialog.locator('.ui-dialog-buttonpane .ui-dialog-buttonset button:has-text("Ok")')
    ok_btn.wait_for(state="visible")
    ok_btn.click(force=True)


def main():

    # Set up logging
    logging.basicConfig(filename='Xylem_SCM.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    url = "http://172.190.107.21/WebApplicationSCM/Default.aspx"
    username = "Admin"
    password = os.getenv('SCM_PASSWORD')
    plant_id = "Xylem (Xylem)"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        # Create a new page and set default timeout
        context = browser.new_context()

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
            page.wait_for_load_state('networkidle')
            print("   ✓ Logged in successfully")

            # Step 7: Navigate to Parameters Section
            print("7. Navigating to Input tab and XylemParameters...")
            time.sleep(3)
            click_menu_item(page, "Input")
            time.sleep(1)
            click_menu_item(page, "XylemParameters")
            page.wait_for_load_state('networkidle')
            time.sleep(2)  # Additional wait for page to load
            print("   ✓ Navigated to XylemParameters")
            
            # Step 8: Retrieve Current Parameter Values
            print("8. Retrieving current parameter values...")
            customer_priority = get_field_value(page, "CustomerPriority", "Customer Priority")
            due_date = get_field_value(page, "DueDate", "Due Date")
            revenue = get_field_value(page, "Revenue", "Revenue")

            if customer_priority is not None and due_date is not None and revenue is not None:
                print(f"   Current Customer Priority: {customer_priority}")
                print(f"   Current Due Date: {due_date}")
                print(f"   Current Revenue: {revenue}")
                logging.info(f"Retrieved current values - Customer Priority: {customer_priority}, Due Date: {due_date}, Revenue: {revenue}")
            else:
                print("   Unable to retrieve one or more current parameter values.")
                logging.info(f"Unable to retrieve current parameter values: CustomerPriority={customer_priority}, DueDate={due_date}, Revenue={revenue}")
                customer_priority = customer_priority or "Unknown"
                due_date = due_date or "Unknown"
                revenue = revenue or "Unknown"
###  New Tasks
            # Step 9: Edit Parameter Values
            print("9. Editing parameter values...")
            edit_and_update_values_and_save(page, customer_priority="33", due_date="33", revenue="34")
            print("   ✓ Values updated")
            
            page.wait_for_load_state('networkidle')
            time.sleep(2)  # Additional wait for changes to save and reflect

            # Retrieve updated values
            print("10. Retrieving updated parameter values...")
            customer_priority = get_field_value(page, "CustomerPriority", "Customer Priority")
            due_date = get_field_value(page, "DueDate", "Due Date")
            revenue = get_field_value(page, "Revenue", "Revenue")

            if customer_priority is not None and due_date is not None and revenue is not None:
                print(f"   Updated Customer Priority: {customer_priority}")
                print(f"   Updated Due Date: {due_date}")
                print(f"   Updated Revenue: {revenue}")
                logging.info(f"Retrieved updated values - Customer Priority: {customer_priority}, Due Date: {due_date}, Revenue: {revenue}")
            else:
                print("   Unable to retrieve one or more updated parameter values.")
                logging.info(f"Unable to retrieve updated parameter values: CustomerPriority={customer_priority}, DueDate={due_date}, Revenue={revenue}")
                customer_priority = customer_priority or "Unknown"
                due_date = due_date or "Unknown"
                revenue = revenue or "Unknown"



        except Exception as e:
            print(f"Script error: {e}")
            import traceback
            traceback.print_exc()

        finally:
            # Pause and wait for user review before closing
            input("\nPress ENTER to continue to Close the Browser...")
            logging.info("User pressed ENTER; continuing to close browser")
            browser.close()
            print("\nBrowser closed.")

if __name__ == "__main__":
    main()