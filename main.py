"""家庭相册入口：python main.py 启动。"""
import sys
from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from app.db import Database
from app.thumbs import ensure_pil_plugins
from app.ui.main_window import MainWindow
from app.ui.style import FONT_FAMILIES, apply_constants, QSS

APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"


def main():
    ensure_pil_plugins()
    app = QApplication(sys.argv)
    app.setApplicationName("家庭相册")
    app.setOrganizationName("Family")
    app.setStyle("Fusion")
    # 强制浅色调色板：即使 Windows 处于深色模式，默认控件（消息框/输入框/弹层）也保持浅色
    app.setPalette(app.style().standardPalette())

    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPointSize(10)
    app.setFont(font)
    app.setStyleSheet(apply_constants(QSS))

    db = Database(DATA_DIR / "photos.db")
    db.init()
    win = MainWindow(db, DATA_DIR)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
