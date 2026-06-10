"""
北师羽毛球预约助手 - 主入口
启动 GUI 桌面应用
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from gui.app import BookingApp


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # 跨平台一致风格
    window = BookingApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
