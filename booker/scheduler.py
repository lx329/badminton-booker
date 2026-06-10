"""
定时调度模块 - 精确到点触发预约，带倒计时
"""
import time
import threading
from datetime import datetime, timedelta


class Scheduler:
    """预约定时器"""

    def __init__(self, target_time: str, callback, advance_seconds: int = 5):
        """
        target_time: "2026-06-13 20:00:00" 或 "20:00:00" 格式
        callback: 到达时间后调用的预约函数
        advance_seconds: 提前多少秒启动浏览器预热
        """
        self.target_time_str = target_time
        self.callback = callback
        self.advance_seconds = advance_seconds
        self.running = False
        self.thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._status_callback = None  # 用于更新 GUI 状态

        # 解析目标时间
        self.target_dt = self._parse_time(target_time)

    def _parse_time(self, time_str: str) -> datetime:
        """解析时间字符串"""
        now = datetime.now()
        time_str = time_str.strip()

        # 尝试解析完整日期时间
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(time_str, fmt)
            except ValueError:
                continue

        # 只给了时间（如 "08:00:00"），认为是今天
        time_formats = ["%H:%M:%S", "%H:%M"]
        for fmt in time_formats:
            try:
                parsed = datetime.strptime(time_str, fmt)
                result = now.replace(
                    hour=parsed.hour, minute=parsed.minute,
                    second=parsed.second, microsecond=0
                )
                # 如果今天的时间已过，则设定为明天
                if result <= now:
                    result += timedelta(days=1)
                return result
            except ValueError:
                continue

        raise ValueError(f"Cannot parse time: {time_str}")

    def set_status_callback(self, callback):
        """设置状态回调（用于更新 GUI）"""
        self._status_callback = callback

    def _update_status(self, message: str):
        """通过回调更新状态"""
        if self._status_callback:
            self._status_callback(message)

    def get_remaining_seconds(self) -> float:
        """获取距离目标时间的剩余秒数"""
        return (self.target_dt - datetime.now()).total_seconds()

    def get_countdown_str(self) -> str:
        """获取格式化的倒计时字符串"""
        remaining = self.get_remaining_seconds()
        if remaining <= 0:
            return "00:00:00"

        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        seconds = int(remaining % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def start(self):
        """启动定时器（在后台线程中运行）"""
        if self.running:
            print("[Scheduler] Already running!")
            return

        remaining = self.get_remaining_seconds()
        if remaining <= 0:
            print("[Scheduler] Target time already passed!")
            self._update_status("目标时间已过，立即执行预订...")
            self.callback()
            return

        self.running = True
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        print(f"[Scheduler] Started. Target: {self.target_dt}, "
              f"Remaining: {self.get_countdown_str()}")
        self._update_status(f"定时器已启动，距目标时间 {self.get_countdown_str()}")

    def stop(self):
        """停止定时器"""
        self.running = False
        self._stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
        print("[Scheduler] Stopped")
        self._update_status("定时器已停止")

    def _run(self):
        """后台运行的主循环"""
        # 预热阶段：在目标时间前 advance_seconds 秒启动浏览器
        while self.running and not self._stop_event.is_set():
            remaining = self.get_remaining_seconds()

            if remaining <= 0:
                # 时间到！执行预约
                print(f"\n[Scheduler] TIME'S UP! Executing booking at {datetime.now()}")
                self._update_status("时间到！正在执行预约...")
                try:
                    self.callback()
                except Exception as e:
                    print(f"[Scheduler] Booking error: {e}")
                    self._update_status(f"预约出错: {e}")
                self.running = False
                break

            # 更新状态
            countdown = self.get_countdown_str()
            if remaining <= self.advance_seconds:
                status = f"即将开始预约！预热中... {countdown}"
            elif remaining < 60:
                status = f"倒计时: {countdown}"
            else:
                # 每30秒更新一次（减少日志输出）
                if int(remaining) % 30 == 0:
                    status = f"等待中... 距目标时间 {countdown}"

            self._update_status(status)

            # 睡眠间隔：最后1分钟每秒检查一次，之前每5秒检查一次
            if remaining <= 60:
                sleep_time = 0.5  # 更精确
            elif remaining <= 300:
                sleep_time = 2
            else:
                sleep_time = 5

            # 分段睡眠以避免长时间阻塞
            for _ in range(int(sleep_time * 2)):
                if self._stop_event.is_set():
                    break
                time.sleep(0.5)

        self.running = False
        print("[Scheduler] Loop ended")
