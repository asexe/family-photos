"""UI 基础组件：

- FramelessWindow / AppleDialog：圆角半透明窗口（setMask 蒙版保证真圆角），
  Windows 11 下尝试 Mica 背景；
- TitleBar：右上角控制键（缩小黄 / 放大绿 / 关闭红）；
- AnimatedComboBox：弹出选项卡淡入动画 + 圆角；
- PhotoListView：缩略图墙，滚轮平滑滚动动画；
- color_icon：用户色圆点图标。
"""
import os
import sys
from PySide6.QtGui import (QColor, QIcon, QMouseEvent, QPainter, QPainterPath,
                           QPen, QPixmap, QPolygonF, QRegion)
from PySide6.QtCore import (QEasingCurve, QEvent, QObject, QPoint, QPointF,
                            QRectF, QSize, QThread, Qt, Signal,
                            QPropertyAnimation, QAbstractAnimation)
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QFrame,
                               QGraphicsOpacityEffect, QHBoxLayout, QLabel,
                               QListView, QMainWindow, QPushButton, QWidget)

from .icons import icon as make_icon

EDGE_MARGIN = 6      # 边缘调整大小热区（像素）
WINDOW_RADIUS = 16   # 窗口圆角半径（与 style.WINDOW_RADIUS 保持一致）

# PM_OPAQUE=1 时关闭半透明/蒙版（排查 WebEngine 渲染问题用；Win11 原生圆角仍生效）
TRANSLUCENT_WINDOWS = os.environ.get("PM_OPAQUE") != "1"


def try_apply_backdrop(hwnd: int):
    """Windows 11 22H2+：开启 Mica 背景（38 为 DWMWA_SYSTEMBACKDROP_TYPE，2 为 Mica）。
    旧系统或无权限时静默失败，窗口仍保持半透明圆角。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        DWMWA_SYSTEMBACKDROP_TYPE = 38
        DWMSBT_MAINWINDOW = 2
        value = ctypes.c_int(DWMSBT_MAINWINDOW)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd), DWMWA_SYSTEMBACKDROP_TYPE,
            ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass


def rounded_mask_region(size: QSize, radius: int) -> QRegion:
    """按尺寸生成圆角矩形区域（用于窗口蒙版）。"""
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size.width(), size.height()), radius, radius)
    return QRegion(path.toFillPolygon().toPolygon())


def color_icon(color: str, size: int = 12) -> QIcon:
    """纯色圆点图标（家人列表用）。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(0, 0, size, size)
    p.end()
    return QIcon(pm)


class ScanThread(QThread):
    """后台扫描线程：进度 / 完成 / 失败信号。"""
    progress = Signal(int, int, int, int)   # done, total, new, dup
    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, scanner, folder_ids, parent=None, clean_missing: bool = False):
        super().__init__(parent)
        self._scanner = scanner
        self._ids = list(folder_ids)
        self._clean_missing = clean_missing

    def run(self):
        result = {}
        try:
            for fid in self._ids:
                result = self._scanner.scan_folder(
                    fid, on_progress=lambda d, t, n, p: self.progress.emit(d, t, n, p),
                    clean_missing=self._clean_missing)
                if result.get("cancelled"):
                    break
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))
            return
        self.finished_ok.emit(result)


