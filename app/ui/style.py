"""苹果简约风 + 半透明圆角主题：颜色常量 + 全局 QSS。

窗口：无边框、圆角 14px、半透明（Windows 11 下叠加亚克力/Mica 背景）。
窗口控制键位于右上角：缩小（黄）、放大（绿）、关闭（红）。
"""
from PySide6.QtGui import QColor

# ---- 颜色 ----
BG = "rgba(245,245,247,225)"        # 窗口底色（半透明浅灰）
BG_SOLID = "#F5F5F7"
SIDEBAR_BG = "rgba(245,245,247,222)"
CARD_BG = "#FFFFFF"
TEXT = "#1D1D1F"
TEXT_SECONDARY = "#86868B"
SEPARATOR = "rgba(229,229,234,190)"
HOVER_BG = "#E8E8ED"
SELECT_BG = "#E0EDFF"
ACCENT = "#007AFF"
ACCENT_HOVER = "#1E88FF"
RED = "#FF3B30"
RED_HOVER = "#E02E25"
GREEN = "#28C840"
YELLOW = "#FEBC2E"
CLOSE_RED = "#FF5F57"       # 关闭（红）
MIN_YELLOW = "#FEBC2E"      # 缩小（黄）
MAX_GREEN = "#28C840"       # 放大（绿）
VIEWER_BG = "rgba(16,16,19,232)"
WINDOW_RADIUS = "16px"

USER_COLORS = ["#007AFF", "#FF3B30", "#FF9500", "#34C759",
               "#AF52DE", "#5856D6", "#FF2D55", "#5AC8FA",
               "#A2845E", "#FFCC00"]

FONT_FAMILIES = ["Segoe UI", "Microsoft YaHei UI"]

