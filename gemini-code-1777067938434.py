from datetime import datetime
import os
import sys
import asyncio
import time
import re
from tkinter import dialog
from typing import Dict, Any, Optional
from playwright.async_api import Page, async_playwright
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv
import logging
import pandas as pd

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

async def edit_and_update_values_and_save(page: Page, customer_priority: str, due_date: str, revenue: str):
    # Click Edit (icon button)
    await page.locator("#OPTParams_edit").wait_for(state="visible")
    await page.locator("#OPTParams_edit").click(force=True)

    # Fill values (prefer visible inputs; avoids hidden/template matches)
    await page.locator('input[id="Customer Priority"]:visible').first.wait_for(state="visible")
    await page.locator('input[id="Customer Priority"]:visible').first.fill(str(customer_priority))
    await page.locator('input[id="Due Date"]:visible').first.fill(str(due_date))
    await page.locator('input[id="Revenue"]:visible').first.fill(str(revenue))

    save_btn = page.locator("#OPTParams_save")
    await save_btn.wait_for(state="visible")
    await save_btn.click(force=True)

    await page.wait_for_load_state('networkidle')
    await asyncio.sleep(2)  # Additional wait for changes to save and reflect
    # Click OK on confirmation dialog (jQuery UI style)
    # ok_btn = page.locator('span.ui-button-text:has-text("Ok")').first.locator("xpath=ancestor::button[1]")
    # ok_btn.wait_for(state="visible")
    # ok_btn.click(force=True)

    dialog = page.locator('div.ui-dialog[role="dialog"]:visible')
    await dialog.wait_for(state="visible")

    ok_btn = dialog.locator('.ui-dialog-buttonpane .ui-dialog-buttonset button:has-text("Ok")')
    await ok_btn.wait_for(state="visible")
    await ok_btn.click(force=True)

def _today_mm_dd() -> str:
    return datetime.now().strftime("%m-%d")

async def get_max_scenario_id(page: Page) -> int:
    """
    From Scenario Master  read 'ScenarioId' and retrieve the max value
    """

    # 1) Wait for the grid data area to be visible 
    data_area = page.locator("#div_ScenarioMaster .pv-datagrid-data")
    await data_area.wait_for(state="visible")

    # 2) Get all rows in the grid
    rows = data_area.locator("table tbody tr")
    row_count = await rows.count()
    if row_count == 0:
        raise RuntimeError("Scenario Master grid has no data rows.")

    # 3) Get column headers and find the index of the 'ScenarioId' column
    header_ths = page.locator('#div_ScenarioMaster .pv-datagrid-colheaders th')
    header_count = await header_ths.count()
    if header_count == 0:
        raise RuntimeError("Column headers not found.")


    scenario_id_col_index = None
    for i in range(header_count):
        colname = (await header_ths.nth(i).get_attribute("data-colname") or "").strip()
        if colname.lower() == "scenarioid":
            scenario_id_col_index = i
            break

    if scenario_id_col_index is None:
        raise RuntimeError("Column header for 'ScenarioId' not found.")

    # 4) Iterate through rows to find the max ScenarioId value
    max_id = None
    for r in range(row_count):
        # Get the cell in the ScenarioId column for this row
        cell = rows.nth(r).locator("td").nth(scenario_id_col_index)
        txt = (await cell.inner_text() or "").strip()

        m = re.search(r"\d+", txt)
        if not m:
            continue
        val = int(m.group(0))
        max_id = val if (max_id is None) else max(max_id, val)

    if max_id is None:
        raise RuntimeError("No numeric values found in the 'ScenarioId' column.")

    return max_id




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
    logger.info(f"Current event loop: {id(asyncio.get_event_loop())}")
    logger.info("Retrieving business parameters")
    scm = SCMAutomator()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await scm._login(page)
            # await asyncio.sleep(2)  # Wait for page to load after login
            print("Navigating to Input tab and XylemParameters...")
            await asyncio.sleep(3)
            await click_menu_item(page, "Input")
            await asyncio.sleep(1)
            await click_menu_item(page, "XylemParameters")
            await page.wait_for_load_state('networkidle')
            await asyncio.sleep(2)  # Additional wait for page to load
            print("   ✓ Navigated to XylemParameters")
           
            customer_priority = await get_field_value(page, "CustomerPriority", "Customer Priority")
            due_date = await get_field_value(page, "DueDate", "Due Date")
            revenue = await get_field_value(page, "Revenue", "Revenue")
            # Extract logic
            results = {
                "Customer Priority": customer_priority,
                "Due Date": due_date,
                "Revenue": revenue
            }
            logger.info("Business parameters retrieved successfully")
            return "\n".join([f"{key}: {value}" for key, value in results.items()])
        finally:
            await browser.close()

