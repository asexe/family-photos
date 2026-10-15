"""时间轴照片墙（苹果相册风格）：

- 按「年月」分组，组间显示分割线标题（如 2018年8月，无拍摄时间单独一组）；
- 右侧刻度尺：年份标签 + 月份刻度线（没有照片的年份/月份自动省略）；
- 点击/拖动刻度尺可跳转滚动；滚轮平滑滚动；
- 虚拟化绘制：只画可见区域，数千张照片不卡顿。
"""
import math
from pathlib import Path

from PySide6.QtCore import (QEasingCurve, QPoint, QPointF, QRect, QRectF, QSize,
                            Qt, QPropertyAnimation, Signal)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPolygonF
from PySide6.QtWidgets import QAbstractScrollArea

from .models import load_thumb_pixmap

MARGIN = 12
CARD_W = 206
CARD_H = 182
GAP = 10
HEADER_H = 40
RULER_W = 48
THUMB_RADIUS = 10
CARD_RADIUS = 12

PAGE_BG = QColor("#FFFFFF")
HEADER_TEXT = QColor("#1D1D1F")
HAIRLINE = QColor("#E5E5EA")
CARD_HOVER = QColor("#F2F2F7")
CARD_SELECT = QColor("#E0EDFF")
DATE_TEXT = QColor("#6E6E73")
RULER_BG = QColor("#FAFAFC")
RULER_YEAR = QColor("#1D1D1F")
RULER_MONTH = QColor("#86868B")
ACCENT = QColor("#007AFF")