class TitleBar(QFrame):
    """标题栏：左侧标题，右上角 [缩小(黄)][放大(绿)][关闭(红)]。

    按住空白处可拖动窗口，双击切换最大化。
    """

    def __init__(self, window: QMainWindow, title: str = "家庭相册", parent=None):
        super().__init__(parent)
        self.setObjectName("titleBar")
        self.setFixedHeight(44)
        self._win = window
        self._drag_offset: QPoint | None = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(8)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("appTitle")
        lay.addWidget(self.title_label)
        lay.addStretch(1)

        # 右上角控制键：缩小（黄）→ 放大（绿）→ 关闭（红），带符号图标
        self.btn_min = QPushButton()
        self.btn_min.setObjectName("trafficMin")
        self.btn_min.setProperty("class", "traffic")
        self.btn_min.setIcon(make_icon("minimize", "#7A5E0F", 10))
        self.btn_min.setIconSize(QSize(10, 10))
        self.btn_min.setToolTip("缩小")
        self.btn_max = QPushButton()
        self.btn_max.setObjectName("trafficMax")
        self.btn_max.setProperty("class", "traffic")
        self.btn_max.setIcon(make_icon("maximize", "#0E5C16", 9))
        self.btn_max.setIconSize(QSize(9, 9))
        self.btn_max.setToolTip("放大 / 还原")
        self.btn_close = QPushButton()
        self.btn_close.setObjectName("trafficClose")
        self.btn_close.setProperty("class", "traffic")
        self.btn_close.setIcon(make_icon("close", "#FFFFFF", 10))
        self.btn_close.setIconSize(QSize(10, 10))
        self.btn_close.setToolTip("关闭")
        for b in (self.btn_min, self.btn_max, self.btn_close):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            lay.addWidget(b)

        self.btn_min.clicked.connect(window.showMinimized)
        self.btn_max.clicked.connect(self._toggle_max)
        self.btn_close.clicked.connect(window.close)

    def _toggle_max(self):
        if self._win.isMaximized():
            self._win.showNormal()
        else:
            self._win.showMaximized()

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (e.globalPosition().toPoint()
                                 - self._win.frameGeometry().topLeft())
            e.accept()

    def mouseMoveEvent(self, e: QMouseEvent):
        if self._drag_offset is not None and e.buttons() & Qt.MouseButton.LeftButton:
            if self._win.isMaximized():
                return
            self._win.move(e.globalPosition().toPoint() - self._drag_offset)
            e.accept()

    def mouseReleaseEvent(self, e: QMouseEvent):
        self._drag_offset = None
        e.accept()

    def mouseDoubleClickEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton:
            self._toggle_max()
            e.accept()


