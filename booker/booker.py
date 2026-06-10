"""
预约核心模块 - 基于流程模板的自动化回放
读取 flow_template.json，按步骤执行，支持变量替换
"""
import os
import json
import time
from datetime import datetime
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLOW_TEMPLATE_PATH = os.path.join(BASE_DIR, "flow_template.json")

# 回退：如果 flow_template.json 不存在，使用的默认流程
DEFAULT_FLOW = {
    "name": "默认通用预约流程",
    "steps": [
        {
            "action": "click",
            "description": "选择校区",
            "selector": "input[placeholder*='校区']",
            "wait_after": 1500,
            "screenshot": True,
        },
        {
            "action": "click",
            "description": "选择校区的第一个选项",
            "selector": ".el-select-dropdown__item:visible",
            "wait_after": 1500,
            "screenshot": True,
        },
        {
            "action": "click",
            "description": "点击包含羽毛球的卡片",
            "selector": "text=羽毛球",
            "wait_after": 2000,
            "screenshot": True,
        },
        {
            "action": "click",
            "description": "点击场馆预约按钮",
            "selector": "button:has-text('预约')",
            "wait_after": 4000,
            "screenshot": True,
        },
        {
            "action": "fill",
            "description": "填写日期",
            "selector": "input[placeholder*='日期']",
            "value": "{{target_date}}",
            "wait_after": 1500,
            "screenshot": True,
        },
        {
            "action": "click",
            "description": "选择时间段",
            "selector": "text={{time_slot_start}}",
            "value": "{{time_slot_start}}",
            "wait_after": 1500,
            "screenshot": True,
        },
        {
            "action": "click",
            "description": "提交预约",
            "selector": "button:has-text('提交')",
            "wait_after": 5000,
            "screenshot": True,
        },
    ],
}


