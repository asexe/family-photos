"""日历视图：月历格子显示每天的照片数量与封面缩略图，点击某天筛选。

自绘实现（性能好、样式统一）：格子内铺封面缩略图 + 日期数字 + 数量徽章。
"""
import calendar as _cal
import datetime as dt
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from .icons import icon as make_icon

WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]
HEADER_H = 26
GAP = 4
RADIUS = 10


class CalendarGrid(QWidget):
    """自绘月历网格。"""

    day_clicked = Signal(str)          # "2024-10-05"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(420)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self._year = dt.date.today().year
        self._month = dt.date.today().month
        self._counts = {}              # {"2024-10-05": 12}
        self._covers = {}              # {"2024-10-05": QPixmap}
        self._rects = {}               # {"2024-10-05": QRect}
        self._hover = None

    # ---------- 数据 ----------
    def set_month(self, year: int, month: int):
        self._year, self._month = year, month
        self.update()

    def set_data(self, counts: dict, covers: dict):
        self._counts = counts
        self._covers = covers
        self.update()

    @property
    def year(self):
        return self._year

    @property
    def month(self):
        return self._month

    # ---------- 绘制 ----------
    def _cell_rects(self):
        w = self.width()
        h = self.height() - HEADER_H
        cw = w / 7.0
        ch = h / 6.0
        first_weekday, days_in_month = _cal.monthrange(self._year, self._month)
        rects = {}
        for day in range(1, days_in_month + 1):
            idx = first_weekday + day - 1          # 0 = 周一
            col = idx % 7
            row = idx // 7
            x = col * cw + GAP / 2
            y = HEADER_H + row * ch + GAP / 2
            rects[f"{self._year:04d}-{self._month:02d}-{day:02d}"] = QRect(
                int(x), int(y), int(cw - GAP), int(ch - GAP))
        return rects

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor("#FFFFFF"))

        # 星期表头
        f = p.font()
        f.setPointSizeF(9.5)
        f.setBold(False)
        p.setFont(f)
        p.setPen(QColor("#86868B"))
        cw = self.width() / 7.0
        for i, name in enumerate(WEEKDAYS):
            p.drawText(QRect(int(i * cw), 0, int(cw), HEADER_H),
                       Qt.AlignmentFlag.AlignCenter, name)

        self._rects = self._cell_rects()
        today = dt.date.today().isoformat()
        for day_str, rect in self._rects.items():
            count = self._counts.get(day_str, 0)
            cover = self._covers.get(day_str)
            hovered = self._hover == day_str
            # 背景
            if cover is not None:
                path = QPainterPath()
                path.addRoundedRect(QRectF(rect), RADIUS, RADIUS)
                p.save()
                p.setClipPath(path)
                scaled = cover.scaled(rect.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                      Qt.TransformationMode.SmoothTransformation)
                p.drawPixmap(rect.left() + (rect.width() - scaled.width()) // 2,
                             rect.top() + (rect.height() - scaled.height()) // 2, scaled)
                # 底部渐隐，保证数字可读
                grad = QColor(0, 0, 0, 120)
                p.fillRect(QRect(rect.left(), rect.top(), rect.width(), rect.height()), 
                           QColor(0, 0, 0, 40))
                p.restore()
                p.setPen(QColor("#FFFFFF"))
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#F2F2F7") if not hovered else QColor("#E8E8ED"))
                p.drawRoundedRect(QRectF(rect), RADIUS, RADIUS)
                p.setPen(QColor("#C7C7CC"))
            # 日期数字
            f = p.font()
            f.setPointSizeF(10.5)
            f.setBold(count > 0)
            p.setFont(f)
            p.drawText(rect.adjusted(8, 5, -6, -6),
                       Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                       str(int(day_str[-2:])))
            # 数量徽章
            if count:
                badge = f"{count}"
                bw = max(18, 8 + 7 * len(badge))
                br = QRect(rect.right() - bw - 6, rect.bottom() - 22, bw, 16)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(0, 122, 255, 235))
                p.drawRoundedRect(QRectF(br), 8, 8)
                f.setPointSizeF(8.5)
                f.setBold(True)
                p.setFont(f)
                p.setPen(QColor("#FFFFFF"))
                p.drawText(br, Qt.AlignmentFlag.AlignCenter, badge)
            # 今天描边
            if day_str == today:
                pen = p.pen()
                pen.setColor(QColor("#007AFF"))
                pen.setWidth(2)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(QRectF(rect).adjusted(1, 1, -1, -1), RADIUS, RADIUS)

    # ---------- 交互 ----------
    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        hit = None
        for day_str, rect in self._rects.items():
            if rect.contains(pos):
                hit = day_str
                break
        if hit != self._hover:
            self._hover = hit
            self.update()
        self.setCursor(Qt.CursorShape.PointingHandCursor if hit else Qt.CursorShape.ArrowCursor)

    def leaveEvent(self, _e):
        self._hover = None
        self.update()

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        pos = e.position().toPoint()
        for day_str, rect in self._rects.items():
            if rect.contains(pos) and self._counts.get(day_str):
                self.day_clicked.emit(day_str)
                return


