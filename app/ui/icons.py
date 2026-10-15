"""SVG 图标加载与着色（Element 风格线性/实心图标，来自 Font Awesome Free）。

用法：icon("map", color="#1D1D1F", size=16) -> QIcon
"""
import re
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ICON_DIR = Path(__file__).resolve().parent / "icons"

# 名称 → 文件名（部分图标只有 solid 版）
_ALIAS = {
    "refresh": "rotate-right",
    "zoom-out": "compress",
    "zoom-in": "expand",
    "location": "location-dot",
    "gps": "location-dot",
    "nogps": "ban",
    "search": "magnifying-glass",
    "favorite": "heart",
    "delete": "trash-can",
    "close": "xmark",
    "minimize": "minus",
    "maximize": "expand",
    "add-folder": "folder-plus",
}


def _resolve(name: str) -> Path:
    name = _ALIAS.get(name, name)
    f = ICON_DIR / f"{name}.svg"
    if not f.exists() and name not in ("ban",):
        raise FileNotFoundError(f"缺少图标: {name}")
    return f


@lru_cache(maxsize=512)
def _pixmap(name: str, color: str, size: int) -> QPixmap:
    f = _resolve(name)
    svg = f.read_text(encoding="utf-8")
    # 给所有 path 注入颜色
    svg = re.sub(r'fill="[^"]*"', f'fill="{color}"', svg)
    svg = re.sub(r"<path(?![^>]*\bfill=)",
                 lambda m: f'<path fill="{color}"', svg)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p)
    p.end()
    return pm


def icon(name: str, color: str = "#1D1D1F", size: int = 16) -> QIcon:
    try:
        return QIcon(_pixmap(name, color, size))
    except Exception:
        return QIcon()