@mcp.tool()
async def update_parameters(customer_priority: str, due_date: str, revenue: str) -> str:
    """Update the business parameters (Customer Priority, Due Date, Revenue)."""
    logger.info("Updating business parameters")
    scm = SCMAutomator()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await scm._login(page)
            # await asyncio.sleep(2)  # Wait for page to load after login
            print("Navigating to Input tab and XylemParameters...")
            await asyncio.sleep(3)
            await click_menu_item(page, "Input")
            await asyncio.sleep(1)
            await click_menu_item(page, "XylemParameters")
            await page.wait_for_load_state('networkidle')
            await asyncio.sleep(2)  # Additional wait for page to load
            print("   ✓ Navigated to XylemParameters")
           
            existing_customer_priority = await get_field_value(page, "CustomerPriority", "Customer Priority")
            existing_due_date = await get_field_value(page, "DueDate", "Due Date")
            existing_revenue = await get_field_value(page, "Revenue", "Revenue")
            # Extract logic
            results = {
                "Customer Priority": existing_customer_priority,
                "Due Date": existing_due_date,
                "Revenue": existing_revenue
            }
            logger.info("Business parameters retrieved successfully")
            print("\n".join([f"{key}: {value}" for key, value in results.items()]))

            await edit_and_update_values_and_save(page, customer_priority, due_date, revenue)
            logger.info("Business parameters updated successfully")
            await page.wait_for_load_state('networkidle')
            await asyncio.sleep(2)  # Additional wait for changes to save and reflect
            logger.info("Verifying updated parameters")
            customer_priority = await get_field_value(page, "CustomerPriority", "Customer Priority")
            due_date = await get_field_value(page, "DueDate", "Due Date")
            revenue = await get_field_value(page, "Revenue", "Revenue")
            results = {
                "Customer Priority": customer_priority,
                "Due Date": due_date,
                "Revenue": revenue
            }
            logger.info("Updated business parameters retrieved successfully")
            return "Updated Parameters:\n" + "\n".join([f"{key}: {value}" for key, value in results.items()])
        finally:
            await browser.close()

