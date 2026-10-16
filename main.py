# -*- coding: utf-8 -*-
"""ClipCut 入口。CLIPCUT_SELFTEST=ui|full 时进入自检模式。"""
import os
import sys

from PySide6.QtWidgets import QApplication


def main():
    app = QApplication(sys.argv)

    from app import MainWindow      # 主题 QSS 由 MainWindow 按用户设置应用
    win = MainWindow()
    win.show()

    mode = os.environ.get("CLIPCUT_SELFTEST")
    if mode:
        from selftest import SelfTest
        win._selftest = SelfTest(win, mode)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
