"""
旋转滑块验证码自动求解器 (dd-core-captcha-slider)
水平拖拽滑块控制图片旋转角度，直到图片正立

实测结论:
- TouchEvent dispatch 可以移动滑块
- 松开鼠标后验证码会验证角度，不对则重置图片
- CAPTCHA 弹窗在 iframe 内
"""
import io
import time
import math
import random
import re
from playwright.sync_api import Page, Frame


class RotationCaptchaSolver:
    """旋转滑块验证码自动求解"""

    def __init__(self, page: Page):
        self.page = page
        self.max_retries = 3

    # ── 求解主流程 ──

    def solve(self, scope=None) -> bool:
        target = scope if scope else self.page

        for attempt in range(self.max_retries):
            print(f"[Captcha] === Attempt {attempt + 1}/{self.max_retries} ===")

            # 1. 确认弹窗出现 (验证码弹窗包含 .slider)
            try:
                dialog = target.locator('.el-dialog:visible:has(.slider)')
                if not dialog.is_visible(timeout=1000):
                    # 回退: 取第一个可见弹窗
                    dialog = target.locator('.el-dialog:visible').first
                dialog.wait_for(state="visible", timeout=5000)
                print("[Captcha] Dialog visible")
            except Exception:
                print("[Captcha] Dialog not found - may already be solved")
                return True

            # 2. 截取验证码图片
            img_bytes = self._capture_image(target)
            if not img_bytes:
                print("[Captcha] Failed to capture image, refreshing...")
                self._refresh(target)
                continue
            print(f"[Captcha] Image captured: {len(img_bytes)} bytes")

            # 3. 检测旋转角度 - 优先从 Vue config.A 读取
            angle = self._read_angle_from_vue(target)
            if angle is not None:
                print(f"[Captcha] Angle from config.A: {angle:.1f} deg")
            else:
                print("[Captcha] Failed to read config.A, trying OpenCV...")
                angle = self._detect_rotation(img_bytes)

            if angle is None:
                print("[Captcha] Angle detection failed, refreshing...")
                self._refresh(target)
                continue
            print(f"[Captcha] Rotation needed: {angle:.1f} deg")

            # 4. 计算拖拽距离
            slider_w = self._get_track_width(target)
            distance = self._compute_distance(angle, slider_w)
            print(f"[Captcha] Track={slider_w}px, drag={distance:.0f}px")

            # 5. 执行拖拽
            self._human_drag(target, distance)

            # 6. 等待验证结果
            time.sleep(2.0)

            # 7. 检查结果 (验证码弹窗是否消失)
            try:
                still_visible = target.locator(
                    '.el-dialog:visible:has(.slider)'
                ).is_visible(timeout=500)
            except Exception:
                still_visible = False

            if not still_visible:
                print("[Captcha] Dialog closed -- VERIFIED!")
                return True

            # 检查错误信息
            try:
                error_el = target.locator(
                    '[class*=error]:visible, .el-message--error:visible'
                )
                if error_el.is_visible(timeout=500):
                    txt = error_el.text_content() or ''
                    print(f"[Captcha] Error: {txt[:100]}")
            except Exception:
                pass

            self._refresh(target)
            time.sleep(0.5)

        print("[Captcha] All retries exhausted")
        return False

    # ── 图片截取 ──

    def _capture_image(self, scope) -> bytes | None:
        try:
            img = scope.locator('img.scene-image')
            if not img.is_visible(timeout=2000):
                print("[Captcha] scene-image not visible")
                return None
            return img.screenshot()
        except Exception as e:
            print(f"[Captcha] Screenshot error: {e}")
            try:
                base64 = scope.evaluate("""() => {
                    const img = document.querySelector('img.scene-image');
                    if (!img || !img.complete) return null;
                    const c = document.createElement('canvas');
                    c.width = img.naturalWidth;
                    c.height = img.naturalHeight;
                    c.getContext('2d').drawImage(img, 0, 0);
                    return c.toDataURL('image/png');
                }""")
                if base64 and ',' in str(base64):
                    import base64 as b64
                    return b64.b64decode(str(base64).split(',')[1])
            except Exception as e2:
                print(f"[Captcha] JS fallback failed: {e2}")
        return None

    # ── 旋转角度检测 ──

    def _detect_rotation(self, img_bytes: bytes) -> float | None:
        try:
            import cv2
            import numpy as np

            arr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                return None

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape
            gray = cv2.GaussianBlur(gray, (3, 3), 0)

            median = np.median(gray)
            lo = int(max(0, 0.66 * median))
            hi = int(min(255, 1.33 * median))
            edges = cv2.Canny(gray, lo, hi)

            lines = cv2.HoughLines(
                edges, 1, np.pi / 180,
                threshold=max(30, min(w, h) // 8)
            )
            if lines is None:
                return None

            angle_hist = [0] * 180
            for rho_theta in lines:
                rho, theta = rho_theta[0]
                deg = int(np.rad2deg(theta)) % 180
                angle_hist[deg] += 1

            angle_hist = np.convolve(angle_hist, [1, 2, 3, 2, 1], mode='same')

            best_offset = 0
            best_score = 0
            for offset in range(-45, 46):
                score = 0
                for base in [0, 90]:
                    idx = (base + offset) % 180
                    score += angle_hist[idx]
                    for d in [-2, -1, 1, 2]:
                        score += angle_hist[(idx + d) % 180] * 0.5
                if score > best_score:
                    best_score = score
                    best_offset = offset

            print(f"[Captcha] Best offset={best_offset}, score={best_score:.0f}, "
                  f"lines={len(lines)}")

            if best_score < len(lines) * 0.15:
                print("[Captcha] Low confidence")
                return None

            return float(best_offset)

        except ImportError:
            print("[Captcha] OpenCV not installed")
            return None
        except Exception as e:
            print(f"[Captcha] Detection error: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _read_angle_from_vue(self, scope) -> float | None:
        """从 Vue 组件 config.A 读取正确的旋转角度"""
        try:
            raw = scope.evaluate(self.JS_READ_ANGLE)
            if not raw or raw == 'no slider' or raw == 'no vue/config':
                return None
            import json
            info = json.loads(raw) if isinstance(raw, str) else raw
            A = info.get('A', [])
            if not A or len(A) < 1:
                return None
            angle = float(A[0])
            # A[0] 通常接近0 (图像基本正立)
            # 如果值非常小, 直接用0度
            if abs(angle) < 0.05:
                print(f"[Captcha] config.A[0]={angle:.4f} ~= 0 deg")
                return 0.0
            return angle
        except Exception as e:
            print(f"[Captcha] Read config.A error: {e}")
            return None

    # ── 距离计算 ──

    def _get_track_width(self, scope) -> int:
        try:
            track = scope.locator('.sliderMask')
            box = track.bounding_box()
            if box:
                return int(box['width'])
        except Exception:
            pass
        return 400

    def _compute_distance(self, angle_deg: float, track_width: int) -> int:
        max_angle = 90.0
        center = track_width / 2
        px_per_deg = (track_width / 2) / max_angle
        target = center + angle_deg * px_per_deg
        return int(max(5, min(track_width - 5, target)))

    # ── 拖拽执行 ──

    # JS: 从 Vue config.A 读取正确角度并计算滑块位置
    JS_READ_ANGLE = """() => {
        const slider = document.querySelector('.slider');
        if (!slider) return 'no slider';
        let el = slider.parentElement;
        let vm = null;
        for (let i = 0; i < 10 && el; i++) {
            if (el.__vue__) { vm = el.__vue__; break; }
            el = el.parentElement;
        }
        if (!vm || !vm.config) return 'no vue/config';
        return JSON.stringify({
            A: vm.config.A,
            maxX: vm.maxX,
            currentX: vm.currentX,
            sceneWidth: vm.sceneWidth,
            shapeWidth: vm.shapeWidth,
        });
    }"""

    # JS: 暴力扫描找正确位置 (设置 currentX + 调用 valid())
    JS_SCAN_VUE = """(args) => {
        const [stepCount] = args;
        const slider = document.querySelector('.slider');
        if (!slider) return 'no slider';
        let el = slider.parentElement;
        let vm = null;
        for (let i = 0; i < 10 && el; i++) {
            if (el.__vue__) { vm = el.__vue__; break; }
            el = el.parentElement;
        }
        if (!vm) return 'no vue instance';
        const maxX = vm.maxX || 400;
        const step = maxX / stepCount;
        const results = [];
        for (let x = step; x < maxX; x += step) {
            vm.currentX = Math.round(x);
            if (typeof vm.valid === 'function' && vm.valid()) {
                return 'SOLVED at x=' + x + ' maxX=' + maxX;
            }
            results.push(x + ':' + (typeof vm.valid === 'function' ? vm.valid() : 'no valid fn'));
        }
        return 'scanned ' + stepCount + ' steps, results: ' + results.slice(0, 10).join(',');
    }"""

    # JS: 通过 Vue 组件方法直接拖拽
    JS_VUE_DRAG = """(args) => {
        const [targetX] = args;
        const slider = document.querySelector('.slider');
        if (!slider) return 'no slider';
        let el = slider.parentElement;
        let vm = null;
        for (let i = 0; i < 10 && el; i++) {
            if (el.__vue__) { vm = el.__vue__; break; }
            el = el.parentElement;
        }
        if (!vm) return 'no vue instance';
        const track = slider.closest('.sliderMask') || slider.parentElement;
        const trackRect = track.getBoundingClientRect();
        const clientX = trackRect.left + targetX;
        const clientY = trackRect.top + trackRect.height / 2;
        // Build proper TouchEvent-like object with touches array
        const makeTouch = (x, y) => ({
            clientX: x, clientY: y,
            pageX: x, pageY: y,
            screenX: x, screenY: y,
            target: slider,
            identifier: 0,
        });
        // touchstart
        if (vm.handleDragStart) {
            vm.handleDragStart({
                type: 'touchstart',
                target: slider,
                touches: [makeTouch(clientX, clientY)],
                targetTouches: [makeTouch(clientX, clientY)],
                changedTouches: [makeTouch(clientX, clientY)],
                preventDefault: () => {},
                stopPropagation: () => {},
            });
        }
        // touchmove
        if (vm.handleDragMove) {
            vm.handleDragMove({
                type: 'touchmove',
                target: slider,
                touches: [makeTouch(clientX, clientY)],
                targetTouches: [makeTouch(clientX, clientY)],
                changedTouches: [makeTouch(clientX, clientY)],
                preventDefault: () => {},
                stopPropagation: () => {},
            });
        }
        // touchend
        if (vm.handleDragEnd) {
            vm.handleDragEnd({
                type: 'touchend',
                target: slider,
                touches: [],
                targetTouches: [],
                changedTouches: [makeTouch(clientX, clientY)],
                preventDefault: () => {},
                stopPropagation: () => {},
            });
        }
        return 'vue done, currentX=' + vm.currentX + ', value=' + vm.value + ', valid=' + vm.valid;
    }"""

    # JS 代码片段 (类变量)
    JS_TOUCH_DRAG = """(args) => {
        const [sx, sy, dx, dy] = args;
        const slider = document.querySelector('.slider');
        if (!slider) return 'no slider';
        const mt = (x, y) => new Touch({
            identifier: 0, target: slider,
            clientX: x, clientY: y,
            screenX: x, screenY: y,
            pageX: x, pageY: y,
            radiusX: 1, radiusY: 1,
            rotationAngle: 0, force: 0.5,
        });
        // touchstart on slider
        slider.dispatchEvent(new TouchEvent('touchstart', {
            bubbles: true, cancelable: true,
            touches: [mt(sx, sy)],
            targetTouches: [mt(sx, sy)],
            changedTouches: [mt(sx, sy)],
        }));
        // touchmove on document
        for (let i = 1; i <= 30; i++) {
            const p = i / 30;
            const ease = 1 - Math.pow(1 - p, 2.5);
            const cx = sx + (dx - sx) * ease + (Math.random() - 0.5) * 1;
            const cy = dy + (Math.random() - 0.5) * 0.5;
            const t = mt(cx, cy);
            document.dispatchEvent(new TouchEvent('touchmove', {
                bubbles: true, cancelable: true,
                touches: [t], targetTouches: [t], changedTouches: [t],
            }));
        }
        // touchend on document
        const t = mt(dx, dy);
        document.dispatchEvent(new TouchEvent('touchend', {
            bubbles: true, cancelable: true,
            touches: [], targetTouches: [], changedTouches: [t],
        }));
        return slider.style.left || 'unknown';
    }"""

    JS_POINTER_DRAG = """(args) => {
        const [sx, sy, dx, dy] = args;
        const mk = (type, x, y) => new PointerEvent(type, {
            bubbles: true, cancelable: true,
            clientX: x, clientY: y,
            screenX: x, screenY: y,
            pointerId: 1, pointerType: 'mouse',
            isPrimary: true, pressure: 0.5,
            width: 1, height: 1,
        });
        const slider = document.querySelector('.slider');
        if (!slider) return 'no slider';
        slider.dispatchEvent(mk('pointerdown', sx, sy));
        for (let i = 1; i <= 30; i++) {
            const p = i / 30;
            const ease = 1 - Math.pow(1 - p, 2.5);
            const cx = sx + (dx - sx) * ease + (Math.random() - 0.5) * 1;
            const cy = dy + (Math.random() - 0.5) * 0.5;
            document.dispatchEvent(mk('pointermove', cx, cy));
        }
        document.dispatchEvent(mk('pointerup', dx, dy));
        return slider.style.left || 'unknown';
    }"""

    def _human_drag(self, scope, target_x: int):
        """模拟拖拽 - TouchEvent 优先 (实测可行)"""
        slider = scope.locator('.slider')
        try:
            box = slider.bounding_box()
        except Exception as e:
            print(f"[Captcha] slider bounding_box error: {e}")
            box = None

        if not box:
            page = self.page
            if hasattr(scope, 'page'):
                page = scope.page
            slider = page.locator('.slider')
            try:
                box = slider.bounding_box()
            except Exception:
                box = None
            if not box:
                print("[Captcha] slider not found")
                self._dump_captcha_dom(page)
                return
            scope = page
            print("[Captcha] Found slider on main page")

        print(f"[Captcha] Slider: x={box['x']:.0f} y={box['y']:.0f} "
              f"w={box['width']} h={box['height']}")

        sx = box['x'] + box['width'] / 2      # 滑块当前中心
        sy = box['y'] + box['height'] / 2     # 滑块垂直中心

        track = scope.locator('.sliderMask')
        try:
            track_box = track.bounding_box()
        except Exception:
            track_box = None
        track_left = track_box['x'] if track_box else box['x']

        # 修正: dx = 滑块中心在目标位置 (不是左边缘!)
        dx = track_left + target_x + box['width'] / 2
        dy = sy
        args = [sx, sy, dx, dy]

        print(f"[Captcha] Drag: ({sx:.0f}, {sy:.0f}) -> ({dx:.0f}, {dy:.0f}) "
              f"distance={target_x}px")

        # 方式0: 暴力扫描 Vue 组件找正确位置
        print("[Captcha] Trying Vue state scan...")
        try:
            r = scope.evaluate(self.JS_SCAN_VUE, [16])
            print(f"[Captcha]   Scan result: {r}")
            time.sleep(0.3)
            # 检查是否解决了
            try:
                still = target.locator(
                    '.el-dialog:visible:has(.slider)'
                ).is_visible(timeout=500)
                if not still:
                    print("[Captcha] Vue scan SOLVED!")
                    return
            except Exception:
                pass
        except Exception as e:
            print(f"[Captcha]   Scan error: {e}")

        # 方式1: Vue 组件方法直接调用
        print("[Captcha] Trying Vue component method...")
        try:
            r = scope.evaluate(self.JS_VUE_DRAG, [target_x])
            print(f"[Captcha]   Vue result: {r}")
            time.sleep(0.3)
            if self._slider_moved(slider):
                print("[Captcha] Vue method SUCCESS")
                return
        except Exception as e:
            print(f"[Captcha]   Vue error: {e}")

        # 方式1: TouchEvent (实测有效!)
        print("[Captcha] Trying TouchEvent...")
        try:
            r = scope.evaluate(self.JS_TOUCH_DRAG, args)
            print(f"[Captcha]   result: {r}")
            time.sleep(0.3)
            if self._slider_moved(slider):
                print("[Captcha] TouchEvent SUCCESS")
                return
        except Exception as e:
            print(f"[Captcha]   error: {e}")

        # 方式2: PointerEvent
        print("[Captcha] Trying PointerEvent...")
        try:
            r = scope.evaluate(self.JS_POINTER_DRAG, args)
            print(f"[Captcha]   result: {r}")
            time.sleep(0.3)
            if self._slider_moved(slider):
                print("[Captcha] PointerEvent SUCCESS")
                return
        except Exception as e:
            print(f"[Captcha]   error: {e}")

        # 方式3: Playwright mouse
        print("[Captcha] Trying Playwright mouse...")
        self._drag_playwright(scope, sx, sy, dx, dy)
        time.sleep(0.3)
        if self._slider_moved(slider):
            print("[Captcha] Playwright SUCCESS")
            return

        # 探测 Vue 状态
        self._probe_vue(scope)

    def _slider_moved(self, slider) -> bool:
        try:
            style = slider.get_attribute('style') or ''
            m = re.search(r'left:\s*(\d+)px', style)
            return bool(m and int(m.group(1)) > 5)
        except Exception:
            return False

    def _drag_playwright(self, scope, sx, sy, dx, dy):
        """Playwright mouse drag"""
        page = self.page
        if hasattr(scope, 'page') and scope.page:
            page = scope.page
        page.mouse.move(sx, sy, steps=5)
        time.sleep(random.uniform(0.03, 0.06))
        page.mouse.down()
        time.sleep(random.uniform(0.02, 0.04))
        for i in range(random.randint(12, 20)):
            progress = (i + 1) / 20
            eased = 1 - math.pow(1 - progress, 2.5)
            page.mouse.move(
                sx + (dx - sx) * eased + random.uniform(-0.8, 0.8),
                dy + random.uniform(-0.3, 0.3),
            )
            time.sleep(random.uniform(0.008, 0.02))
        time.sleep(random.uniform(0.04, 0.08))
        page.mouse.up()

    def _probe_vue(self, scope):
        """探测 Vue 组件 - 读取所有关键状态和 payload"""
        try:
            result = scope.evaluate("""() => {
                const slider = document.querySelector('.slider');
                if (!slider) return 'no slider';
                let el = slider.parentElement;
                let vm = null;
                for (let i = 0; i < 10 && el; i++) {
                    if (el.__vue__) { vm = el.__vue__; break; }
                    el = el.parentElement;
                }
                if (!vm) return 'no vue instance';
                // Read everything useful
                const info = {};
                const keys = ['currentX','maxX','value','isDragging','sceneWidth',
                    'shapeWidth','shapeImageHeight','shapeImageWidth','id',
                    'isMouseDown','lastTrackTime','track','valid','loaded'];
                keys.forEach(k => {
                    try { info[k] = typeof vm[k] === 'function' ? 'fn' : vm[k]; }
                    catch(e) { info[k] = 'err'; }
                });
                // Try payload_data
                try {
                    if (vm.payload_data) {
                        info.payload_data = JSON.stringify(vm.payload_data).substring(0, 300);
                    }
                } catch(e) {}
                // Try config
                try {
                    if (vm.config) {
                        info.config = JSON.stringify(vm.config).substring(0, 300);
                    }
                } catch(e) {}
                // Try to call valid with proper context
                try {
                    info.validResult = vm.valid();
                } catch(e) {
                    info.validResult = 'error:' + e.message;
                }
                return JSON.stringify(info);
            }""")
            print(f"[Captcha] Vue state: {result}")
        except Exception as e:
            print(f"[Captcha] Vue error: {e}")

    def _dump_captcha_dom(self, scope):
        try:
            html = scope.evaluate("""() => {
                const d = document.querySelector('.el-dialog');
                if (!d) return 'no dialog';
                return d.innerHTML.substring(0, 600);
            }""")
            print(f"[Captcha] Dialog HTML: {html}")
        except Exception:
            pass

    def _refresh(self, scope):
        for sel in ['.card-refresh span', '[title*=换]', '.fa-refresh']:
            try:
                btn = scope.locator(sel)
                if btn.is_visible(timeout=800):
                    btn.click()
                    time.sleep(0.6)
                    return
            except Exception:
                pass