class FramelessWindow(QMainWindow):
    """无边框、真圆角（蒙版）、半透明、可拖动、可边缘缩放的窗口基类。"""

    def __init__(self, min_size: QSize = QSize(880, 560), parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        if TRANSLUCENT_WINDOWS:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._min_size = min_size
        self._edge = None
        self._resize_started = False
        self._backdrop_tried = False
        self._maximized_state = False
        self._extra_corners = []

    def register_corner(self, widget):
        """注册需要跟随最大化状态切换圆角的部件（标题栏/状态栏之外）。"""
        self._extra_corners.append(widget)

    # ---- 真圆角：窗口蒙版 ----
    def _apply_round_mask(self):
        if not TRANSLUCENT_WINDOWS:
            self.clearMask()
            return
        if self.isMaximized() or self.isFullScreen():
            self.clearMask()
        else:
            self.setMask(rounded_mask_region(self.size(), WINDOW_RADIUS))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply_round_mask()

    def showEvent(self, e):
        super().showEvent(e)
        self._apply_round_mask()
        if not self._backdrop_tried:
            self._backdrop_tried = True
            try_apply_backdrop(int(self.winId()))

    def changeEvent(self, e):
        if e.type() == QEvent.Type.WindowStateChange:
            maximized = self.isMaximized()
            if maximized != self._maximized_state:
                self._maximized_state = maximized
                self._apply_round_mask()
                for w in [self, self.menuWidget(), self.statusBar()] + self._extra_corners:
                    if w is not None:
                        w.setProperty("winMaximized", maximized)
                        w.style().unpolish(w)
                        w.style().polish(w)
        super().changeEvent(e)

    # ---- 边缘缩放（利用系统级 startSystemResize，Windows 原生手感） ----
    def _hit_edge(self, pos: QPoint):
        r = self.rect()
        if self.isMaximized():
            return None
        left = pos.x() <= EDGE_MARGIN
        right = pos.x() >= r.width() - EDGE_MARGIN
        top = pos.y() <= EDGE_MARGIN
        bottom = pos.y() >= r.height() - EDGE_MARGIN
        edges = None
        if top:
            edges = Qt.Edge.TopEdge
        elif bottom:
            edges = Qt.Edge.BottomEdge
        if left:
            edges = Qt.Edge.LeftEdge if edges is None else edges | Qt.Edge.LeftEdge
        elif right:
            edges = Qt.Edge.RightEdge if edges is None else edges | Qt.Edge.RightEdge
        return edges

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress,
                            QEvent.Type.MouseButtonRelease):
            gp = event.globalPosition().toPoint()
            local = self.mapFromGlobal(gp)
            edge = self._hit_edge(local)
            if event.type() == QEvent.Type.MouseMove and not (event.buttons() & Qt.MouseButton.LeftButton):
                if edge:
                    self._set_cursor(obj, edge)
                else:
                    obj.unsetCursor()
            elif event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                if edge and self.windowHandle() and not self._resize_started:
                    self._resize_started = True
                    self.windowHandle().startSystemResize(edge)
                    self._resize_started = False
                    return True
            elif event.type() == QEvent.Type.MouseButtonRelease:
                self._resize_started = False
        return super().eventFilter(obj, event)

    @staticmethod
    def _set_cursor(obj, edge):
        cur = {
            Qt.Edge.TopEdge: Qt.CursorShape.SizeVerCursor,
            Qt.Edge.BottomEdge: Qt.CursorShape.SizeVerCursor,
            Qt.Edge.LeftEdge: Qt.CursorShape.SizeHorCursor,
            Qt.Edge.RightEdge: Qt.CursorShape.SizeHorCursor,
            Qt.Edge.TopEdge | Qt.Edge.LeftEdge: Qt.CursorShape.SizeFDiagCursor,
            Qt.Edge.BottomEdge | Qt.Edge.RightEdge: Qt.CursorShape.SizeFDiagCursor,
            Qt.Edge.TopEdge | Qt.Edge.RightEdge: Qt.CursorShape.SizeBDiagCursor,
            Qt.Edge.BottomEdge | Qt.Edge.LeftEdge: Qt.CursorShape.SizeBDiagCursor,
        }.get(edge, Qt.CursorShape.ArrowCursor)
        obj.setCursor(cur)

    def install_edge_resize(self, widget: QWidget):
        widget.installEventFilter(self)


class AppleDialog(QDialog):
    """圆角对话框基类（不透明 + 圆角蒙版，任何系统下渲染稳定）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("appleDialog", True)

    def _apply_round_mask(self):
        self.setMask(rounded_mask_region(self.size(), WINDOW_RADIUS))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply_round_mask()

    def showEvent(self, e):
        super().showEvent(e)
        self._apply_round_mask()


class _RoundedMaskFilter(QObject):
    """跟随窗口尺寸动态更新圆角蒙版（弹层尺寸在显示后才确定）。"""

    def __init__(self, radius: int):
        super().__init__()
        self._radius = radius

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.Resize:
            obj.setMask(rounded_mask_region(obj.size(), self._radius))
        return False


class _PopupView(QListView):
    """下拉列表视图：强制白色圆角样式；弹层容器浅色底 + 圆角蒙版。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "QListView { background: #FFFFFF; color: #1D1D1F;"
            " border: 1px solid #E5E5EA; border-radius: 12px; padding: 4px;"
            " font-family: 'Segoe UI', 'Microsoft YaHei UI'; font-size: 13px; }"
            "QListView::item { border-radius: 8px; padding: 5px 8px; }"
            "QListView::item:hover { background: #F2F2F7; }"
            "QListView::item:selected { background: #007AFF; color: #FFFFFF; }")
        # 弹层至少留出 5 行的空间（用户少时也不会只显示一条）
        self.setMinimumHeight(5 * 30 + 10)
        self._mask_filter = None

    def showEvent(self, e):
        super().showEvent(e)
        w = self.window()
        if w is not self:
            # 弹层容器：不透明浅色底 + 去边框
            w.setStyleSheet("background: #F5F5F7;")
            if isinstance(w, QFrame):
                w.setFrameShape(QFrame.Shape.NoFrame)


