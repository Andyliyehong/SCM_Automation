import os
import time
import re
from typing import Dict, Any, Optional
from playwright.sync_api import sync_playwright
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 初始化 MCP
mcp = FastMCP("SCM_Agent")

class SCMAutomator:
    def __init__(self):
        self.url = "http://172.190.107.21/WebApplicationSCM/Default.aspx"
        self.username = "Admin"
        self.password = os.getenv('SCM_PASSWORD')
        self.plant_id = "Xylem (Xylem)"

    def _login(self, page):
        """通用登录逻辑"""
        page.goto(self.url)
        page.locator('input#UserName').first.fill(self.username)
        page.locator('input[name="Password1"]').fill(self.password)
        
        # 处理 Plant ID
        plant_input = page.locator('input.custom-combobox-input').nth(0)
        plant_input.fill('Xylem')
        page.wait_for_selector('.ui-autocomplete .ui-menu-item')
        page.click(".ui-autocomplete .ui-menu-item:has-text('Xylem (Xylem)')")
        
        # 点击登录
        selectors = ['button:has-text("Signin")', 'input[value="Signin"]', 'text=Signin']
        for s in selectors:
            locator = page.locator(s).first
            if locator.count() > 0:
                locator.click()
                break
        page.wait_for_load_state('networkidle')

    def _click_menu(self, page, labels: list):
        """通用菜单导航逻辑"""
        for label in labels:
            page.locator(f'text={label}').first.click()
            time.sleep(1)

@mcp.tool()
def get_business_parameters() -> str:
    """获取当前的业务参数（Customer Priority, Due Date, Revenue）。"""
    scm = SCMAutomator()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            scm._login(page)
            scm._click_menu(page, ["Input", "XylemParameters"])
            
            # 提取逻辑
            results = []
            for field in ["Customer Priority", "Due Date", "Revenue"]:
                val = page.locator(f"xpath=//tr[td[contains(., '{field}')]]/td[2]").text_content()
                results.append(f"{field}: {val.strip() if val else 'N/A'}")
            
            return "\n".join(results)
        finally:
            browser.close()

@mcp.tool()
def update_parameters(customer_priority: int, due_date: int, revenue: int) -> str:
    """修改业务参数值。"""
    scm = SCMAutomator()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            scm._login(page)
            scm._click_menu(page, ["Input", "XylemParameters"])
            # 更新逻辑
            # 这里填入你在 3_update_business_parameters.py 中的输入框定位代码
            # page.fill(...) 
            # page.click("text=Submit")
            return "Parameters updated successfully."
        finally:
            browser.close()

@mcp.tool()
def create_scenario(scenario_name: str) -> str:
    """创建一个新的场景(Scenario)。"""
    scm = SCMAutomator()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            scm._login(page)
            scm._click_menu(page, ["Scenario", "Scenario Manager"])
            # 这里的逻辑参考 4_create_new_scenario.py
            return f"Scenario '{scenario_name}' created."
        finally:
            browser.close()

@mcp.tool()
def run_workflow() -> str:
    """运行 SCM Workflow 流程。"""
    scm = SCMAutomator()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            scm._login(page)
            scm._click_menu(page, ["Workflow", "Workflow Execution"])
            # 执行逻辑参考 5_run_workflow.py
            return "Workflow execution triggered."
        finally:
            browser.close()

@mcp.tool()
def get_comparison_report() -> str:
    """调取场景对比分析报告数据。"""
    scm = SCMAutomator()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            scm._login(page)
            scm._click_menu(page, ["Analysis", "Comparison Analytics"])
            # 提取报告逻辑参考 6_retrieve_scenario_comparison_analytics_reports.py
            return "Report data retrieved: [Analysis Summary Data...]"
        finally:
            browser.close()

if __name__ == "__main__":
    mcp.run()