"""
认证模块 - 处理 BNU CAS 统一身份认证登录
"""
import time
from playwright.sync_api import Page


CAS_USERNAME_SELECTORS = [
    "input[placeholder*='学工号']",
    "input[placeholder*='学号']",
    "input[placeholder*='邮箱']",
    "input#username",
    "input[name='username']",
    "#username",
]

CAS_PASSWORD_SELECTORS = [
    "#password-input",
    "input[placeholder*='密码']",
    "input#password",
    "input[name='password']",
    "#password",
]

CAS_LOGIN_BUTTON_SELECTORS = [
    ".login-btn",
    "button:has-text('登录')",
    "input[type='submit']",
    "button[type='submit']",
    "a:has-text('登录')",
]


class Authenticator:
    """处理北师大 CAS 统一身份认证"""

    def __init__(self, username: str = "", password: str = ""):
        self.username = username
        self.password = password

    def is_on_login_page(self, page: Page) -> bool:
        """检测当前是否在登录页面"""
        try:
            title = page.title()
            body_text = page.locator("body").inner_text()
            return ("统一身份认证" in title or
                    "统一身份认证" in body_text or
                    "CAS" in title)
        except Exception:
            return False

    def login(self, page: Page, auto_fill: bool = True) -> bool:
        """
        执行登录操作
        auto_fill=True: 自动填写账号密码并登录
        auto_fill=False: 等待用户手动登录
        返回是否成功登录
        """
        if not self.is_on_login_page(page):
            print("[Auth] Not on login page, skipping")
            return True

        if not auto_fill or not self.username:
            print("[Auth] Waiting for manual login... (no credentials provided)")
            return self._wait_for_login(page, timeout=600)

        print(f"[Auth] Attempting auto-login for user: {self.username}")

        # 1. 找到并填写用户名
        username_input = None
        for selector in CAS_USERNAME_SELECTORS:
            try:
                el = page.locator(selector).first
                if el.is_visible(timeout=2000):
                    username_input = el
                    break
            except Exception:
                continue

        if not username_input:
            print("[Auth] Could not find username input")
            return self._wait_for_login(page)

        username_input.click()
        username_input.fill(self.username)
        print("[Auth] Username filled")

        # 2. 找到并填写密码
        password_input = None
        for selector in CAS_PASSWORD_SELECTORS:
            try:
                el = page.locator(selector).first
                if el.is_visible(timeout=2000):
                    password_input = el
                    break
            except Exception:
                continue

        if not password_input:
            print("[Auth] Could not find password input")
            return self._wait_for_login(page)

        password_input.click()
        password_input.fill(self.password)
        print("[Auth] Password filled")

        # 3. 点击登录按钮
        login_button = None
        for selector in CAS_LOGIN_BUTTON_SELECTORS:
            try:
                el = page.locator(selector).first
                if el.is_visible(timeout=2000):
                    login_button = el
                    break
            except Exception:
                continue

        if not login_button:
            print("[Auth] Could not find login button")
            return self._wait_for_login(page)

        login_button.click()
        print("[Auth] Login button clicked, waiting for redirect...")

        # 等待登录完成
        return self._wait_for_login(page, timeout=30)

    def _wait_for_login(self, page: Page, timeout: int = 600) -> bool:
        """
        等待登录完成（页面跳转离开登录页）
        timeout: 秒
        """
        start = time.time()
        while time.time() - start < timeout:
            try:
                if not self.is_on_login_page(page):
                    print("[Auth] Login successful!")
                    time.sleep(3)  # 等待页面完全加载
                    return True
            except Exception:
                pass
            time.sleep(1)

        print(f"[Auth] Login wait timeout ({timeout}s)")
        return False

    def wait_for_manual_login(self, page: Page, timeout: int = 600) -> bool:
        """
        等待用户在浏览器中手动登录
        timeout: 秒
        """
        print(f"[Auth] Waiting for manual login (max {timeout}s)...")
        print("  Please login in the browser window...")
        return self._wait_for_login(page, timeout=timeout)
