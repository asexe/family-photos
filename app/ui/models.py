"""缩略图墙数据模型：懒加载缩略图（QPixmapCache），虚拟滚动。"""
from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, QSize
from PySide6.QtGui import QColor, QIcon, QPixmap, QPixmapCache

THUMB_KEY_PREFIX = "pm_thumb_"


def display_text(p: dict) -> str:
    """缩略图下方的说明文字：拍摄日期优先，其次文件名。"""
    t = p.get("taken_at") or ""
    if t and len(t) >= 10:
        return t[:10]
    return p.get("filename") or ""


def load_thumb_pixmap(p: dict, size: QSize) -> QPixmap:
    """按需加载缩略图（带缓存）；失败返回灰色占位图。"""
    key = THUMB_KEY_PREFIX + str(p["id"])
    pm = QPixmapCache.find(key)
    if pm and not pm.isNull():
        return pm
    path = p.get("thumb_path")
    if path:
        pm = QPixmap(path)
    else:
        pm = QPixmap()
    if pm.isNull():
        pm = QPixmap(size)
        pm.fill(QColor("#E8E8ED"))
    QPixmapCache.insert(key, pm)
    return pm


class PhotoListModel(QAbstractListModel):
    """照片列表模型。photos: list[dict]，每项含 id/thumb_path/taken_at 等。"""

    def __init__(self, photos=None, parent=None):
        super().__init__(parent)
        self.photos = list(photos or [])

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.photos)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self.photos)):
            return None
        p = self.photos[index.row()]
        if role == Qt.ItemDataRole.DecorationRole:
            return QIcon(load_thumb_pixmap(p, QSize(220, 160)))
        if role == Qt.ItemDataRole.DisplayRole:
            return display_text(p)
        if role == Qt.ItemDataRole.ToolTipRole:
            t = p.get("taken_at") or "拍摄时间未知"
            gps = f"📍 {p['lat']:.5f}, {p['lng']:.5f}" if p.get("lat") else "无定位"
            return f"{p['filename']}\n{t}\n{gps}\n归属：{p.get('user_name', '未知')}"
        if role == Qt.ItemDataRole.UserRole:
            return p
        return None

    def set_photos(self, photos: list):
        self.beginResetModel()
        self.photos = list(photos)
        self.endResetModel()

    def photo_at(self, row: int):
        if 0 <= row < len(self.photos):
            return self.photos[row]
        return None

    def remove_at(self, row: int):
        self.beginRemoveRows(QModelIndex(), row, row)
        self.photos.pop(row)
        self.endRemoveRows()