QSS = """
* { outline: none; }
QMainWindow { background: $BG; border-radius: $WINDOW_RADIUS; }
QMainWindow[viewerWindow="true"] { background: $VIEWER_BG; }
QMainWindow[winMaximized="true"] { border-radius: 0px; }
QDialog[appleDialog="true"] { background: rgba(245,245,247,250); border-radius: $WINDOW_RADIUS; }
QWidget { font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
          color: $TEXT; font-size: 13px; }

/* ---------- 标题栏（右上角：缩小黄 / 放大绿 / 关闭红） ---------- */
#titleBar { background: $BG; border-bottom: 1px solid $SEPARATOR;
            border-top-left-radius: $WINDOW_RADIUS;
            border-top-right-radius: $WINDOW_RADIUS; }
#titleBar[dark="true"] { background: rgba(20,20,24,205);
                         border-bottom: 1px solid rgba(42,42,46,190); }
#titleBar[winMaximized="true"] { border-top-left-radius: 0px;
                                 border-top-right-radius: 0px; }
#appTitle { font-size: 14px; font-weight: 600; color: $TEXT; }
#titleBar[dark="true"] #appTitle { color: #EBEBF0; }
QPushButton[class="traffic"] { border: none; border-radius: 8px;
                      min-width: 16px; max-width: 16px;
                      min-height: 16px; max-height: 16px; }
QPushButton#trafficMin    { background: $MIN_YELLOW; }
QPushButton#trafficMin:hover    { background: #FFD60A; }
QPushButton#trafficMax    { background: $MAX_GREEN; }
QPushButton#trafficMax:hover    { background: #30D158; }
QPushButton#trafficClose  { background: $CLOSE_RED; }
QPushButton#trafficClose:hover  { background: #FF3B30; }

/* ---------- 侧边栏 ---------- */
#sidebar { background: $SIDEBAR_BG; border-right: 1px solid $SEPARATOR; }
#sideHeader { color: $TEXT_SECONDARY; font-size: 11px; font-weight: 600; }
#brandLabel { font-size: 16px; font-weight: 700; color: $TEXT; }
QPushButton#sideButton {
    border: none; border-radius: 10px; padding: 7px 12px;
    text-align: left; background: transparent; color: $TEXT; }
QPushButton#sideButton:hover { background: rgba(232,232,237,220); }
QPushButton#sideButton:checked { background: rgba(232,232,237,235); font-weight: 600; }
QPushButton#sideGhost {
    border: none; border-radius: 10px; padding: 6px 12px;
    text-align: left; background: transparent; color: $TEXT_SECONDARY; }
QPushButton#sideGhost:hover { background: rgba(232,232,237,220); color: $TEXT; }

/* ---------- 家人树（带动画展开） ---------- */
#userTree { background: transparent; border: none; }
#userTree::item { border-radius: 10px; padding: 3px 6px; color: $TEXT; }
#userTree::item:hover { background: rgba(232,232,237,220); }
#userTree::item:selected { background: rgba(232,232,237,235); color: $TEXT; }
#userTree::branch { background: transparent; }
#userDot { border-radius: 4px; min-width: 8px; max-width: 8px;
           min-height: 8px; max-height: 8px; }
#badgeLabel { background: $RED; color: white; border-radius: 9px;
              font-size: 10px; font-weight: 700; padding: 0 6px; }

/* ---------- 顶部工具条 ---------- */
#viewTitle { font-size: 21px; font-weight: 700; color: $TEXT; }
#viewSubtitle { font-size: 12px; color: $TEXT_SECONDARY; }

/* ---------- 输入与选项框（圆角） ---------- */
QComboBox, QLineEdit {
    background: $CARD_BG; border: 1px solid #D1D1D6; border-radius: 10px;
    padding: 6px 10px; color: $TEXT; }
QComboBox:hover, QLineEdit:hover { border-color: #B8B8BE; }
QComboBox:focus, QLineEdit:focus { border-color: $ACCENT; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox::down-arrow { image: none; border-left: 4px solid transparent;
                        border-right: 4px solid transparent;
                        border-top: 5px solid #86868B; margin-right: 9px; }
QComboBox QAbstractItemView {
    background: $CARD_BG; border: 1px solid $SEPARATOR; border-radius: 12px;
    padding: 4px; selection-background-color: $ACCENT;
    selection-color: white; }
QComboBox QAbstractItemView::item { border-radius: 8px; padding: 5px 8px; }

QPushButton#primary {
    background: $ACCENT; color: white; border: none; border-radius: 10px;
    padding: 7px 16px; font-weight: 600; }
QPushButton#primary:hover { background: $ACCENT_HOVER; }
QPushButton#primary:disabled { background: #B0D2FF; }
QPushButton#ghost {
    background: rgba(255,255,255,220); border: 1px solid #D1D1D6; border-radius: 10px;
    padding: 7px 14px; color: $TEXT; }
QPushButton#ghost:hover { background: $HOVER_BG; }
QPushButton#ghost:disabled { color: #B8B8BE; border-color: #E5E5EA; }

/* ---------- 缩略图墙（由 PhotoDelegate 绘制缩略图与日期，避免重叠） ---------- */
#photoWall { background: rgba(255,255,255,242); border: none; border-radius: 12px; }
#emptyHint { color: $TEXT_SECONDARY; font-size: 15px; }

/* ---------- 状态栏 ---------- */
QStatusBar { background: $BG; color: $TEXT_SECONDARY;
             border-top: 1px solid $SEPARATOR;
             border-bottom-left-radius: $WINDOW_RADIUS;
             border-bottom-right-radius: $WINDOW_RADIUS; }
QStatusBar[winMaximized="true"] { border-bottom-left-radius: 0px;
                                  border-bottom-right-radius: 0px; }
QStatusBar::item { border: none; }
QProgressBar { background: #E5E5EA; border: none; border-radius: 4px;
               max-height: 6px; text-align: center; }
QProgressBar::chunk { background: $ACCENT; border-radius: 4px; }

/* ---------- 滚动条 ---------- */
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #D1D1D6; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #B8B8BE; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #D1D1D6; border-radius: 5px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* ---------- 菜单 ---------- */
QMenu { background: $CARD_BG; border: 1px solid $SEPARATOR; border-radius: 12px;
        padding: 6px; }
QMenu::item { padding: 7px 24px 7px 14px; border-radius: 8px; color: $TEXT; }
QMenu::item:selected { background: $ACCENT; color: white; }
QMenu::separator { height: 1px; background: $SEPARATOR; margin: 4px 8px; }

/* ---------- 对话框内部 ---------- */
QDialog[appleDialog="true"] QLabel { color: $TEXT; }
QDialog[appleDialog="true"] #dialogTitle { font-size: 17px; font-weight: 700; }
QListWidget { background: $CARD_BG; border: 1px solid $SEPARATOR; border-radius: 12px; }
QListWidget::item { padding: 8px 10px; border-radius: 10px; }
QListWidget::item:hover { background: #F2F2F7; }
QListWidget::item:selected { background: $SELECT_BG; color: $TEXT; }

/* ---------- 系统消息框 / 输入框（深色模式下也保持浅色） ---------- */
QMessageBox { background: #F5F5F7; }
QMessageBox QLabel { color: $TEXT; font-size: 13px; }
QMessageBox QPushButton {
    background: $ACCENT; color: white; border: none; border-radius: 8px;
    padding: 6px 18px; min-width: 64px; }
QMessageBox QPushButton:hover { background: $ACCENT_HOVER; }
QInputDialog { background: #F5F5F7; }
QInputDialog QLabel { color: $TEXT; }
QInputDialog QLineEdit {
    background: $CARD_BG; border: 1px solid #D1D1D6; border-radius: 8px;
    padding: 6px 10px; color: $TEXT; }
QInputDialog QPushButton {
    background: $ACCENT; color: white; border: none; border-radius: 8px;
    padding: 6px 18px; min-width: 64px; }
QInputDialog QPushButton:hover { background: $ACCENT_HOVER; }

QCheckBox, QRadioButton { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 2px solid #D1D1D6;
                       border-radius: 5px; background: white; }
QCheckBox::indicator:checked { background: $ACCENT; border-color: $ACCENT; }
QRadioButton::indicator { width: 16px; height: 16px; border: 2px solid #D1D1D6;
                          border-radius: 8px; background: white; }
QRadioButton::indicator:checked { border: 5px solid $ACCENT; background: white; }

/* ---------- 大图浏览窗口 ---------- */
#viewer { background: transparent; }
#viewerToolbar { background: rgba(20,20,24,205);
                 border-bottom: 1px solid rgba(42,42,46,190); }
#viewerToolbar QLabel { color: #EBEBF0; }
QPushButton#viewerBtn {
    background: transparent; color: #EBEBF0; border: none; border-radius: 10px;
    padding: 6px 12px; font-size: 13px; }
QPushButton#viewerBtn:hover { background: #3A3A40; }
#viewerInfo { background: rgba(20,20,24,215); border-top: 1px solid rgba(42,42,46,190);
              border-bottom-left-radius: $WINDOW_RADIUS;
              border-bottom-right-radius: $WINDOW_RADIUS; }
#viewerInfo[winMaximized="true"] { border-bottom-left-radius: 0px;
                                   border-bottom-right-radius: 0px; }
#viewerInfo QLabel { color: #D8D8DE; font-size: 12px; }
"""


