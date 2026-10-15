"""缩略图墙委托：自绘缩略图（圆角）+ 日期文字，布局互不重叠。

替代默认 IconMode 绘制，规避图标与文字重叠问题。
"""
from PySide6.QtCore import QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from .models import load_thumb_pixmap

PAD = 4          # 网格间距的一半
TEXT_H = 24      # 底部日期文字高度
RADIUS = 12      # 卡片背景圆角
THUMB_RADIUS = 10


class PhotoDelegate(QStyledItemDelegate):
    """单元格布局：[圆角缩略图（按比例居中）] + [日期文字]"""

    def paint(self, painter: QPainter, option, index):
        p = index.data(Qt.ItemDataRole.UserRole)
        if not p:
            return
        rect = option.rect.adjusted(PAD, PAD, -PAD, -PAD)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ---- 悬停 / 选中背景 ----
        state = option.state
        if state & QStyle.StateFlag.State_Selected:
            bg = QColor("#E0EDFF")
        elif state & QStyle.StateFlag.State_MouseOver:
            bg = QColor("#F2F2F7")
        else:
            bg = QColor(0, 0, 0, 0)
        if bg.alpha() > 0:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(rect, RADIUS, RADIUS)

        # ---- 缩略图（顶部区域，按比例居中，圆角裁剪） ----
        thumb_area = QRect(rect.left(), rect.top(), rect.width(), rect.height() - TEXT_H)
        pm = load_thumb_pixmap(p, thumb_area.size())
        scaled = pm.scaled(thumb_area.size(),
                           Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
        x = thumb_area.left() + (thumb_area.width() - scaled.width()) // 2
        y = thumb_area.top() + (thumb_area.height() - scaled.height()) // 2
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(x, y, scaled.width(), scaled.height()),
                            THUMB_RADIUS, THUMB_RADIUS)
        painter.setClipPath(clip)
        painter.drawPixmap(x, y, scaled)
        painter.restore()

        # ---- 日期文字（底部，与图片不重叠） ----
        painter.save()
        f = painter.font()
        f.setPointSizeF(9.5)
        painter.setFont(f)
        painter.setPen(QColor("#6E6E73"))
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        text_rect = QRect(rect.left(), thumb_area.bottom() + 2,
                          rect.width(), TEXT_H - 2)
        painter.drawText(text_rect,
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                         painter.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight,
                                                          text_rect.width()))
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(234, 226)
