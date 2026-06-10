"""
GUI 应用模块 - 使用 PySide6 构建现代化界面
"""
import os
import json
from datetime import datetime

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QComboBox, QLineEdit,
    QGroupBox, QFormLayout, QSlider, QScrollArea,
    QMessageBox, QApplication, QDateEdit, QTimeEdit,
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QTime
from PySide6.QtGui import QFont

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

# ── 校区 + 场地联动数据 ──
CAMPUS_VENUES = {
    "海淀校区": [
        "羽1", "羽2", "羽3", "羽4", "羽5", "羽6", "羽7", "羽8",
        "二层东", "二层西", "小综合1", "小综合2", "小综合3", "小综合4",
    ],
    "昌平校区": [
        "羽1", "羽2", "羽3", "羽4", "羽5", "羽6", "羽7", "羽8",
    ],
}

DURATIONS = ["1小时", "2小时"]
TIME_OPTIONS = [f"{h:02d}:00" for h in range(8, 22)]  # 08:00 - 21:00


class BookingApp(QMainWindow):

    status_signal = Signal(str)
    log_signal = Signal(str)
    countdown_signal = Signal(str)
    booking_done_signal = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("北师羽毛球预约助手")
        self.setMinimumSize(520, 580)
        self.resize(560, 620)

        self.scheduler = None
        self.booking_running = False
        self.preheat_active = False
        self.config = self._load_config()

        self.status_signal.connect(self._set_status)
        self.log_signal.connect(self._append_log)
        self.countdown_signal.connect(self._set_countdown)
        self.booking_done_signal.connect(self._on_booking_done)

        self._build_ui()
        self._load_config_to_ui()

    # ── 配置管理 ──

    def _load_config(self) -> dict:
        default = {
            "credentials": {"username": "", "password": ""},
            "booking": {
                "campus": "",
                "venue_name": "",
                "duration": "1小时",
                "advance_seconds": 5,
            },
        }
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    default.update(json.load(f))
            except Exception:
                pass
        return default

    def _save_config(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
            self._log("配置已保存")
        except Exception as e:
            self._log(f"保存配置失败: {e}")

    # ── 界面构建 ──

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(8)

        # 标题
        title = QLabel("北师羽毛球预约助手")
        title.setFont(QFont("Microsoft YaHei", 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)

        subtitle = QLabel("自动定时预订羽毛球场馆")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: gray; font-size: 11px;")
        main_layout.addWidget(subtitle)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(8)

        # ── 启动时间（何时开始抢）──
        from datetime import timedelta
        today = datetime.now().date()

        start_group = QGroupBox("启动时间（何时开始抢票）")
        start_form = QFormLayout()

        self.start_date_picker = QDateEdit()
        self.start_date_picker.setCalendarPopup(True)
        self.start_date_picker.setMinimumHeight(28)
        self.start_date_picker.setDate(today)
        self.start_date_picker.setMinimumDate(today)
        self.start_date_picker.setMaximumDate(today + timedelta(days=2))
        start_form.addRow("启动日期:", self.start_date_picker)

        self.start_time_picker = QTimeEdit()
        self.start_time_picker.setMinimumHeight(28)
        self.start_time_picker.setDisplayFormat("HH:mm:ss")
        self.start_time_picker.setTime(QTime(0, 0, 5))  # 默认 00:00:05
        start_form.addRow("启动时间:", self.start_time_picker)

        start_hint = QLabel("到启动时间后，程序自动打开浏览器开始预约。\n"
                            "通常设置为场地开放预约的时间点（如凌晨00:00）。")
        start_hint.setWordWrap(True)
        start_hint.setStyleSheet("color: #888; font-size: 10px;")
        start_form.addRow("", start_hint)

        start_group.setLayout(start_form)
        scroll_layout.addWidget(start_group)

        # ── 场地预约时间（你要预约哪个时段）──
        time_group = QGroupBox("场地预约时间（你要预约的场地时段）")
        time_form = QFormLayout()

        # 场地日期: 今天到今天+3天
        self.date_picker = QDateEdit()
        self.date_picker.setCalendarPopup(True)
        self.date_picker.setMinimumHeight(28)
        self.date_picker.setDate(today)
        self.date_picker.setMinimumDate(today)
        self.date_picker.setMaximumDate(today + timedelta(days=3))
        time_form.addRow("场地日期:", self.date_picker)

        # 场地开始时间 (下拉选择 8:00-21:00)
        self.time_combo = QComboBox()
        self.time_combo.setMinimumHeight(28)
        self.time_combo.addItems(TIME_OPTIONS)
        self.time_combo.setCurrentText("10:00")
        self.time_combo.currentTextChanged.connect(self._on_time_changed)
        time_form.addRow("开始时间:", self.time_combo)

        # 时长选择
        self.duration_combo = QComboBox()
        self.duration_combo.setMinimumHeight(28)
        self.duration_combo.addItems(DURATIONS)
        self.duration_combo.setCurrentText("1小时")
        time_form.addRow("预约时长:", self.duration_combo)

        time_group.setLayout(time_form)
        scroll_layout.addWidget(time_group)

        # ── 场地选择 ──
        venue_group = QGroupBox("场地选择")
        venue_form = QFormLayout()

        self.campus_combo = QComboBox()
        self.campus_combo.setMinimumHeight(28)
        self.campus_combo.addItem("请选择校区", "")
        for campus_name in CAMPUS_VENUES:
            self.campus_combo.addItem(campus_name, campus_name)
        self.campus_combo.currentIndexChanged.connect(self._on_campus_changed)
        venue_form.addRow("校区:", self.campus_combo)

        self.venue_combo = QComboBox()
        self.venue_combo.setMinimumHeight(28)
        self.venue_combo.setEditable(True)
        self.venue_combo.addItem("请先选择校区", "")
        venue_form.addRow("场地名称:", self.venue_combo)

        venue_group.setLayout(venue_form)
        scroll_layout.addWidget(venue_group)

        # ── 抢票策略 ──
        strategy_group = QGroupBox("抢票策略")
        strategy_form = QFormLayout()

        advance_layout = QHBoxLayout()
        self.advance_slider = QSlider(Qt.Horizontal)
        self.advance_slider.setRange(1, 30)
        self.advance_slider.setValue(5)
        self.advance_label = QLabel("5 秒")
        self.advance_slider.valueChanged.connect(
            lambda v: self.advance_label.setText(f"{v} 秒"))
        advance_layout.addWidget(self.advance_slider)
        advance_layout.addWidget(self.advance_label)
        strategy_form.addRow("提前预热:", advance_layout)

        preheat_hint = QLabel(
            "在目标时间前 N 秒自动启动浏览器并完成登录，"
            "到点瞬间提交预约请求。\n"
            "建议 3-5 秒：太快可能来不及加载页面，太慢可能被抢光。"
        )
        preheat_hint.setWordWrap(True)
        preheat_hint.setStyleSheet("color: #888; font-size: 10px;")
        strategy_form.addRow("", preheat_hint)

        strategy_group.setLayout(strategy_form)
        scroll_layout.addWidget(strategy_group)

        # ── 认证信息 ──
        auth_group = QGroupBox("认证信息 (CAS 登录)")
        auth_form = QFormLayout()

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("学工号/学号/邮箱")
        auth_form.addRow("学工号:", self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("密码")
        auth_form.addRow("密码:", self.password_input)

        auth_hint = QLabel("留空则在浏览器中手动登录")
        auth_hint.setStyleSheet("color: gray; font-size: 10px;")
        auth_form.addRow("", auth_hint)

        auth_group.setLayout(auth_form)
        scroll_layout.addWidget(auth_group)

        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll, stretch=1)

        # ── 倒计时 ──
        self.countdown_label = QLabel("--:--:--")
        self.countdown_label.setFont(QFont("Consolas", 34, QFont.Bold))
        self.countdown_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.countdown_label)

        self.status_label = QLabel("就绪 - 请配置预约信息后点击开始")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: gray;")
        main_layout.addWidget(self.status_label)

        # ── 按钮 ──
        btn_layout = QHBoxLayout()

        self.start_btn = QPushButton("开始预约")
        self.start_btn.setMinimumHeight(42)
        self.start_btn.setStyleSheet(
            "QPushButton { background-color: #2980b9; color: white; "
            "font-size: 15px; font-weight: bold; border-radius: 5px; }"
            "QPushButton:hover { background-color: #3498db; }"
            "QPushButton:disabled { background-color: #bdc3c7; }")
        self.start_btn.clicked.connect(self._start_booking)
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("停止")
        self.stop_btn.setMinimumHeight(42)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet(
            "QPushButton { background-color: #c0392b; color: white; "
            "font-size: 15px; font-weight: bold; border-radius: 5px; }"
            "QPushButton:hover { background-color: #e74c3c; }"
            "QPushButton:disabled { background-color: #bdc3c7; }")
        self.stop_btn.clicked.connect(self._stop_booking)
        btn_layout.addWidget(self.stop_btn)

        self.save_btn = QPushButton("保存配置")
        self.save_btn.setMinimumHeight(42)
        self.save_btn.clicked.connect(self._on_save_config)
        btn_layout.addWidget(self.save_btn)

        main_layout.addLayout(btn_layout)

        # ── 日志 ──
        log_group = QGroupBox("运行日志")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(70)
        self.log_text.setFont(QFont("Consolas", 9))
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)

        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self._tick_countdown)

    # ── 时间-时长联动 ──

    def _on_time_changed(self, time_text):
        """21:00时只能选1小时(22:00关门)"""
        if time_text == "21:00":
            self.duration_combo.setCurrentText("1小时")
            # 禁用1小时以上的选项
            model = self.duration_combo.model()
            for i in range(self.duration_combo.count()):
                item = model.item(i)
                if self.duration_combo.itemText(i) != "1小时":
                    item.setEnabled(False)
        else:
            # 恢复所有选项
            model = self.duration_combo.model()
            for i in range(self.duration_combo.count()):
                model.item(i).setEnabled(True)

    # ── 校区-场地联动 ──

    def _on_campus_changed(self, idx):
        campus = self.campus_combo.currentData() or self.campus_combo.currentText()
        self.venue_combo.clear()
        if campus in CAMPUS_VENUES:
            for v in CAMPUS_VENUES[campus]:
                self.venue_combo.addItem(v, v)
        elif campus and campus != "请选择校区":
            # 未知校区，允许手动输入
            self.venue_combo.setEditable(True)
            self.venue_combo.addItem("(请手动输入)", "")
        else:
            self.venue_combo.addItem("请先选择校区", "")

    # ── 信号槽 ──

    @Slot(str)
    def _set_status(self, msg):
        self.status_label.setText(msg)

    @Slot(str)
    def _append_log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{ts}] {msg}")

    @Slot(str)
    def _set_countdown(self, cd):
        self.countdown_label.setText(cd)

    def _log(self, msg):
        self.log_signal.emit(msg)

    # ── 配置保存/加载 ──

    def _load_config_to_ui(self):
        b = self.config.get("booking", {})
        c = self.config.get("credentials", {})

        campus = b.get("campus", "")
        for i in range(self.campus_combo.count()):
            if self.campus_combo.itemData(i) == campus or \
               self.campus_combo.itemText(i) == campus:
                self.campus_combo.setCurrentIndex(i)
                break

        venue = b.get("venue_name", "")
        if venue:
            idx = self.venue_combo.findText(venue)
            if idx >= 0:
                self.venue_combo.setCurrentIndex(idx)
            else:
                self.venue_combo.setCurrentText(venue)

        idx = self.duration_combo.findText(b.get("duration", "1小时"))
        if idx >= 0:
            self.duration_combo.setCurrentIndex(idx)

        self.advance_slider.setValue(b.get("advance_seconds", 5))
        self.username_input.setText(c.get("username", ""))
        self.password_input.setText(c.get("password", ""))
        # 启动时间
        start_date_str = b.get("start_date", "")
        if start_date_str:
            from PySide6.QtCore import QDate
            sd = QDate.fromString(start_date_str, "yyyy-MM-dd")
            if sd.isValid():
                self.start_date_picker.setDate(sd)
        start_time_str = b.get("start_time", "00:00:05")
        from PySide6.QtCore import QTime
        st = QTime.fromString(start_time_str, "HH:mm:ss")
        if st.isValid():
            self.start_time_picker.setTime(st)
        # 场地开始时间
        target_time = b.get("target_time", "10:00")
        idx = self.time_combo.findText(target_time)
        if idx >= 0:
            self.time_combo.setCurrentIndex(idx)

    def _collect_config(self):
        self.config["booking"]["campus"] = self.campus_combo.currentData() or self.campus_combo.currentText()
        self.config["booking"]["venue_name"] = self.venue_combo.currentData() or self.venue_combo.currentText()
        self.config["booking"]["duration"] = self.duration_combo.currentText()
        self.config["booking"]["advance_seconds"] = self.advance_slider.value()
        self.config["booking"]["start_date"] = self.start_date_picker.date().toString("yyyy-MM-dd")
        self.config["booking"]["start_time"] = self.start_time_picker.time().toString("HH:mm:ss")
        self.config["booking"]["target_date"] = self.date_picker.date().toString("yyyy-MM-dd")
        self.config["booking"]["target_time"] = self.time_combo.currentText()
        self.config["credentials"]["username"] = self.username_input.text().strip()
        self.config["credentials"]["password"] = self.password_input.text().strip()

    def _on_save_config(self):
        self._collect_config()
        self._save_config()

    # ── 控制逻辑 ──

    def _get_start_datetime(self) -> str:
        """启动时间 = 何时开始执行预约"""
        date_val = self.start_date_picker.date().toString("yyyy-MM-dd")
        time_val = self.start_time_picker.time().toString("HH:mm:ss")
        return f"{date_val} {time_val}"

    def _get_time_slot(self) -> str:
        start_text = self.time_combo.currentText()
        parts = start_text.split(":")
        start_h, start_m = int(parts[0]), int(parts[1])
        dur_text = self.duration_combo.currentText()
        dur_hours = float(dur_text.replace("小时", ""))

        end_minutes = start_h * 60 + start_m + int(dur_hours * 60)
        end_h, end_m = divmod(end_minutes, 60)
        return f"{start_h:02d}:{start_m:02d}-{end_h:02d}:{end_m:02d}"

    def _start_preheat(self):
        """预热：提前验证登录并缓存 auth，到点秒开浏览器。"""
        if self.preheat_active:
            return
        self.preheat_active = True
        self._log("预热：验证登录状态...")
        self.status_signal.emit("预热中 - 验证登录...")

        try:
            from booker.browser import BrowserManager
            from booker.authenticator import Authenticator

            bm = BrowserManager(headless=False)
            bm.start()

            auth = Authenticator(
                username=self.config.get("credentials", {}).get("username", ""),
                password=self.config.get("credentials", {}).get("password", ""),
            )

            btn_found = bm.navigate_and_wait_for_button()
            bm.page.wait_for_timeout(300)

            if not btn_found and auth.is_on_login_page(bm.page):
                self._log("预热: 需要登录...")
                if auth.username:
                    auth.login(bm.page, auto_fill=True)
                else:
                    self.status_signal.emit("请在浏览器中登录...")
                    auth.wait_for_manual_login(bm.page, timeout=300)
                bm.navigate_and_wait_for_button()
                bm.page.wait_for_timeout(300)

            bm.save_auth_state()
            bm.close()
            self._log("预热完成：auth 已缓存")
            self.status_signal.emit("预热就绪 - 等待启动时间...")

        except Exception as e:
            self._log(f"预热失败: {e} (将在到达时间重试)")
        finally:
            self.preheat_active = False

    def _cleanup_preheat(self):
        self.preheat_active = False

    def _tick_countdown(self):
        if self.scheduler and self.scheduler.running:
            cd = self.scheduler.get_countdown_str()
            self.countdown_label.setText(cd)
        else:
            self.countdown_timer.stop()

    def _start_booking(self):
        self._collect_config()
        self._save_config()

        start_dt = self._get_start_datetime()
        time_slot = self._get_time_slot()

        if not self.date_picker.date().isValid():
            QMessageBox.warning(self, "配置错误", "请选择有效的场地日期！")
            return

        self._log(f"启动时间: {start_dt} (到点自动开始抢票)")
        self._log(f"预约目标: {self.date_picker.date().toString('yyyy-MM-dd')} "
                  f"{time_slot} ({self.duration_combo.currentText()})")
        self._log(f"场地: {self.venue_combo.currentText()}, "
                  f"校区: {self.campus_combo.currentText()}")

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        booking_config = {
            "target_date": self.date_picker.date().toString("yyyy-MM-dd"),
            "target_time": self.time_combo.currentText(),
            "venue_name": self.venue_combo.currentData() or self.venue_combo.currentText(),
            "venue_name_2": "",
            "campus": self.campus_combo.currentData() or self.campus_combo.currentText(),
            "time_slot": time_slot,
            "duration": self.duration_combo.currentText(),
            "advance_seconds": self.advance_slider.value(),
        }

        from booker.scheduler import Scheduler
        from datetime import datetime

        # 检查启动时间是否已过
        target_dt = datetime.strptime(start_dt, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        if target_dt <= now:
            # 时间已过，立即执行
            self._log(f"启动时间 {start_dt} 已过，立即开始预约...")
            self.status_signal.emit("立即开始预约...")
            QTimer.singleShot(500, lambda: self._execute_booking(booking_config))
        else:
            # 预热：提前验证登录缓存 auth
            self._start_preheat()

            self.scheduler = Scheduler(
                target_time=start_dt,
                callback=lambda: self._execute_booking(booking_config),
                advance_seconds=self.advance_slider.value(),
            )
            self.scheduler.set_status_callback(
                lambda msg: self.status_signal.emit(msg))
            self.scheduler.start()
            self.countdown_timer.start(500)

        self._log(f"预约目标: {booking_config['target_date']} {booking_config['target_time']} "
                  f"({booking_config['duration']}) {booking_config['venue_name']}")

    def _stop_booking(self):
        if self.scheduler:
            self.scheduler.stop()
        self.countdown_timer.stop()
        self._cleanup_preheat()
        self._log("预约已取消")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.countdown_label.setText("--:--:--")
        self.status_label.setText("已停止")

    def _execute_booking(self, booking_config: dict):
        if self.booking_running:
            print("[Booking] Already running, skip")
            return
        self.booking_running = True

        try:
            print("[Booking] === Starting booking execution ===")
            self.log_signal.emit("=" * 40)
            self.log_signal.emit("开始执行预约流程...")

            from booker.browser import BrowserManager
            from booker.authenticator import Authenticator
            from booker.booker import FlowBooker

            print("[Booking] Launching browser...")
            bm = BrowserManager(headless=False)
            bm.start()
            page = bm.page
            print("[Booking] Browser launched")

            auth = Authenticator(
                username=self.config.get("credentials", {}).get("username", ""),
                password=self.config.get("credentials", {}).get("password", ""),
            )

            print("[Booking] Fast navigating to target URL...")
            btn_found = bm.navigate_and_wait_for_button()
            # 等 Vue 渲染完毕 (按钮可见 ≠ 页面可交互)
            page.wait_for_timeout(2000)
            print(f"[Booking] Current URL: {page.url[:100]}")

            if not btn_found and auth.is_on_login_page(page):
                print("[Booking] Login page detected")
                if auth.username:
                    self.log_signal.emit("自动登录中...")
                    auth.login(page, auto_fill=True)
                else:
                    self.log_signal.emit("需要手动登录，请在浏览器中输入账号密码")
                    auth.wait_for_manual_login(page, timeout=300)
                # 登录成功，重新导航
                bm.navigate_and_wait_for_button()
                page.wait_for_timeout(300)
            else:
                print("[Booking] Already logged in")

            bm.save_auth_state()

            print(f"[Booking] Running flow booker: {booking_config}")
            booker = FlowBooker(page, booking_config)
            result = booker.run()
            print(f"[Booking] Flow result: {result.get('message')}")

            if result.get("success"):
                self.log_signal.emit("预约流程执行完成！请检查浏览器确认结果")
            else:
                self.log_signal.emit(result.get("message", "预约流程结束"))

            self.log_signal.emit("浏览器将在 30 秒后关闭...")
            page.wait_for_timeout(30000)
            bm.close()
            print("[Booking] === Booking execution completed ===")

        except Exception as e:
            print(f"[Booking] ERROR: {e}")
            import traceback
            traceback.print_exc()
            self.log_signal.emit(f"预约执行出错: {e}")
            self.log_signal.emit(traceback.format_exc())
        finally:
            self.booking_running = False
            self.booking_done_signal.emit()

    def _on_booking_done(self):
        self._cleanup_preheat()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.countdown_timer.stop()
        self.countdown_label.setText("--:--:--")
        self.status_label.setText("预约流程已结束")

    def closeEvent(self, event):
        if self.scheduler and self.scheduler.running:
            reply = QMessageBox.question(
                self, "确认退出",
                "定时器正在运行中，确定要退出吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self._stop_booking()
                self._cleanup_preheat()
                event.accept()
            else:
                event.ignore()
        else:
            self._cleanup_preheat()
            event.accept()
