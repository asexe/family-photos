"""家庭相册入口：python main.py 启动。"""
import sys
from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from app.db import Database
from app.thumbs import ensure_pil_plugins
from app.ui.main_window import MainWindow
from app.ui.style import FONT_FAMILIES, apply_constants, QSS

def _base_dir() -> Path:
    """打包成 exe 后，数据目录放在 exe 旁边；开发时即项目根目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_DIR = _base_dir()
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
    # 升级兼容：为已有 GPS 但尚无地点的记录回填「省·市」（首次运行稍慢，之后跳过）
    try:
        from app.places import backfill as backfill_places
        filled = backfill_places(db)
        if filled:
            print(f"已回填 {filled} 条地点信息")
    except Exception:
        pass
    win = MainWindow(db, DATA_DIR)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