class AnimatedComboBox(QComboBox):
    """白色圆角下拉框：完全自绘（不依赖样式引擎，半透明窗口下也不会变黑）。

    弹出选项卡为白色圆角 + 内容淡入动画。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setView(_PopupView())
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, e):
        """自绘：白底圆角 + 当前图标/文字 + 灰色箭头。"""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor("#D1D1D6"), 1))
        p.setBrush(QColor("#FFFFFF"))
        p.drawRoundedRect(rect, 10, 10)

        # 当前项图标（如有，如颜色圆点）
        icon = self.itemIcon(self.currentIndex())
        text_left = rect.left() + 12
        if icon and not icon.isNull():
            pm = icon.pixmap(12, 12)
            iy = int(rect.center().y() - pm.height() / 2)
            p.drawPixmap(int(text_left), iy, pm)
            text_left += pm.width() + 6

        # 文字（超长省略）
        p.setPen(QColor("#1D1D1F"))
        p.setFont(self.font())
        text_rect = QRectF(text_left, rect.top(), rect.right() - 28 - text_left,
                           rect.height())
        elided = p.fontMetrics().elidedText(self.currentText(),
                                            Qt.TextElideMode.ElideRight,
                                            int(text_rect.width()))
        p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   elided)

        # 下拉箭头
        cx = rect.right() - 16
        cy = rect.center().y()
        arrow = QPolygonF([QPointF(cx - 4, cy - 2.5), QPointF(cx + 4, cy - 2.5),
                           QPointF(cx, cy + 3.5)])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#86868B"))
        p.drawPolygon(arrow)
        p.end()

    def showPopup(self):
        # 直接以完整样式弹出（透明度特效在部分环境下会卡在半透明/半渲染，
        # 造成「样式只显示一半」的观感，故不使用）
        super().showPopup()
        try:
            # 强制弹层锚定在下拉框正下方（部分环境下 Qt 会把弹层盖在下拉框上）
            popup = self.view().window()
            g = self.mapToGlobal(QPoint(0, self.height()))
            screen = self.screen().availableGeometry() if self.screen() else None
            if screen is not None and g.y() + popup.height() > screen.bottom():
                g.setY(max(screen.top(),
                           self.mapToGlobal(QPoint(0, 0)).y() - popup.height()))
            popup.move(g)
        except Exception:
            pass


class PhotoListView(QListView):
    """缩略图墙：滚轮平滑滚动动画。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._scroll_anim = None

    def wheelEvent(self, e):
        bar = self.verticalScrollBar()
        delta = e.angleDelta().y()
        if delta == 0:
            e.accept()
            return
        target = bar.value() - int(delta * 1.6)
        target = max(bar.minimum(), min(bar.maximum(), target))
        self._animate_to(target)
        e.accept()

    def _animate_to(self, target: int):
        bar = self.verticalScrollBar()
        if self._scroll_anim is not None:
            self._scroll_anim.stop()
            self._scroll_anim.deleteLater()
            self._scroll_anim = None
        self._scroll_anim = QPropertyAnimation(bar, b"value", self)
        self._scroll_anim.setDuration(180)
        self._scroll_anim.setStartValue(bar.value())
        self._scroll_anim.setEndValue(target)
        self._scroll_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._scroll_anim.start()

    def stop_scroll_animation(self):
        if self._scroll_anim is not None:
            self._scroll_anim.stop()
            self._scroll_anim.deleteLater()
            self._scroll_anim = None