class TimelineWall(QAbstractScrollArea):
    photo_activated = Signal(int)                    # 双击照片（photo_id）
    photo_menu_requested = Signal(int, QPoint)       # 右键（photo_id, 全局坐标）

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QAbstractScrollArea.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._photos = []
        self._sections = []      # [{title, year, month, photos:[...]}]
        self._rows = []          # 布局后的条目（含 rect）
        self._sec_pos = {}       # 段 id -> 标题 y
        self._doc_h = 0
        self._selected = set()
        self._hover_id = None
        self._ruler_detail = 2        # 1=仅年份 2=年份+月份
        self._ruler_rows = []         # [(kind, text, sec_idx)]
        self._ruler_hit = []          # [(QRect, sec_idx)]
        self._ruler_btn_rect = QRect()
        self._scroll_anim = None
        self.viewport().setMouseTracking(True)

    # ==================================================================
    # 数据与布局
    # ==================================================================
    def set_photos(self, photos: list):
        self._photos = list(photos)
        self._selected.clear()
        self._build_sections()
        self.relayout()
        self.verticalScrollBar().setValue(0)
        self.viewport().update()

    def _build_sections(self):
        self._sections = []
        cur = None
        for p in self._photos:
            t = p.get("taken_at") or ""
            if len(t) >= 7:
                year, month = t[:4], int(t[5:7])
                title = f"{year}年{month}月"
            else:
                year, month, title = None, None, "无拍摄时间"
            if cur is None or cur["title"] != title:
                cur = {"title": title, "year": year, "month": month, "photos": []}
                self._sections.append(cur)
            cur["photos"].append(p)

    def relayout(self):
        self._rows = []
        self._sec_pos = {}
        vw = max(200, self.viewport().width())
        avail = vw - RULER_W - MARGIN * 2
        cols = max(1, (avail + GAP) // (CARD_W + GAP))
        y = 10
        for si, sec in enumerate(self._sections):
            y += HEADER_H
            self._sec_pos[si] = y - HEADER_H
            n = len(sec["photos"])
            for i, p in enumerate(sec["photos"]):
                col, row = i % cols, i // cols
                x = MARGIN + col * (CARD_W + GAP)
                yy = y + row * (CARD_H + GAP)
                self._rows.append({"photo": p, "rect": QRect(x, yy, CARD_W, CARD_H)})
            y += math.ceil(n / cols) * (CARD_H + GAP) + 14
        self._doc_h = y + 20
        self._build_ruler_index()
        sb = self.verticalScrollBar()
        sb.setRange(0, max(0, self._doc_h - self.viewport().height()))
        sb.setPageStep(self.viewport().height())
        self.viewport().update()

    def _build_ruler_index(self):
        """紧凑时间索引：所有年份与所有有照片的月份，可点击跳转。"""
        rows = []
        seen_years = {}
        for si, sec in enumerate(self._sections):
            if sec["year"]:
                if sec["year"] not in seen_years:
                    seen_years[sec["year"]] = si
                    rows.append(("year", str(sec["year"]), si))
                if self._ruler_detail >= 2:
                    rows.append(("month", f"{sec['month']}月", si))
            else:
                rows.append(("year", "未知", si))
        self._ruler_rows = rows

    def _active_section(self) -> int:
        """当前视口顶部所在的月份段。"""
        top = self.verticalScrollBar().value()
        active = None
        for si in range(len(self._sections)):
            if self._sec_pos[si] <= top + 12:
                active = si
            else:
                break
        return active if active is not None else (0 if self._sections else None)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.relayout()

    def scrollContentsBy(self, dx, dy):
        self.viewport().update()

    # ==================================================================
    # 绘制
    # ==================================================================
    def paintEvent(self, e):
        p = QPainter(self.viewport())
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        vw = self.viewport().width()
        vh = self.viewport().height()
        p.fillRect(0, 0, vw, vh, PAGE_BG)
        if not self._sections:
            return

        top = self.verticalScrollBar().value()
        bottom = top + vh
        p.save()
        p.translate(0, -top)
        # 分割线标题
        for si, sec in enumerate(self._sections):
            hy = self._sec_pos[si]
            if hy + HEADER_H < top or hy > bottom:
                continue
            self._draw_header(p, sec["title"], hy, vw)
        # 照片卡片
        for row in self._rows:
            r = row["rect"]
            if r.bottom() < top or r.top() > bottom:
                continue
            self._draw_card(p, row["photo"], r)
        p.restore()
        self._draw_ruler(p, vw, vh, top, bottom)

    def _draw_header(self, p: QPainter, title: str, y: int, vw: int):
        p.setPen(HEADER_TEXT)
        f = p.font()
        f.setPointSizeF(10.5)
        f.setBold(True)
        p.setFont(f)
        text_x = MARGIN
        p.drawText(QRect(text_x, y, 260, HEADER_H),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, title)
        tw = p.fontMetrics().horizontalAdvance(title)
        line_y = y + HEADER_H // 2
        p.setPen(HAIRLINE)
        p.drawLine(text_x + tw + 14, line_y, vw - RULER_W - 10, line_y)

    def _draw_card(self, p: QPainter, photo: dict, r: QRect):
        pid = photo["id"]
        hovered = self._hover_id == pid
        selected = pid in self._selected
        bg = CARD_SELECT if selected else (CARD_HOVER if hovered else QColor(0, 0, 0, 0))
        if bg.alpha() > 0:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(QRectF(r), CARD_RADIUS, CARD_RADIUS)
        if selected:
            pen = p.pen()
            pen.setColor(ACCENT)
            pen.setWidth(2)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(r).adjusted(1, 1, -1, -1), CARD_RADIUS, CARD_RADIUS)
        # 缩略图
        text_h = 26
        thumb_area = QRect(r.left() + 4, r.top() + 4, r.width() - 8, r.height() - text_h - 4)
        pm = load_thumb_pixmap(photo, thumb_area.size())
        scaled = pm.scaled(thumb_area.size(), Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
        x = thumb_area.center().x() - scaled.width() // 2
        y = thumb_area.center().y() - scaled.height() // 2
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(x, y, scaled.width(), scaled.height()),
                            THUMB_RADIUS, THUMB_RADIUS)
        p.save()
        p.setClipPath(clip)
        p.drawPixmap(x, y, scaled)
        p.restore()
        # 日期
        p.setPen(DATE_TEXT)
        f = p.font()
        f.setPointSizeF(9.5)
        p.setFont(f)
        t = photo.get("taken_at") or ""
        label = t[:10] if len(t) >= 10 else (photo.get("filename") or "")
        text_rect = QRect(r.left(), r.top() + r.height() - text_h, r.width(), text_h - 2)
        p.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                   p.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight,
                                              text_rect.width()))
        # 视频角标（▶ 播放符号）
        if photo.get("duration") is not None:
            c = thumb_area.center()
            rad = 17
            p.setBrush(QColor(0, 0, 0, 120))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(c, rad, rad)
            tri = QPolygonF([
                QPointF(c.x() - 4.5, c.y() - 8),
                QPointF(c.x() - 4.5, c.y() + 8),
                QPointF(c.x() + 9.5, c.y()),
            ])
            p.setBrush(QColor(255, 255, 255, 230))
            p.drawPolygon(tri)

    def _draw_ruler(self, p: QPainter, vw: int, vh: int, top: int, bottom: int):
        x0 = vw - RULER_W
        p.fillRect(x0, 0, RULER_W, vh, RULER_BG)
        p.setPen(HAIRLINE)
        p.drawLine(x0, 0, x0, vh)

        # 顶部缩放模式按钮：年 / 年+月
        btn_h = 24
        self._ruler_btn_rect = QRect(x0, 0, RULER_W, btn_h)
        half = RULER_W // 2
        for i, (label, mode) in enumerate((("年", 1), ("月", 2))):
            r = QRect(x0 + i * half, 0, half, btn_h - 1)
            active = self._ruler_detail == mode
            if active:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#E8E8ED"))
                p.drawRoundedRect(QRectF(r).adjusted(3, 4, -3, -4), 6, 6)
            p.setPen(RULER_YEAR if active else RULER_MONTH)
            f = p.font()
            f.setPointSizeF(8)
            f.setBold(active)
            p.setFont(f)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, label)
        p.setPen(HAIRLINE)
        p.drawLine(x0, btn_h, vw, btn_h)

        # 紧凑时间索引（全部年份+月份，压缩到可视高度）
        rows = self._ruler_rows
        self._ruler_hit = []
        if not rows:
            return
        active = self._active_section()
        active_year = None
        if active is not None:
            active_year = self._sections[active].get("year")
        area_h = max(30, vh - btn_h - 8)
        row_h = min(16, max(9, area_h // len(rows)))
        y = btn_h + 4
        for kind, text, si in rows:
            rect = QRect(x0 + 2, int(y), RULER_W - 6, int(row_h + 1))
            self._ruler_hit.append((rect, si))
            # 当前所在月份/年份 → 高亮胶囊
            is_active = (si == active) or (kind == "year" and active_year is not None
                                          and text == str(active_year) and si <= (active or 0))
            if is_active:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#DCEBFF"))
                p.drawRoundedRect(QRectF(rect).adjusted(0, 1, 0, -1), 7, 7)
            if kind == "year":
                p.setPen(QColor("#007AFF") if is_active else RULER_YEAR)
                f = p.font()
                f.setPointSizeF(8.5)
                f.setBold(True)
                p.setFont(f)
                p.drawText(QRect(x0 + 4, int(y), RULER_W - 8, int(row_h)),
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
            else:
                if is_active:
                    p.setPen(QColor("#007AFF"))
                    p.drawLine(x0 + 5, int(y + row_h / 2), x0 + 11, int(y + row_h / 2))
                else:
                    p.setPen(RULER_MONTH)
                    p.drawLine(x0 + 5, int(y + row_h / 2), x0 + 11, int(y + row_h / 2))
                f = p.font()
                f.setPointSizeF(7.5)
                f.setBold(is_active)
                p.setFont(f)
                p.setPen(QColor("#007AFF") if is_active else RULER_MONTH)
                p.drawText(QRect(x0 + 14, int(y), RULER_W - 18, int(row_h)),
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
            y += row_h

    # ==================================================================
    # 交互
    # ==================================================================
    def _hit_photo(self, pos: QPoint):
        for row in self._rows:
            if row["rect"].contains(pos):
                return row["photo"]
        return None

    def mousePressEvent(self, e):
        pos = e.position().toPoint()
        vw = self.viewport().width()
        if pos.x() >= vw - RULER_W:
            if e.button() == Qt.MouseButton.LeftButton:
                if self._ruler_btn_rect.contains(pos):
                    # 缩放模式：左半=仅年份，右半=年份+月份
                    half = self._ruler_btn_rect.width() // 2
                    mode = 1 if pos.x() < self._ruler_btn_rect.left() + half else 2
                    if mode != self._ruler_detail:
                        self._ruler_detail = mode
                        self._build_ruler_index()
                        self.viewport().update()
                else:
                    # 点击年份/月份索引跳转
                    for rect, si in self._ruler_hit:
                        if rect.contains(pos):
                            bar = self.verticalScrollBar()
                            bar.setValue(min(bar.maximum(), max(0, self._sec_pos[si] - 8)))
                            break
            return
        if e.button() == Qt.MouseButton.LeftButton:
            photo = self._hit_photo(pos)
            if photo:
                if not (e.modifiers() & Qt.KeyboardModifier.ControlModifier):
                    self._selected.clear()
                if photo["id"] in self._selected:
                    self._selected.discard(photo["id"])
                else:
                    self._selected.add(photo["id"])
                self.viewport().update()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        photo = self._hit_photo(pos)
        new_hover = photo["id"] if photo else None
        if new_hover != self._hover_id:
            self._hover_id = new_hover
            self.viewport().update()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)

    def leaveEvent(self, e):
        self._hover_id = None
        self.viewport().update()
        super().leaveEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            photo = self._hit_photo(e.position().toPoint())
            if photo:
                self.photo_activated.emit(photo["id"])
                return
        super().mouseDoubleClickEvent(e)

    def contextMenuEvent(self, e):
        photo = self._hit_photo(e.pos())
        if photo:
            self.photo_menu_requested.emit(photo["id"], e.globalPos())
            e.accept()
        else:
            super().contextMenuEvent(e)

    # ==================================================================
    # 滚轮平滑滚动
    # ==================================================================
    def wheelEvent(self, e):
        bar = self.verticalScrollBar()
        delta = e.angleDelta().y()
        if delta == 0:
            e.accept()
            return
        target = bar.value() - int(delta * 1.6)
        target = max(bar.minimum(), min(bar.maximum(), target))
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
        e.accept()
