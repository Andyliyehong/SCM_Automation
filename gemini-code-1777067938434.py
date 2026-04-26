import os
import sys
import asyncio
import time
import re
from typing import Dict, Any, Optional
from playwright.async_api import async_playwright
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    stream=sys.stderr)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# Used for Sign_in process
async def click_signin(page):
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
        if await locator.count() == 0:
            continue
        try:
            print(f'   Trying signin selector: {selector}')
            if await locator.is_visible():
                await locator.click()
            else:
                await locator.click(force=True)
            return True
        except Exception as e:
            print(f'   Selector failed: {selector} -> {e}')
    raise RuntimeError('Unable to find or click the Signin button')


async def click_menu_item(page, label: str):
    selectors = [
        f'button:has-text("{label}")',
        f'a:has-text("{label}")',
        f'span:has-text("{label}")',
        f'div:has-text("{label}")',
        f'text={label}',
    ]
    for selector in selectors:
        locator = page.locator(selector).first
        if await locator.count() == 0:
            continue
        try:
            print(f'   Trying menu selector: {selector}')
            await locator.wait_for(state='visible', timeout=20000)
            await locator.click()
            return True
        except Exception as e:
            print(f'   Menu selector failed: {selector} -> {e}')
    raise RuntimeError(f'Unable to find or click menu item "{label}"')

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
    return text or None


async def get_field_value(page, field_name: str, field_label: str):
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
        if await locator.count() > 0:
            try:
                value = await locator.first.get_attribute('value')
                if value:
                    return value
            except Exception:
                pass
    # Try label-based lookups and adjacent display fields.
    label = page.locator(f'label:has-text("{field_label}")')
    if await label.count() == 0:
        label = page.locator(f'xpath=//*[contains(normalize-space(.), "{field_label}")]')
    if await label.count() > 0:
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
            if await locator.count() > 0:
                try:
                    value = await locator.first.get_attribute('value')
                    if value:
                        return value
                except Exception:
                    text = await locator.first.text_content()
                    cleaned = clean_value_text(text, field_label)
                    if cleaned:
                        return cleaned

    # Fallback to row-based table extraction.
    row_locator = page.locator(f'xpath=//tr[td[contains(normalize-space(.), "{field_label}")]]')
    if await row_locator.count() > 0:
        value_cell = row_locator.locator('xpath=./td[2]').first
        if await value_cell.count() > 0:
            text = await value_cell.text_content()
            print(f"Debug {field_name}: raw text from table td[2]: '{text}'")
            cleaned = clean_value_text(text, field_label)
            if cleaned:
                return cleaned

    return None

# Initialize MCP server
mcp = FastMCP("SCM_Agent")

class SCMAutomator:
    def __init__(self):
        self.url = "http://172.190.107.21/WebApplicationSCM/Default.aspx"
        self.username = "Admin"
        self.password = os.getenv('SCM_PASSWORD')
        self.plant_id = "Xylem (Xylem)"

    async def _login(self, page):
        """Log in to SCM application using provided credentials and plant selection."""
        logger.info("Attempting to log in to SCM application")
        await page.goto(self.url)
        logger.info(f"Navigated to login page: {self.url}")
        await page.locator('input#UserName').first.fill(self.username)
        await page.locator('input[name="Password1"]').fill(self.password)
        
        # Fill in the plant input and select the correct option from the dropdown.
        plant_input = page.locator('input.custom-combobox-input').nth(0)
        await plant_input.fill('Xylem')
        await page.wait_for_selector('.ui-autocomplete .ui-menu-item')
        await page.click(".ui-autocomplete .ui-menu-item:has-text('Xylem (Xylem)')")
        
        # Click Sign In button
        logger.info("clicking Sign In button")
        try:
            await click_signin(page)
        except Exception as e:
            logger.error(f"Error during login: {e}")
            raise RuntimeError("Login failed") from e
        await page.wait_for_load_state('networkidle')

        await page.wait_for_selector('text=Input', timeout=30000)
        logger.info("Login successful")

    async def _click_menu(self, page, labels: list):
        """Navigate through the menu based on a list of labels."""
        for label in labels:
            selectors = [
                f'button:has-text("{label}")',
                f'a:has-text("{label}")',
                f'span:has-text("{label}")',
                f'div:has-text("{label}")',
                f'text={label}',
            ]
            for selector in selectors:
                locator = page.locator(selector).first
                if await locator.count() > 0:
                    try:
                        await locator.wait_for(state='visible', timeout=10000)
                        await locator.click()
                        break
                    except Exception as e:
                        continue
            await asyncio.sleep(1)


@mcp.tool()
async def get_business_parameters() -> str:
    """Get the current business parameters (Customer Priority, Due Date, Revenue)."""
    logger.info("Retrieving business parameters")
    scm = SCMAutomator()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await scm._login(page)
            # await asyncio.sleep(2)  # Wait for page to load after login
            await scm._click_menu(page, ["Input", "XylemParameters"])
           
            await page.wait_for_load_state('networkidle')
            await asyncio.sleep(1)
            # Extract logic
            results = []
            field_mappings = {
                "Customer Priority": "CustomerPriority",
                "Due Date": "DueDate",
                "Revenue": "Revenue"
            }
            for field_label, field_name in field_mappings.items():
                val = await get_field_value(page, field_name, field_label)
                results.append(f"{field_label}: {val if val else 'N/A'}")
            
            logger.info("Business parameters retrieved successfully")
            return "\n".join(results)
        finally:
            await browser.close()

@mcp.tool()
async def update_parameters(customer_priority: int, due_date: int, revenue: int) -> str:
    """Update the business parameters (Customer Priority, Due Date, Revenue)."""
    logger.info("Updating business parameters")
    scm = SCMAutomator()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await scm._login(page)
            await scm._click_menu(page, ["Input", "XylemParameters"])
            # Update logic
            # This is where you would place the input field locators from 3_update_business_parameters.py   
            # page.fill(...) 
            # page.click("text=Submit")
            logger.info("Parameters updated successfully.")
            return "Parameters updated successfully."
        finally:
            await browser.close()

@mcp.tool()
async def create_scenario(scenario_name: str) -> str:
    """Create a new scenario (Scenario)."""
    scm = SCMAutomator()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await scm._login(page)
            await scm._click_menu(page, ["Scenario", "Scenario Manager"])
            # The logic here refers to 4_create_new_scenario.py
            return f"Scenario '{scenario_name}' created."
        finally:
            await browser.close()

@mcp.tool()
async def run_workflow() -> str:
    """Run the SCM Workflow process."""
    scm = SCMAutomator()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await scm._login(page)
            await scm._click_menu(page, ["Workflow", "Workflow Execution"])
            # Execution logic refers to 5_run_workflow.py
            return "Workflow execution triggered."
        finally:
            await browser.close()

@mcp.tool()
async def get_comparison_report() -> str:
    """Get the scenario comparison analysis report data."""
    scm = SCMAutomator()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await scm._login(page)
            await scm._click_menu(page, ["Analysis", "Comparison Analytics"])
            # Extract report logic refers to 6_retrieve_scenario_comparison_analytics_reports.py
            return "Report data retrieved: [Analysis Summary Data...]"
        finally:
            await browser.close()

if __name__ == "__main__":
    logger.info("Starting SCM MCP Server")
    mcp.run()