class FlowBooker:
    """基于流程模板的自动预约器 (支持 iframe 和新标签页)"""

    def __init__(self, page: Page, config: dict):
        self.page = page
        self.context = page.context  # browser context for new page detection
        self.config = config
        self.current_frame = None    # 当前操作的 iframe
        self.result = {"success": False, "message": "", "screenshot": "",
                       "steps_completed": 0, "steps_failed": 0}

        # 变量表 - 用于模板中的 {{var}} 替换
        time_slot = config.get("time_slot", "10:00-11:00")
        time_parts = time_slot.split("-") if "-" in time_slot else [time_slot, ""]
        target_date = config.get("target_date", "")
        target_day = target_date.split("-")[-1] if "-" in target_date else target_date
        target_day = target_day.lstrip("0") or "0"

        # 计算格子行列：grid_row = 开始小时 - 7 (用户代码: itime1 = itime - 7)
        target_time = config.get("target_time", "10:00")
        try:
            start_hour = int(target_time.split(":")[0])
        except (ValueError, IndexError):
            start_hour = 10
        grid_row = start_hour - 7  # e.g., 10:00 -> row 3
        grid_row_2 = grid_row + 1  # next hour for 2-hour booking

        # 场地编号：按场地名称在列表中的位置映射到预约表格列号
        # 列号 = 在 CAMPUS_VENUES 列表中的索引 + 1
        venue_name = config.get("venue_name", "羽1")
        import re
        CAMPUS_VENUES_MAP = {
            "海淀校区": ["羽1","羽2","羽3","羽4","羽5","羽6","羽7","羽8",
                         "二层东","二层西","小综合1","小综合2","小综合3","小综合4"],
            "昌平校区": ["羽1","羽2","羽3","羽4","羽5","羽6","羽7","羽8"],
            "海淀": ["羽1","羽2","羽3","羽4","羽5","羽6","羽7","羽8",
                     "二层东","二层西","小综合1","小综合2","小综合3","小综合4"],
            "昌平": ["羽1","羽2","羽3","羽4","羽5","羽6","羽7","羽8"],
        }
        venue_list = CAMPUS_VENUES_MAP.get(str(config.get("campus", "")), [])
        try:
            field_id = venue_list.index(str(venue_name)) + 1
        except ValueError:
            field_match = re.search(r'(\d+)', str(venue_name))
            field_id = int(field_match.group(1)) if field_match else 1

        self.vars = {
            "target_date": target_date,
            "target_day": target_day,
            "target_time": target_time,
            "time_slot": time_slot,
            "time_slot_start": time_parts[0] if len(time_parts) > 0 else "",
            "time_slot_end": time_parts[1] if len(time_parts) > 1 else "",
            "venue_name": str(venue_name),
            "venue_name_2": config.get("venue_name_2", ""),
            "campus": config.get("campus", "昌平"),
            "duration": config.get("duration", "1小时"),
            "grid_row": str(grid_row),
            "grid_row_2": str(grid_row_2),
            "grid_col": str(field_id),
            "field_id": str(field_id),
        }

        # 加载流程模板
        self.flow = self._load_flow()

    def _load_flow(self) -> dict:
        if os.path.exists(FLOW_TEMPLATE_PATH):
            try:
                with open(FLOW_TEMPLATE_PATH, "r", encoding="utf-8") as f:
                    flow = json.load(f)
                print(f"[FlowBooker] Loaded flow template: {flow.get('name', 'unknown')}")
                print(f"  {len(flow.get('steps', []))} steps")
                return flow
            except Exception as e:
                print(f"[FlowBooker] Failed to load flow template: {e}")
        print("[FlowBooker] Using default flow (will need manual tuning)")
        return dict(DEFAULT_FLOW)

    def _resolve(self, text: str) -> str:
        """解析模板变量 {{var}}"""
        result = text
        for key, val in self.vars.items():
            result = result.replace("{{" + key + "}}", str(val or ""))
        return result

    def _take_screenshot(self, label: str):
        sd = os.path.join(BASE_DIR, "screenshots")
        os.makedirs(sd, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(sd, f"{ts}_{label}.png")
        try:
            self.page.screenshot(path=filepath, full_page=True)
            if not self.result["screenshot"]:
                self.result["screenshot"] = filepath
            print(f"  [Shot] {filepath}")
        except Exception:
            pass

    def _find_element(self, selector: str, timeout: int = 3000):
        """查找元素(自动使用当前 iframe/page)"""
        target = self._get_active_locator()
        try:
            elem = target.locator(selector).first
            if elem.is_visible(timeout=timeout):
                return elem
        except Exception:
            pass
        return None

    def _execute_step(self, step: dict, step_idx: int) -> bool:
        """执行单个步骤"""
        action = step.get("action", "click")
        desc = step.get("description", f"Step {step_idx}")
        selector = step.get("selector", "")
        value = step.get("value", "")
        wait_after = step.get("wait_after", 2000)
        do_screenshot = step.get("screenshot", True)
        fallbacks = step.get("fallback_selectors", [])
        optional = step.get("optional", False)

        # 解析变量
        selector = self._resolve(selector)
        value = self._resolve(value)

        # 可选步骤
        if optional and not value and not selector:
            print(f"  [{step_idx}] SKIP (optional, no value): {desc}")
            return True

        print(f"  [{step_idx}] {action}: {desc}")

        # ── switch_frame 特殊处理 ──
        if action == "switch_frame":
            frame_idx = int(value) if value and value.isdigit() else 2
            ok = self._switch_to_frame(frame_idx)
            if ok:
                self._get_active_page().wait_for_timeout(wait_after)
                if do_screenshot:
                    self._take_screenshot(f"step{step_idx}_frame{frame_idx}")
                self.result["steps_completed"] += 1
                print(f"       OK")
            else:
                self.result["steps_failed"] += 1
                print(f"       FAILED")
            return ok

        # ── 纯 wait 步骤 ──
        if action == "wait" and not selector:
            wait_ms = int(value) if value and value.isdigit() else wait_after
            print(f"       waiting {wait_ms}ms")
            self._get_active_page().wait_for_timeout(wait_ms)
            if do_screenshot:
                self._take_screenshot(f"step{step_idx}_wait")
            self.result["steps_completed"] += 1
            return True

        # ── js_click 不需要查找元素，直接执行 JS ──
        if action == "js_click":
            target = self._get_active_locator()
            js = value if value else "document.querySelector('body').click()"
            try:
                result = target.evaluate(js)
                print(f"       JS result: {result}")
                self._get_active_page().wait_for_timeout(wait_after)
                if do_screenshot:
                    self._take_screenshot(f"step{step_idx}_jsclick")
                self.result["steps_completed"] += 1
                return True
            except Exception as e:
                print(f"       JS ERROR: {e}")
                self.result["steps_failed"] += 1
                return False

        # ── wait_manual_captcha: 等待用户手动完成验证码 ──
        if action == "wait_manual_captcha":
            timeout_sec = int(value) if value and value.isdigit() else 120
            print(f"       ========================================")
            print(f"       [!] 请在浏览器中手动拖动滑块完成验证码!")
            print(f"       等待最长 {timeout_sec} 秒...")
            print(f"       ========================================")
            page = self._get_active_page()
            for i in range(timeout_sec):
                try:
                    # 检查验证码弹窗是否已关闭
                    target = self._get_active_locator()
                    still_visible = target.locator(
                        '.el-dialog:visible:has(.slider)'
                    ).is_visible(timeout=500)
                    if not still_visible:
                        print(f"       [OK] 验证码已通过 (用户手动完成)")
                        self.result["steps_completed"] += 1
                        return True
                except Exception:
                    # 弹窗可能已关闭
                    print(f"       [OK] 验证码弹窗已消失")
                    self.result["steps_completed"] += 1
                    return True
                time.sleep(1)
            print(f"       [FAIL] 等待超时 ({timeout_sec}s)")
            self.result["steps_failed"] += 1
            return False

        # ── slide_captcha: 自动求解旋转滑块验证码 (2.0 实验版) ──
        if action == "slide_captcha":
            from booker.captcha_solver import RotationCaptchaSolver
            print(f"       启动验证码求解器...")
            # 验证码弹窗在 iframe 里 (实测确认)
            target = self._get_active_locator()  # 保持 iframe 上下文
            page = self._get_active_page()
            print(f"       [debug] target type: {type(target).__name__}")
            solver = RotationCaptchaSolver(page)
            ok = solver.solve(target)
            page.wait_for_timeout(wait_after)
            if ok:
                self.result["steps_completed"] += 1
                print(f"       CAPTCHA SOLVED")
            else:
                self.result["steps_failed"] += 1
                print(f"       CAPTCHA FAILED (manual intervention needed)")
            return ok

        # ── 需要选择器的步骤 ──
        selectors_to_try = [selector]
        if fallbacks:
            selectors_to_try += [self._resolve(fb) for fb in fallbacks if fb]
        selectors_to_try = list(dict.fromkeys([s for s in selectors_to_try if s]))

        if selectors_to_try:
            print(f"       selectors: {selectors_to_try[:3]}")

        elem = None
        for sel in selectors_to_try[:5]:
            elem = self._find_element(sel, timeout=2000)
            if elem:
                break

        if not elem:
            if optional:
                print(f"       SKIP (optional, element not found)")
                return True
            print(f"       FAILED - element not found")
            if do_screenshot:
                self._take_screenshot(f"error_step{step_idx}_{action}")
            self.result["steps_failed"] += 1
            return False

        try:
            active_page = self._get_active_page()
            if action == "click":
                elem.click()
            elif action == "fill":
                elem.click()
                active_page.wait_for_timeout(200)
                elem.fill(value)
            elif action == "press":
                elem.press(value)
            elif action == "select":
                elem.select_option(value)
            elif action == "check":
                elem.check()
            else:
                print(f"       Unknown action: {action}")
                return False

            active_page.wait_for_timeout(wait_after)
            if do_screenshot:
                self._take_screenshot(f"step{step_idx}_{action}")

            self.result["steps_completed"] += 1
            print(f"       OK")
            return True

        except Exception as e:
            if optional:
                print(f"       SKIP (optional, error: {e})")
                return True
            print(f"       ERROR: {e}")
            if do_screenshot:
                self._take_screenshot(f"error_step{step_idx}")
            self.result["steps_failed"] += 1
            return False

    def _get_active_page(self):
        """获取当前活跃的页面(处理新标签页)"""
        # 如果有新打开的页面,使用最新的
        pages = self.context.pages
        if len(pages) > 1:
            return pages[-1]  # 最新打开的页面
        return self.page

    def _get_active_locator(self):
        """获取当前操作的元素定位器(自动处理 iframe)"""
        page = self._get_active_page()
        if self.current_frame:
            return self.current_frame
        return page

    def _switch_to_frame(self, frame_idx: int):
        """切换到指定的 iframe"""
        page = self._get_active_page()
        frames = page.frames
        if frame_idx < len(frames):
            self.current_frame = frames[frame_idx]
            print(f"       Switched to frame {frame_idx}: {frames[frame_idx].url[:100]}")
            return True
        print(f"       Frame {frame_idx} not found (total: {len(frames)})")
        return False

    def _setup_new_page_listener(self):
        """设置新页面监听器"""
        self._new_pages = []

        def handle_page(page):
            self._new_pages.append(page)
            print(f"       [NEW PAGE] {page.url[:120]}")

        self.context.on("page", handle_page)

    def run(self) -> dict:
        """执行完整流程"""
        steps = self.flow.get("steps", [])
        total = len(steps)

        print("\n" + "=" * 50)
        print(f" [FlowBooker] Starting: {self.flow.get('name', 'Booking')}")
        print(f"   Total steps: {total}")
        print(f"   Target date: {self.vars['target_date']}")
        print(f"   Time slot: {self.vars['time_slot']}")
        print(f"   Venue: {self.vars['venue_name']}")
        print(f"   Campus: {self.vars['campus']}")
        print("=" * 50 + "\n")

        self._setup_new_page_listener()

        for i, step in enumerate(steps):
            self.page.wait_for_timeout(50)

            # 检查是否有新页面打开
            expect_new = step.get("expect_new_page", False)
            if expect_new and hasattr(self, '_new_pages') and self._new_pages:
                new_page = self._new_pages[-1]
                self.page = new_page
                print(f"       Switched to new page: {new_page.url[:120]}")
                new_page.wait_for_timeout(1500)
                self._new_pages = []

            ok = self._execute_step(step, i + 1)

            if not ok:
                recent = self.result["steps_failed"]
                if recent >= 3 and recent > total * 0.5:
                    self._take_screenshot("too_many_failures")
                    self.result["message"] = f"Too many failures ({recent}/{total})"
                    break

        self.result["success"] = self.result["steps_failed"] < total
        self.result["message"] = (
            f"Completed: {self.result['steps_completed']}/{total} steps OK, "
            f"{self.result['steps_failed']} failed"
        )
        print(f"\n[FlowBooker] Done: {self.result['message']}")
        return self.result