class CalendarPage(QWidget):
    """日历页：月份导航 + 月历网格。"""

    day_selected = Signal(str)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        today = dt.date.today()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        bar = QHBoxLayout()
        self.btn_prev = QPushButton()
        self.btn_prev.setObjectName("ghost")
        self.btn_prev.setIcon(make_icon("arrow-rotate-right", "#1D1D1F", 14))
        self.btn_prev.setFixedWidth(40)
        self.btn_prev.setToolTip("上个月")
        self.month_label = QLabel("")
        self.month_label.setStyleSheet("font-size: 16px; font-weight: 700;")
        self.month_label.setFixedWidth(140)
        self.btn_next = QPushButton()
        self.btn_next.setObjectName("ghost")
        self.btn_next.setIcon(make_icon("arrow-rotate-right", "#1D1D1F", 14))
        self.btn_next.setFixedWidth(40)
        self.btn_next.setToolTip("下个月")
        btn_today = QPushButton("今天")
        btn_today.setObjectName("ghost")
        btn_today.clicked.connect(self._goto_today)
        self.summary = QLabel("")
        self.summary.setStyleSheet("color: #86868B;")

        bar.addWidget(self.btn_prev)
        bar.addWidget(self.month_label)
        bar.addWidget(self.btn_next)
        bar.addSpacing(8)
        bar.addWidget(btn_today)
        bar.addStretch(1)
        bar.addWidget(self.summary)
        lay.addLayout(bar)

        self.grid = CalendarGrid()
        self.grid.day_clicked.connect(self.day_selected)
        lay.addWidget(self.grid, 1)

        self.btn_prev.clicked.connect(lambda: self._shift(-1))
        self.btn_next.clicked.connect(lambda: self._shift(1))
        self._year, self._month = today.year, today.month
        self.reload()

    def _shift(self, delta: int):
        m = self._month + delta
        y = self._year
        while m < 1:
            m += 12
            y -= 1
        while m > 12:
            m -= 12
            y += 1
        self._year, self._month = y, m
        self.reload()

    def _goto_today(self):
        today = dt.date.today()
        self._year, self._month = today.year, today.month
        self.reload()

    def reload(self):
        """按当前月份从数据库取每天数量与封面。"""
        prefix = f"{self._year:04d}-{self._month:02d}"
        counts = {d["day"]: d["n"] for d in self.db.days_with_counts()
                  if d["day"].startswith(prefix)}
        covers = {}
        reps = self.db.first_photo_of_days(list(counts))
        for day, info in reps.items():
            thumb = info.get("thumb_path")
            if thumb and Path(thumb).exists():
                pm = QPixmap(thumb)
                if not pm.isNull():
                    covers[day] = pm
        self.month_label.setText(f"{self._year}年{self._month}月")
        self.summary.setText(f"本月 {sum(counts.values())} 张 · 有照片 {len(counts)} 天")
        self.grid.set_month(self._year, self._month)
        self.grid.set_data(counts, covers)