def apply_constants(qss: str) -> str:
    """把 $XXX 占位符替换为常量。"""
    consts = {
        "$BG": BG, "$SIDEBAR_BG": SIDEBAR_BG, "$CARD_BG": CARD_BG,
        "$TEXT": TEXT, "$TEXT_SECONDARY": TEXT_SECONDARY,
        "$SEPARATOR": SEPARATOR, "$HOVER_BG": HOVER_BG,
        "$SELECT_BG": SELECT_BG, "$ACCENT": ACCENT, "$ACCENT_HOVER": ACCENT_HOVER,
        "$RED": RED, "$RED_HOVER": RED_HOVER, "$GREEN": GREEN, "$YELLOW": YELLOW,
        "$CLOSE_RED": CLOSE_RED, "$MIN_YELLOW": MIN_YELLOW, "$MAX_GREEN": MAX_GREEN,
        "$VIEWER_BG": VIEWER_BG, "$WINDOW_RADIUS": WINDOW_RADIUS,
    }
    for k in sorted(consts, key=len, reverse=True):  # 先替换长键，避免 $TEXT 吞掉 $TEXT_SECONDARY
        qss = qss.replace(k, consts[k])
    return qss


def user_color(i: int) -> str:
    return USER_COLORS[i % len(USER_COLORS)]