@mcp.tool()
async def create_scenario() -> str:
    """Create a new scenario (Scenario)."""
    scm = SCMAutomator()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await scm._login(page)
            # await asyncio.sleep(2)  # Wait for page to load after login
            print("Navigating to Input tab and XylemParameters...")
            await asyncio.sleep(3)
            await click_menu_item(page, "Input")
            await asyncio.sleep(1)
            await click_menu_item(page, "XylemParameters")
            await page.wait_for_load_state('networkidle')
            await asyncio.sleep(2)  # Additional wait for page to load
            print("   ✓ Navigated to XylemParameters")
           
            customer_priority = await get_field_value(page, "CustomerPriority", "Customer Priority")
            due_date = await get_field_value(page, "DueDate", "Due Date")
            revenue = await get_field_value(page, "Revenue", "Revenue")
            print("Current Business Parameters:")
            print(f"Customer Priority: {customer_priority}")
            print(f"Due Date: {due_date}")
            print(f"Revenue: {revenue}")
            logger.info("Business parameters retrieved successfully")

            print("Navigating to File tab and Scenario Master...")
            await asyncio.sleep(3)
            await click_menu_item(page, "File")
            await asyncio.sleep(1)
            await click_menu_item(page, "Scenario Master")
            await page.wait_for_load_state('networkidle')
            await asyncio.sleep(2)  # Additional wait for page to load
            print("   ✓ Navigated to Scenario Master")
            
            # Step 10: Create a new Scenario
            print("Creating a new Scenario...")

            max_id = await get_max_scenario_id(page)
            new_scenario_id = max_id + 1
            print("New Scenario Id =", new_scenario_id)
            logging.info(f"Retrieved max ScenarioId from grid: {max_id}")
            today_date = _today_mm_dd()
            new_scenario_name = f"{today_date}-Unconst-{customer_priority}-{due_date}-{revenue}"
            print(f"New Scenario Name: {new_scenario_name}")
            logging.info(f"Generated new scenario name: {new_scenario_name}")

            # Click "Add" Buttion to create new scenario
            # page.locator("#div_ScenarioMaster .pv-dgd-tb-addbutton").click()
            await page.locator("#div_ScenarioMaster .pv-dgd-titlediv .pv-dgd-toolbar .pv-dgd-tb-addbutton").click()
            # Fill in Add Window
            await page.locator('input[data-datafieldname="ScenarioId"]').fill(str(new_scenario_id))
            await page.locator('input[data-datafieldname="ScenarioName"]').fill(str(new_scenario_name))
    
            add_btn = page.locator('.ui-dialog-buttonpane .ui-dialog-buttonset button:has-text("Add")')
            await add_btn.wait_for(state="visible")
            await asyncio.sleep(2)  # Wait for any dynamic validation to complete
            await add_btn.click(force=True)
            await page.wait_for_load_state('networkidle')
            await asyncio.sleep(2)  # Additional wait for scenario to be created and grid to refresh
            # The logic here refers to 4_create_new_scenario.py
            return f"Scenario '{new_scenario_name}' created."
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
            # await asyncio.sleep(2)  # Wait for page to load after login

            print("Navigating to File tab and Work Flow...")
            await asyncio.sleep(3)
            await click_menu_item(page, "File")
            await asyncio.sleep(1)
            wf = await page.locator('#pvmenubar ul.pv-sub-menu:visible a.pagelink[data-menuname="WorkFlow"]:visible')
            await wf.wait_for(state="visible", timeout=10000)
            await wf.click()
            await page.wait_for_load_state('networkidle')
            await asyncio.sleep(2)  # Additional wait for page to load
            print("   ✓ Navigated to Workflow")
            # Execution logic refers to 5_run_workflow.py
             # Step 8: Select the workflows which need to run and click run button
            await page.eval_on_selector_all('div.pv-datagrid-data tr[pv-data-row="True"]', '(rows, targets)=>{const set=new Set(targets); rows.forEach(r=>{const t=(r.querySelector(\'td[data-colname="Description"] .pv-view-element\')?.textContent||"").trim(); if(set.has(t)){(r.querySelector(\'td[data-colname="CheckBox"] input[type="checkbox"]\')||r.querySelector(\'td[data-colname="CheckBox"]\'))?.click();}});}', ["Generate Master data","Preprocessing","Update Production Shifts","Finite Capacity Plan","UpdateEPST_Early Ship Date","Scheduling","Scheduling Output","Save Scenario"])
            await asyncio.sleep(2)  # Additional wait for page to load
            print("   ✓ Check the workflows which need to run")

            # # Click the Run button to run the workflows
            # await page.click("#btn_runworkflow")
            # await asyncio.sleep(2)  # Additional wait for page to load
            # print("   ✓ Clicked Run button to run the workflows")
            # return "Workflow execution triggered."
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
            # await asyncio.sleep(2)  # Wait for page to load after login

            print("Navigating to Xylem Reports tab and Scenario Comparison - Analytics...")
            await asyncio.sleep(3)
            await click_menu_item(page, "Xylem Reports")
            await asyncio.sleep(1)
            wf = page.locator('#pvmenubar ul.pv-sub-menu:visible a.pagelink[data-modulename="ScenarioComparison_Analytics"]:visible')
            await wf.wait_for(state="visible", timeout=10000)
            await wf.click()
            await page.wait_for_load_state('networkidle')
            await asyncio.sleep(2)  # Additional wait for page to load
            print("   ✓ Navigated to Scenario Comparison - Analytics")
            # Execution logic refers to 5_run_workflow.py
            # Retrieve ScenarioComparison_Analytics as table data and convert to structured format (e.g. list of dicts)
            col_list = []

            headers = page.locator(
                '#TopGrid[data-tablename="ScenarioComparison_Analytics"] '
                '.pv-datagrid-colheaders [data-colname]'
            )

            for i in range(headers.count()):
                col_list.append(headers.nth(i).get_attribute("data-colname"))
            col_list = list(dict.fromkeys(col_list))
            print("Extracted column names:")
            print(col_list)

            grid = page.locator('#TopGrid[data-tablename="ScenarioComparison_Analytics"]')

            payload = grid.evaluate(r"""
            (el) => {
            const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();

            // --- headers: prefer data-colname, fallback to data-column ---
            const ths =
                el.querySelectorAll('.pv-datagrid-colheaders th[data-colname]')?.length
                ? el.querySelectorAll('.pv-datagrid-colheaders th[data-colname]')
                : el.querySelectorAll('.pv-datagrid-colheaders th[data-column]');

            const headers = Array.from(ths).map(th => th.getAttribute('data-colname') || th.getAttribute('data-column') || norm(th.textContent));

            // --- rows: inside pv-datagrid-data, grab all row-like <tr> that contain <td> ---
            const dataRoot = el.querySelector('.pv-datagrid-data') || el;
            const rowTrs = Array.from(dataRoot.querySelectorAll('tr')).filter(tr => tr.querySelectorAll('td').length > 0);

            const rows = rowTrs.map(tr => Array.from(tr.querySelectorAll('td')).map(td => norm(td.textContent)));

            return { headers, rows };
            }
            """)

            # ---- headers: remove duplicates but keep order ----
            headers = list(dict.fromkeys(payload["headers"]))  # keep order
            rows = payload["rows"]

            # ---- normalize shape so pandas won't error ----
            max_len = max([len(headers)] + [len(r) for r in rows]) if (headers or rows) else 0
            headers2 = headers + [f"__extra_{i}" for i in range(len(headers), max_len)]
            rows2 = [r + [None] * (max_len - len(r)) for r in rows]

            df = pd.DataFrame(rows2, columns=headers2)

            print(df.head(10).to_string(index=False))
            logger.info("Scenario comparison report data retrieved successfully")
            logger.info(f"Report contains {len(df)} rows and {len(df.columns)} columns")

            # Extract report logic refers to 6_retrieve_scenario_comparison_analytics_reports.py
            return "Report data retrieved: [Analysis Summary Data...]"
        finally:
            await browser.close()

if __name__ == "__main__":
    logger.info("Starting SCM MCP Server")
    try:
        mcp.run()   
    except Exception as e:
        logger.error(f"Error occurred while running SCM MCP Server: {e}")
