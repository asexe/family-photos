"""大图浏览窗口（浏览窗口）：深色沉浸式，图片缩放/拖动/左右切换，视频内嵌播放。

与主窗口（缩略图小窗口）可同时打开。
"""
from PySide6.QtCore import Qt, QRectF, QSize, QUrl, Signal
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (QGraphicsPixmapItem, QGraphicsScene, QGraphicsView,
                               QHBoxLayout, QLabel, QPushButton, QSlider,
                               QStackedLayout, QVBoxLayout, QWidget)

from ..dedup import single_delete
from .icons import icon as make_icon
from .widgets import FramelessWindow, TitleBar


class PhotoGraphicsView(QGraphicsView):
    """支持滚轮缩放（以光标为中心）与拖动平移的图片视图。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHints(QPainter.RenderHint.SmoothPixmapTransform
                            | QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(Qt.GlobalColor.transparent)
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

    def set_image(self, pixmap: QPixmap):
        self._scene.clear()
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self.fit()

    def fit(self):
        if self._pixmap_item:
            self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, e):
        factor = 1.2 if e.angleDelta().y() > 0 else 1 / 1.2
        self.scale(factor, factor)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if self.window().isFullScreen():
                self.window().showNormal()
            else:
                self.window().showFullScreen()
            e.accept()


class ViewerWindow(FramelessWindow):
    changed = Signal()   # 删除/收藏后通知主窗口刷新

    def __init__(self, db, trash_dir, photos: list, index: int, parent=None):
        super().__init__(parent=parent)
        self.setProperty("viewerWindow", True)  # 深色半透明窗口样式
        self.setWindowTitle("浏览")
        self.db = db
        self.trash_dir = trash_dir
        self.photos = list(photos)
        self.index = max(0, min(index, len(self.photos) - 1)) if self.photos else -1

        # 标题栏（深色）
        self.title_bar = TitleBar(self, "浏览")
        self.title_bar.setProperty("dark", True)
        self.setMenuWidget(self.title_bar)
        self._tb = QWidget()
        self._tb.setObjectName("viewerToolbar")
        self._tb.setFixedHeight(44)
        lay = QHBoxLayout(self._tb)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(8)
        self.btn_close = self._mk("关闭", self.close, "close")
        self.btn_fit = self._mk("适配", self._fit, "compress")
        self.btn_actual = self._mk("1:1", self._actual, "expand")
        self.filename_label = QLabel("")
        self.filename_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_play = self._mk("播放", self._toggle_play, "play")
        self.btn_play.setVisible(False)
        self.btn_fav = self._mk("收藏", self._toggle_fav, "heart")
        self.btn_del = self._mk("删除", self._delete_current, "trash-can")
        lay.addWidget(self.btn_close)
        lay.addWidget(self.btn_fit)
        lay.addWidget(self.btn_actual)
        lay.addWidget(self.filename_label, 1)
        lay.addWidget(self.btn_play)
        lay.addWidget(self.btn_fav)
        lay.addWidget(self.btn_del)

        # 图片视图 + 视频视图（切换显示）
        self.view = PhotoGraphicsView()
        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet("background: #000000;")
        self.media_stack = QStackedLayout()
        self.media_stack.addWidget(self.view)
        self.media_stack.addWidget(self.video_widget)

        # 视频播放器
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video_widget)
        self.player.positionChanged.connect(self._on_player_pos)
        self.player.durationChanged.connect(self._on_player_dur)
        self.player.playbackStateChanged.connect(self._on_player_state)
        self.player.errorOccurred.connect(self._on_player_error)

        # 底部信息条（视频时显示进度条）
        self.info_bar = QWidget()
        self.info_bar.setObjectName("viewerInfo")
        self.info_bar.setFixedHeight(46)
        ilay = QHBoxLayout(self.info_bar)
        ilay.setContentsMargins(16, 0, 16, 0)
        ilay.setSpacing(18)
        self.info_label = QLabel("")
        ilay.addWidget(self.info_label)
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setFixedWidth(260)
        self.seek.setVisible(False)
        self.seek.sliderMoved.connect(self.player.setPosition)
        ilay.addWidget(self.seek)
        self.time_label = QLabel("")
        self.time_label.setVisible(False)
        ilay.addWidget(self.time_label)
        ilay.addStretch(1)
        self.pos_label = QLabel("第 0 / 0 张   ← → 切换   Esc 退出")
        ilay.addWidget(self.pos_label)

        # 组装
        self._root = QWidget()
        self._root.setObjectName("viewer")
        root_lay = QVBoxLayout(self._root)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)
        root_lay.addWidget(self._tb)
        root_lay.addLayout(self.media_stack, 1)
        root_lay.addWidget(self.info_bar)
        self.setCentralWidget(self._root)
        self.install_edge_resize(self._root)
        self.register_corner(self.info_bar)  # 最大化时随窗口去掉底部圆角

        self.resize(1080, 780)
        self._load()

    # ---------- 工具 ----------
    def _mk(self, text, slot, icon_name=None):
        b = QPushButton(text)
        b.setObjectName("viewerBtn")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        if icon_name:
            b.setIcon(make_icon(icon_name, "#EBEBF0", 15))
            b.setIconSize(QSize(15, 15))
        b.clicked.connect(slot)
        return b

    def _fit(self):
        self.view.fit()

    def _actual(self):
        self.view.resetTransform()

    # ---------- 图片加载 ----------
    def _load(self):
        if not (0 <= self.index < len(self.photos)):
            self.filename_label.setText("没有可浏览的照片")
            self.info_label.setText("")
            self.pos_label.setText("")
            return
        p = self.photos[self.index]
        self.filename_label.setText(p["filename"])
        self.setWindowTitle(p["filename"])
        info = []
        if p.get("taken_at"):
            info.append("📅 " + p["taken_at"])
        if p.get("lat") is not None:
            info.append(f"📍 {p['lat']:.5f}, {p['lng']:.5f}")
        if p.get("camera_model"):
            info.append("📷 " + p["camera_model"])
        if p.get("width"):
            info.append(f"{p['width']}×{p['height']}")
        size_kb = (p.get("file_size") or 0) / 1024
        info.append(f"{size_kb / 1024:.1f} MB" if size_kb > 1024 else f"{size_kb:.0f} KB")
        info.append("归属：" + (p.get("user_name") or "未知"))

        # ---- 视频：切换到播放器 ----
        if p.get("duration") is not None:
            self.player.stop()
            self.media_stack.setCurrentWidget(self.video_widget)
            self.btn_fit.setEnabled(False)
            self.btn_actual.setEnabled(False)
            self.btn_play.setVisible(True)
            self.seek.setVisible(True)
            self.time_label.setVisible(True)
            self.seek.setValue(0)
            info.append(f"🎬 时长 {self._fmt_time(p['duration'])}")
            self.player.setSource(QUrl.fromLocalFile(p["abs_path"]))
            self.player.play()
        else:
            # ---- 图片 ----
            self.player.stop()
            self.media_stack.setCurrentWidget(self.view)
            self.btn_fit.setEnabled(True)
            self.btn_actual.setEnabled(True)
            self.btn_play.setVisible(False)
            self.seek.setVisible(False)
            self.time_label.setVisible(False)
            path = p.get("preview_path") or p.get("abs_path")
            pm = QPixmap(path)
            if pm.isNull():
                pm = QPixmap(p.get("abs_path"))
            if pm.isNull():
                self.filename_label.setText("无法加载：" + p["filename"])
                return
            self.view.set_image(pm)

        self.info_label.setText("    ".join(info))
        self.pos_label.setText(f"第 {self.index + 1} / {len(self.photos)} 个   ← → 切换   Esc 退出")
        fav = bool(p.get("is_favorite"))
        self.btn_fav.setText("已收藏" if fav else "收藏")
        self.btn_fav.setIcon(make_icon("heart", "#FF2D55" if fav else "#EBEBF0", 15))

    # ---------- 视频播放 ----------
    @staticmethod
    def _fmt_time(sec):
        sec = int(sec or 0)
        return f"{sec // 60}:{sec % 60:02d}"

    def _toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _on_player_state(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.btn_play.setText("暂停" if playing else "播放")
        self.btn_play.setIcon(make_icon("pause" if playing else "play", "#EBEBF0", 15))

    def _on_player_pos(self, pos):
        if not self.seek.isSliderDown():
            self.seek.setValue(pos)
        self.time_label.setText(f"{self._fmt_time(pos / 1000)} / "
                                f"{self._fmt_time(self.player.duration() / 1000)}")

    def _on_player_dur(self, dur):
        self.seek.setRange(0, max(0, dur))

    def _on_player_error(self, *_):
        self.filename_label.setText("无法播放：" + self.filename_label.text())

    # ---------- 导航 ----------
    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Left:
            self._goto(self.index - 1)
        elif e.key() == Qt.Key.Key_Right:
            self._goto(self.index + 1)
        elif e.key() == Qt.Key.Key_Space:
            self._toggle_play()
        elif e.key() == Qt.Key.Key_Escape:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.close()
        else:
            super().keyPressEvent(e)

    def closeEvent(self, e):
        try:
            self.player.stop()
        except Exception:
            pass
        super().closeEvent(e)

    def _goto(self, i):
        if 0 <= i < len(self.photos):
            self.index = i
            self._load()

    # ---------- 操作 ----------
    def _toggle_fav(self):
        if not (0 <= self.index < len(self.photos)):
            return
        p = self.photos[self.index]
        fav = not bool(p.get("is_favorite"))
        self.db.set_favorite(p["id"], fav)
        p["is_favorite"] = 1 if fav else 0
        self.btn_fav.setText("已收藏" if fav else "收藏")
        self.btn_fav.setIcon(make_icon("heart", "#FF2D55" if fav else "#EBEBF0", 15))
        self.changed.emit()

    def _delete_current(self):
        if not (0 <= self.index < len(self.photos)):
            return
        p = self.photos[self.index]
        result = single_delete(self.db, self.trash_dir, p["id"])
        if result["failed"]:
            self.filename_label.setText("删除失败：" + p["filename"])
            return
        self.photos.pop(self.index)
        self.changed.emit()
        if not self.photos:
            self.close()
            return
        if self.index >= len(self.photos):
            self.index = len(self.photos) - 1
        self._load()
