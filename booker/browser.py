"""
浏览器管理模块 - 封装 Playwright 浏览器启动和上下文管理
"""
import os
import json
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTH_STATE_PATH = os.path.join(BASE_DIR, "auth_state.json")


class BrowserManager:
    """管理 Playwright 浏览器的生命周期"""

    def __init__(self, headless: bool = False):
        self.headless = headless
        self.playwright: sync_playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    def start(self) -> "BrowserManager":
        """启动浏览器并创建上下文"""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",  # 反检测
            ],
        )

        # 加载已保存的认证状态
        storage_state = None
        if os.path.exists(AUTH_STATE_PATH):
            try:
                with open(AUTH_STATE_PATH, "r", encoding="utf-8") as f:
                    storage_state = json.load(f)
                print(f"[Browser] Loaded auth state from {AUTH_STATE_PATH}")
            except Exception:
                pass

        self.context = self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
            storage_state=storage_state,
        )
        self.page = self.context.new_page()
        return self

    def save_auth_state(self):
        """保存当前浏览器认证状态"""
        if self.context:
            storage = self.context.storage_state()
            with open(AUTH_STATE_PATH, "w", encoding="utf-8") as f:
                json.dump(storage, f, ensure_ascii=False, indent=2)
            print(f"[Browser] Auth state saved to {AUTH_STATE_PATH}")

    def close(self):
        """关闭浏览器"""
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        print("[Browser] Closed")

    @staticmethod
    def get_target_url() -> str:
        return ("https://onevpn.bnu.edu.cn/https/77726476706e69737468656265737421"
                "e4ee429b69326645300d8db9d6562d/www/dd/vue/spa/zhcg#/")

    def navigate_and_wait_for_button(self, timeout: int = 15000):
        """
        快速导航到预约页面：不等待所有资源加载完毕，
        只要"立即预约"按钮出现就继续。
        """
        print("[Browser] Fast navigating - waiting for button, not networkidle")
        # 使用 domcontentloaded 而不是 networkidle (快很多)
        self.page.goto(BrowserManager.get_target_url(),
                        wait_until="domcontentloaded", timeout=timeout)
        # 等待关键按钮出现 (最多等5秒)
        btn = self.page.locator(".el-button--danger")
        btn.wait_for(state="visible", timeout=5000)
        print("[Browser] Venue button is visible - ready to click")
