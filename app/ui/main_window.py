"""主窗口：左侧边栏 + 顶部筛选工具栏 + 缩略图墙（小窗口）。

双击缩略图打开大图浏览窗口（浏览窗口），两窗口可同时使用。
"""
import datetime as dt
import os
import subprocess
from pathlib import Path

from PySide6.QtCore import (QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer)
from PySide6.QtGui import QAction, QColor, QPalette
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QFrame, QHBoxLayout,
                               QGraphicsOpacityEffect, QLabel, QLineEdit,
                               QListView, QMenu, QMessageBox, QProgressBar,
                               QPushButton, QSizePolicy, QStackedWidget,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from .. import __version__
from ..db import Database
from ..dedup import single_delete
from ..map_server import MapServer
from ..scanner import Scanner
from ..settings import Settings
from ..watcher import FolderWatcher
from .calendar_page import CalendarPage
from .dialogs import (DupGroupDialog, FoldersDialog, SettingsDialog,
                      TrashDialog, UsersDialog)
from .icons import icon as make_icon
from .style import TEXT_SECONDARY, user_color
from .timeline_wall import TimelineWall
from .viewer_window import ViewerWindow
from .widgets import (AnimatedComboBox, FramelessWindow, ScanThread,
                      SimilarThread, TitleBar, color_icon)


class MainWindow(FramelessWindow):
    def __init__(self, db: Database, data_dir: Path, parent=None):
        super().__init__(parent=parent)
        self.db = db
        self.data_dir = Path(data_dir)
        self.thumb_dir = self.data_dir / "thumbs"
        self.trash_dir = self.data_dir / "trash"
        self.scanner = Scanner(db, self.thumb_dir)
        self._current_photos = []
        self._scan_thread = None
        self._similar_thread = None
        self._pending_scan = []
        self._auto_scan = False
        self._day = None
        self.watcher = None
        self.settings = Settings(self.data_dir / "settings.json")
        self._mode = "map"          # map | all | dups | user
        self._mode_arg = None       # user id
        self._mode_sub = None       # all | fav | gps | nogps（user 模式下）
        self._viewers = []
        self._user_items = {}
        self.map_server = MapServer(db, self.data_dir)

        self.setWindowTitle("家庭相册")
        self.resize(1240, 800)
        self._build_ui()
        self.refresh_all()

        # 看门狗：库内容变化时自动刷新（首次大扫描时照片墙实时增长）
        self._last_count = -1
        self._last_dups = -1
        self._watchdog = QTimer(self)
        self._watchdog.setInterval(3000)
        self._watchdog.timeout.connect(self._watchdog_tick)
        self._watchdog.start()

        # 自动监控数据源文件夹 + 启动自动扫描
        self._setup_watcher()
        QTimer.singleShot(1500, self._startup_scan)
        QTimer.singleShot(4000, self._refresh_similar)

    def _watchdog_tick(self):
        st = self.db.stats()
        if st["total"] != self._last_count or st["pending_dups"] != self._last_dups:
            self._last_count = st["total"]
            self._last_dups = st["pending_dups"]
            self.refresh_all()

    # ==================================================================
    # 界面搭建
    # ==================================================================
    def _build_ui(self):
        self.title_bar = TitleBar(self, f"家庭相册 v{__version__}")
        self.setMenuWidget(self.title_bar)

        central = QWidget()
        central.setObjectName("central")
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---------- 侧边栏 ----------
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(216)
        s = QVBoxLayout(sidebar)
        s.setContentsMargins(12, 16, 12, 12)
        s.setSpacing(2)

        brand = QLabel("📷 家庭相册")
        brand.setObjectName("brandLabel")
        brand.setContentsMargins(12, 0, 0, 10)
        s.addWidget(brand)

        h1 = QLabel("照片库")
        h1.setObjectName("sideHeader")
        s.addWidget(h1)
        self.btn_map = self._side_button("地图", "map")
        self.btn_all = self._side_button("全部照片", "images")
        self.btn_calendar = self._side_button("日历", "calendar-days")
        self.btn_calendar.setVisible(bool(self.settings.get("show_calendar")))
        s.addWidget(self.btn_map)
        s.addWidget(self.btn_all)
        s.addWidget(self.btn_calendar)

        h2 = QLabel("家人")
        h2.setObjectName("sideHeader")
        s.addWidget(h2)
        self.view_btn_group = QButtonGroup(self)
        self.view_btn_group.setExclusive(True)
        self.view_btn_group.addButton(self.btn_map)
        self.view_btn_group.addButton(self.btn_all)
        self.view_btn_group.addButton(self.btn_calendar)
        self.btn_map.clicked.connect(lambda: self._set_mode("map"))
        self.btn_all.clicked.connect(lambda: self._set_mode("all"))
        self.btn_calendar.clicked.connect(lambda: self._set_mode("calendar"))
        self.btn_map.setChecked(True)

        # 家人树：点开带展开动画，子项为 所有照片/收藏/有定位/无定位
        self.user_tree = QTreeWidget()
        self.user_tree.setObjectName("userTree")
        self.user_tree.setHeaderHidden(True)
        self.user_tree.setAnimated(True)          # 展开/收起动画
        self.user_tree.setIndentation(16)
        self.user_tree.setFrameShape(QFrame.Shape.NoFrame)
        self.user_tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.user_tree.setExpandsOnDoubleClick(False)
        self.user_tree.itemClicked.connect(self._on_tree_item_clicked)
        # 树占满剩余空间（不再加多余 stretch，避免展开后把其它家人挤出可视区）
        self.user_tree.setSizePolicy(QSizePolicy.Policy.Preferred,
                                     QSizePolicy.Policy.Expanding)
        s.addWidget(self.user_tree, 1)

        self.btn_scan = self._side_ghost("重新扫描", "refresh")
        self.btn_folders = self._side_ghost("数据来源…", "folder")
        self.btn_users = self._side_ghost("用户管理…", "user")
        self.btn_trash = self._side_ghost("回收站…", "trash-can")
        self.btn_settings = self._side_ghost("设置…", "star")
        s.addWidget(self.btn_scan)
        s.addWidget(self.btn_folders)
        s.addWidget(self.btn_users)
        s.addWidget(self.btn_trash)
        s.addWidget(self.btn_settings)
        self.btn_scan.clicked.connect(self._scan_all)
        self.btn_folders.clicked.connect(self._open_folders)
        self.btn_users.clicked.connect(self._open_users)
        self.btn_trash.clicked.connect(self._open_trash)
        self.btn_settings.clicked.connect(self._open_settings)
        root.addWidget(sidebar)

        # ---------- 右侧主区域 ----------
        right = QWidget()
        r = QVBoxLayout(right)
        r.setContentsMargins(20, 16, 20, 0)
        r.setSpacing(12)

        # 工具栏
        bar = QHBoxLayout()
        self.title_label = QLabel("全部照片")
        self.title_label.setObjectName("viewTitle")
        self.subtitle_label = QLabel("")
        self.subtitle_label.setObjectName("viewSubtitle")
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.subtitle_label)
        bar.addLayout(title_box)
        bar.addStretch(1)

        self.time_combo = AnimatedComboBox()
        self.time_combo.addItem("全部时间", None)
        self.time_combo.addItem("今年", "year")
        self.time_combo.addItem("本月", "month")
        self.time_combo.addItem("无拍摄时间", "no_time")
        self.time_combo.setFixedWidth(120)
        self.fmt_combo = AnimatedComboBox()
        self.fmt_combo.addItem("全部格式", None)
        for e in (".heic", ".jpg", ".png", ".gif", ".webp"):
            self.fmt_combo.addItem(e.upper(), e)
        self.fmt_combo.setFixedWidth(110)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索文件名…")
        self.search_edit.setFixedWidth(180)
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.addAction(make_icon("search", "#86868B", 14),
                                   QLineEdit.ActionPosition.LeadingPosition)
        # 半透明窗口下强制白色底（QSS 之外的兜底）
        self.search_edit.setAutoFillBackground(True)
        pal = self.search_edit.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#1D1D1F"))
        self.search_edit.setPalette(pal)
        # 地点筛选（离线反查出的省·市）
        self.place_combo = AnimatedComboBox()
        self.place_combo.addItem("全部地点", None)
        self.place_combo.setFixedWidth(180)
        self.place_combo.currentIndexChanged.connect(lambda _: self.refresh_view())
        for w in (self.time_combo, self.place_combo, self.fmt_combo, self.search_edit):
            bar.addWidget(w)
        self.btn_dup_review = QPushButton("处理重复照片…")
        self.btn_dup_review.setObjectName("primary")
        self.btn_dup_review.setIcon(make_icon("clone", "#FFFFFF", 15))
        self.btn_dup_review.setIconSize(QSize(15, 15))
        self.btn_dup_review.setVisible(False)
        self.btn_dup_review.clicked.connect(self._open_dup_dialog)
        bar.addWidget(self.btn_dup_review)
        self.time_combo.currentIndexChanged.connect(lambda _: self.refresh_view())
        self.fmt_combo.currentIndexChanged.connect(lambda _: self.refresh_view())
        self.search_edit.textChanged.connect(lambda _: self.refresh_view())
        r.addLayout(bar)

        # 内容区：空状态 / 缩略图墙
        self.stack = QStackedWidget()
        self.empty_page = QWidget()
        el = QVBoxLayout(self.empty_page)
        el.addStretch(1)
        self.empty_label = QLabel("这里还没有照片")
        self.empty_label.setObjectName("emptyHint")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(self.empty_label)
        self.empty_btn = QPushButton("开始设置")
        self.empty_btn.setObjectName("primary")
        self.empty_btn.setFixedWidth(140)
        self.empty_btn.clicked.connect(self._first_run_setup)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(self.empty_btn)
        btn_row.addStretch(1)
        el.addLayout(btn_row)
        el.addStretch(2)
        self.stack.addWidget(self.empty_page)

        self.wall = TimelineWall()
        self.wall.setObjectName("photoWall")
        self.wall.photo_activated.connect(self._open_wall_photo)
        self.wall.photo_menu_requested.connect(self._wall_menu)
        self.stack.addWidget(self.wall)

        # 地图主页（WebEngine，失败时降级为提示页；PM_SKIP_MAP=1 可强制跳过）
        self.map_page = None
        self.map_fallback = None
        if os.environ.get("PM_SKIP_MAP") != "1":
            try:
                from .map_page import MapPage
                self.map_page = MapPage(self.map_server)
                self.map_page.set_photo_handler(self._open_photo_by_id)
            except Exception:
                self.map_page = None
        if self.map_page is None:
            self.map_fallback = QLabel("地图加载失败\n（QtWebEngine 不可用）")
            self.map_fallback.setObjectName("emptyHint")
            self.map_fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.stack.addWidget(self.map_fallback)
        else:
            self.stack.addWidget(self.map_page)

        # 日历页（默认隐藏，按需惰性创建）
        self.calendar_page = None

        r.addWidget(self.stack, 1)
        root.addWidget(right, 1)
        self.setCentralWidget(central)
        self.install_edge_resize(central)

        # 状态栏
        sb = self.statusBar()
        self.status_label = QLabel("")
        sb.addWidget(self.status_label)
        sb.addPermanentWidget(QLabel("　"))
        self.progress = QProgressBar()
        self.progress.setFixedWidth(220)
        self.progress.setVisible(False)
        sb.addPermanentWidget(self.progress)
        self.scan_status_label = QLabel("")
        sb.addPermanentWidget(self.scan_status_label)

    def _side_button(self, text, icon_name=None):
        b = QPushButton(text)
        b.setObjectName("sideButton")
        b.setCheckable(True)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        if icon_name:
            b.setIcon(make_icon(icon_name, "#1D1D1F", 16))
            b.setIconSize(QSize(16, 16))
        return b

    def _side_ghost(self, text, icon_name=None):
        b = QPushButton(text)
        b.setObjectName("sideGhost")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        if icon_name:
            b.setIcon(make_icon(icon_name, "#86868B", 15))
            b.setIconSize(QSize(15, 15))
        return b

    # ==================================================================
    # 刷新
    # ==================================================================
    def refresh_all(self):
        """刷新侧边栏计数与当前视图。"""
        st = self.db.stats()
        self.btn_all.setText(f"全部照片　{st['total']}")
        self._reload_places()

        # 家人树（保持展开状态；结构未变时仅更新文字）
        expanded = set()
        for i in range(self.user_tree.topLevelItemCount()):
            it = self.user_tree.topLevelItem(i)
            if it.isExpanded():
                expanded.add(it.data(0, Qt.ItemDataRole.UserRole + 1))
        current_ids = [u["id"] for u in st["per_user"]]
        tree_ids = [self.user_tree.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole + 1)
                    for i in range(self.user_tree.topLevelItemCount())]
        if tree_ids != current_ids:
            self.user_tree.clear()
            self._user_items = {}
            for u in st["per_user"]:
                color = u["color"] or user_color(u["id"])
                parent = QTreeWidgetItem([f"{u['name']}　{u['n']}"])
                parent.setIcon(0, color_icon(color))
                parent.setData(0, Qt.ItemDataRole.UserRole + 1, u["id"])     # 用户 id
                parent.setData(0, Qt.ItemDataRole.UserRole + 2, "user")      # 类型
                parent.setSizeHint(0, QSize(0, 34))
                for label, key, ic in (("所有照片", "all", "images"),
                                       ("视频", "video", "film"),
                                       ("收藏", "fav", "heart"),
                                       ("有地理定位", "gps", "location-dot"),
                                       ("无地理定位", "nogps", "ban"),
                                       ("重复照片", "dup", "clone"),
                                       ("相似照片", "similar", "magnifying-glass")):
                    child = QTreeWidgetItem([label])
                    child.setIcon(0, make_icon(ic, "#86868B", 15))
                    child.setData(0, Qt.ItemDataRole.UserRole + 1, u["id"])
                    child.setData(0, Qt.ItemDataRole.UserRole + 2, key)
                    child.setSizeHint(0, QSize(0, 30))
                    parent.addChild(child)
                self.user_tree.addTopLevelItem(parent)
                self._user_items[u["id"]] = parent
                if u["id"] in expanded:
                    parent.setExpanded(True)
        else:
            for u in st["per_user"]:
                it = self._user_items.get(u["id"])
                if it:
                    it.setText(0, f"{u['name']}　{u['n']}")

        # 修正选中态
        if self._mode == "map":
            self.btn_map.setChecked(True)
        elif self._mode == "all":
            self.btn_all.setChecked(True)
        elif self._mode in ("calendar", "day"):
            self.btn_calendar.setChecked(True)

        if not self.db.list_users():
            self.empty_label.setText("欢迎使用家庭相册 👋\n\n第一步：添加家人（每位家人一个账号）\n"
                                     "第二步：给家人指定照片文件夹并扫描")
            self.empty_btn.setVisible(True)
        elif not self.db.list_folders():
            self.empty_label.setText("还没有照片\n\n请先在左下角「数据来源」中添加照片文件夹")
            self.empty_btn.setVisible(False)
        self.refresh_view()

    def _reload_places(self):
        """刷新地点下拉（只列出库里实际存在的地点，带数量）。"""
        try:
            current = self.place_combo.currentData()
            places = self.db.places_list()
            self.place_combo.blockSignals(True)
            self.place_combo.clear()
            self.place_combo.addItem("全部地点", None)
            for p in places[:80]:
                self.place_combo.addItem(f"{p['place']}（{p['n']}）", p["place"])
            idx = self.place_combo.findData(current)
            self.place_combo.setCurrentIndex(idx if idx >= 0 else 0)
            self.place_combo.blockSignals(False)
        except Exception:
            pass

    def _on_tree_item_clicked(self, item, _col):
        kind = item.data(0, Qt.ItemDataRole.UserRole + 2)
        uid = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if kind == "user":
            # 点家人：展开/收起（带动画）+ 显示其全部照片
            item.setExpanded(not item.isExpanded())
            self.user_tree.scrollToItem(item)
            self._set_mode("user", uid, "all")
        elif kind in ("all", "fav", "gps", "nogps", "dup", "video", "similar"):
            self._set_mode("user", uid, kind)

    def _set_mode(self, mode, arg=None, sub=None):
        self._mode = mode
        self._mode_arg = arg
        self._mode_sub = sub if mode == "user" else None
        self.refresh_view()

    def refresh_view(self):
        st = self.db.stats()

        # ---- 日历模式（默认不显示入口，可在设置里开启） ----
        if self._mode == "calendar":
            self.title_label.setText("日历")
            self.subtitle_label.setText("点击有照片的日期，查看当天的照片与视频")
            if self.calendar_page is None:
                self.calendar_page = CalendarPage(self.db)
                self.calendar_page.day_selected.connect(self._on_day_selected)
                self.stack.addWidget(self.calendar_page)
            self.calendar_page.reload()
            self.stack.setCurrentWidget(self.calendar_page)
            self._update_status()
            return

        # ---- 地图模式（主页） ----
        if self._mode == "map":
            self.title_label.setText("地图")
            gps_n = st["total"] - st["no_gps"]
            self.subtitle_label.setText(
                f"{gps_n} 张带定位的照片 · 滚轮/按钮缩放 · 圆点大小随照片数量 · 点击圆点查看照片")
            if not self.db.list_users():
                self.stack.setCurrentWidget(self.empty_page)
                return
            if self.map_page is not None:
                self.stack.setCurrentWidget(self.map_page)
                self.map_page.reload_photos()
            else:
                self.stack.setCurrentWidget(self.map_fallback)
            self._update_status()
            return

        if self._mode == "all":
            self.title_label.setText("全部照片")
        elif self._mode == "dups":
            self.title_label.setText("重复照片")
        elif self._mode == "day":
            self.title_label.setText(f"{self._day or ''} 的照片")
        else:
            name = next((u["name"] for u in st["per_user"] if u["id"] == self._mode_arg), "家人")
            sub_names = {"all": "所有照片", "video": "视频", "fav": "收藏",
                         "gps": "有地理定位", "nogps": "无地理定位",
                         "dup": "重复照片", "similar": "相似照片"}
            sub_name = sub_names.get(self._mode_sub, "照片")
            self.title_label.setText(f"{name} · {sub_name}")

        if not self.db.list_users():
            self.stack.setCurrentWidget(self.empty_page)
            return
        if not self.db.list_folders():
            self.empty_label.setText("还没有照片\n\n请先在左下角「数据来源」中添加照片文件夹")
            self.stack.setCurrentWidget(self.empty_page)
            return

        time_filter = self.time_combo.currentData()
        now = dt.datetime.now()
        kwargs = {}
        # 「处理」按钮：重复照片 / 相似照片 两种视图下出现
        show_review = self._mode == "user" and self._mode_sub in ("dup", "similar")
        self.btn_dup_review.setVisible(show_review)
        if show_review:
            if self._mode_sub == "similar":
                self.btn_dup_review.setText("处理相似照片…")
                self.btn_dup_review.setIcon(make_icon("magnifying-glass", "#FFFFFF", 15))
            else:
                self.btn_dup_review.setText("处理重复照片…")
                self.btn_dup_review.setIcon(make_icon("clone", "#FFFFFF", 15))
        if self._mode == "user":
            kwargs["user_id"] = self._mode_arg
            if self._mode_sub == "fav":
                kwargs["fav_only"] = True
            elif self._mode_sub == "gps":
                kwargs["has_gps"] = True
            elif self._mode_sub == "nogps":
                kwargs["has_gps"] = False
            elif self._mode_sub == "dup":
                kwargs["dup_only"] = True
            elif self._mode_sub == "similar":
                kwargs["similar_only"] = True
            elif self._mode_sub == "video":
                kwargs["video_only"] = True
        if self._mode == "day" and self._day:
            kwargs["date_from"] = self._day
            kwargs["date_to"] = self._day
        if time_filter == "year":
            kwargs["year"] = now.year
        elif time_filter == "month":
            kwargs["year"] = now.year
            kwargs["month"] = now.month
        elif time_filter == "no_time":
            kwargs["no_time"] = True
        fmt = self.fmt_combo.currentData()
        if fmt:
            kwargs["ext"] = fmt
        place = self.place_combo.currentData()
        if place:
            kwargs["place"] = place
        text = self.search_edit.text().strip()
        if text:
            kwargs["text"] = text

        photos = self.db.query_photos(**kwargs)
        self._current_photos = photos
        self.wall.set_photos(photos)

        if photos:
            if self.stack.currentWidget() is not self.wall:
                self.stack.setCurrentWidget(self.wall)
                self._fade_in_wall()
            if self._mode_sub == "dup":
                self.subtitle_label.setText(
                    f"共 {len(photos)} 张重复待处理 · 内容完全相同的照片建议每组保留一张")
            elif self._mode_sub == "similar":
                self.subtitle_label.setText(
                    f"共 {len(photos)} 张疑似相似 · 点右上角「处理相似照片…」逐组确认")
            else:
                self.subtitle_label.setText(
                    f"共 {len(photos)} 张 · 有定位 {sum(1 for p in photos if p.get('lat'))} 张")
        else:
            if self._mode_sub == "dup":
                self.empty_label.setText("🎉 没有待处理的重复照片")
            elif self._mode_sub == "similar":
                self.empty_label.setText("🎉 没有待处理的相似照片\n\n（灵敏度可在「设置…」里调整）")
            else:
                self.empty_label.setText("没有符合条件的照片")
            self.empty_btn.setVisible(False)
            self.stack.setCurrentWidget(self.empty_page)
        self._update_status()

    def _fade_in_wall(self):
        """切换到照片墙时的淡入动画。"""
        try:
            eff = QGraphicsOpacityEffect(self.wall)
            eff.setOpacity(0.25)
            self.wall.setGraphicsEffect(eff)
            anim = QPropertyAnimation(eff, b"opacity", self.wall)
            anim.setDuration(160)
            anim.setStartValue(0.25)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.finished.connect(lambda: self.wall.setGraphicsEffect(None))
            anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        except Exception:
            pass

    def _update_status(self):
        st = self.db.stats()
        parts = [f"共 {st['total']} 张照片"]
        parts.append(f"{st['pending_dups']} 组重复待处理")
        parts.append(f"无定位 {st['no_gps']} 张" if st["no_gps"] else "全部有定位")
        if st["no_time"]:
            parts.append(f"无拍摄时间 {st['no_time']} 张")
        self.status_label.setText("　·　".join(parts))

    # ==================================================================
    # 大图浏览
    # ==================================================================
    def _open_wall_photo(self, photo_id: int):
        """照片墙双击：在当前筛选列表中打开对应照片。"""
        photos = self._current_photos
        idx = next((i for i, p in enumerate(photos) if p["id"] == photo_id), None)
        if idx is None:
            return
        viewer = ViewerWindow(self.db, self.trash_dir, photos, idx, parent=self)
        viewer.changed.connect(self._on_viewer_changed)
        viewer.destroyed.connect(lambda *_: self._on_viewer_closed())
        self._viewers.append(viewer)
        viewer.show()

    def _open_photo_by_id(self, photo_id: int):
        """地图上点击圆点：打开对应照片的大图浏览窗口。"""
        photos = self.db.query_photos()
        idx = next((i for i, p in enumerate(photos) if p["id"] == photo_id), None)
        if idx is None:
            return
        viewer = ViewerWindow(self.db, self.trash_dir, photos, idx, parent=self)
        viewer.changed.connect(self._on_viewer_changed)
        viewer.destroyed.connect(lambda *_: self._on_viewer_closed())
        self._viewers.append(viewer)
        viewer.show()

    def _on_viewer_changed(self):
        pass  # 删除时由关闭统一刷新，避免打断浏览

    def _on_viewer_closed(self):
        self._viewers = [v for v in self._viewers if v.isVisible()]
        self.refresh_all()

    def _wall_menu(self, photo_id: int, global_pos):
        photo = next((p for p in self._current_photos if p["id"] == photo_id), None)
        if not photo:
            return
        menu = QMenu(self)
        act_open = QAction("打开", self)
        act_open.triggered.connect(lambda: self._open_wall_photo(photo_id))
        act_fav = QAction("♥ 已收藏" if photo.get("is_favorite") else "♡ 收藏", self)
        act_fav.triggered.connect(lambda: self._toggle_fav(photo_id))
        act_reveal = QAction("在资源管理器中显示", self)
        act_reveal.triggered.connect(lambda: self._reveal(photo))
        act_copy = QAction("复制文件路径", self)
        act_copy.triggered.connect(lambda: self._copy_path(photo))
        act_del = QAction("删除（移入回收站）", self)
        act_del.triggered.connect(lambda: self._delete_photo_id(photo_id))
        menu.addAction(act_open)
        menu.addAction(act_fav)
        menu.addSeparator()
        menu.addAction(act_reveal)
        menu.addAction(act_copy)
        menu.addSeparator()
        menu.addAction(act_del)
        menu.exec(global_pos)

    def _toggle_fav(self, photo_id: int):
        p = next((x for x in self._current_photos if x["id"] == photo_id), None)
        if not p:
            return
        fav = not bool(p.get("is_favorite"))
        self.db.set_favorite(p["id"], fav)
        p["is_favorite"] = 1 if fav else 0
        if self._mode == "user" and self._mode_sub == "fav" and not fav:
            self.refresh_view()

    def _reveal(self, photo):
        try:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(photo["abs_path"])])
        except OSError:
            pass

    def _copy_path(self, photo):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(photo["abs_path"])

    def _delete_photo_id(self, photo_id: int):
        p = next((x for x in self._current_photos if x["id"] == photo_id), None)
        if not p:
            return
        ret = QMessageBox.question(
            self, "删除照片", f"把「{p['filename']}」移入回收站？（可恢复）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ret != QMessageBox.StandardButton.Yes:
            return
        single_delete(self.db, self.trash_dir, p["id"])
        self.refresh_all()

    # ==================================================================
    # 扫描
    # ==================================================================
    def _scan_all(self):
        folder_ids = [f["id"] for f in self.db.list_folders()]
        if not folder_ids:
            self._open_folders()
            return
        self._run_scan(folder_ids)

    def _run_scan(self, folder_ids, auto: bool = False):
        """启动扫描线程。auto=True 表示由文件夹监控自动触发。"""
        folder_ids = [fid for fid in folder_ids if fid]
        if not folder_ids:
            return
        if self._scan_thread is not None and self._scan_thread.isRunning():
            # 正在扫描：记录待扫，等本轮结束后继续
            self._pending_scan = sorted(set(self._pending_scan) | set(folder_ids))
            return
        self._auto_scan = auto
        self._scan_thread = ScanThread(self.scanner, folder_ids, self,
                                       clean_missing=self.settings.get("clean_missing"))
        self._scan_thread.progress.connect(self._on_scan_progress)
        self._scan_thread.finished_ok.connect(self._on_scan_done)
        self._scan_thread.failed.connect(self._on_scan_failed)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.btn_scan.setEnabled(False)
        if auto:
            self.scan_status_label.setText("检测到新文件，正在自动扫描…")
        self._scan_thread.start()

    def _on_scan_progress(self, done, total, new, dup):
        if total > 0:
            self.progress.setMaximum(total)
            self.progress.setValue(done)
        self.scan_status_label.setText(f"扫描 {done}/{total} · 新增 {new} · 重复 {dup}")

    def _on_scan_done(self, result):
        self.progress.setVisible(False)
        self.btn_scan.setEnabled(True)
        removed = result.get("removed", 0)
        text = f"扫描完成：新增 {result.get('new', 0)}，重复 {result.get('duplicates', 0)}"
        if removed:
            text += f"，清理失效 {removed}"
        self.scan_status_label.setText(text)
        # 扫描后刷新监听目录（可能新增了子目录）
        if self.watcher is not None:
            self.watcher.refresh_dirs()
        self.refresh_all()
        # 有新照片时重新计算相似组
        if result.get("new"):
            self._refresh_similar()
        if self._pending_scan:
            pending = self._pending_scan
            self._pending_scan = []
            QTimer.singleShot(500, lambda: self._run_scan(pending, auto=True))

    def _on_scan_failed(self, msg):
        self.progress.setVisible(False)
        self.btn_scan.setEnabled(True)
        self.scan_status_label.setText("扫描失败：" + msg)

    # ==================================================================
    # 自动监控
    # ==================================================================
    def _setup_watcher(self):
        self.watcher = FolderWatcher(self)
        self.watcher.changed.connect(self._on_folders_changed)
        self._sync_watcher()

    def _sync_watcher(self):
        if self.watcher is None:
            return
        self.watcher.enabled = bool(self.settings.get("auto_watch"))
        self.watcher.set_folders([(f["id"], f["path"]) for f in self.db.list_folders()])

    def _on_folders_changed(self, folder_ids):
        if not self.settings.get("auto_watch"):
            return
        self._run_scan(folder_ids, auto=True)

    def _startup_scan(self):
        if not self.settings.get("auto_scan_on_start"):
            return
        folder_ids = [f["id"] for f in self.db.list_folders()]
        if folder_ids:
            self._run_scan(folder_ids, auto=True)

    def _open_settings(self):
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec():
            self._sync_watcher()
            self._apply_calendar_visibility()
            self.scan_status_label.setText("设置已保存")

    def _apply_calendar_visibility(self):
        """根据设置显示/隐藏日历入口；关闭时若正停留在日历则回到全部照片。"""
        show = bool(self.settings.get("show_calendar"))
        self.btn_calendar.setVisible(show)
        if not show and self._mode in ("calendar", "day"):
            self._day = None
            self._set_mode("all")

    def _open_trash(self):
        dlg = TrashDialog(self.db, self.trash_dir, self)
        restored = {"n": 0}
        dlg.changed.connect(lambda: restored.__setitem__("n", restored["n"] + 1))
        dlg.exec()
        self.refresh_all()
        # 有恢复操作时，重扫一次把文件重新纳入索引
        if restored["n"]:
            folder_ids = [f["id"] for f in self.db.list_folders()]
            self._run_scan(folder_ids, auto=True)

    # ==================================================================
    # 对话框
    # ==================================================================
    def _open_users(self):
        dlg = UsersDialog(self.db, self)
        dlg.changed.connect(self.refresh_all)
        dlg.exec()
        self.refresh_all()

    def _open_dup_dialog(self):
        kind = "similar" if self._mode_sub == "similar" else "exact"
        dlg = DupGroupDialog(self.db, self.trash_dir, self, kind=kind)
        dlg.changed.connect(self.refresh_all)
        dlg.exec()
        self.refresh_all()

    # ==================================================================
    # 相似照片
    # ==================================================================
    def _refresh_similar(self):
        """后台补算感知哈希并重新聚类（不阻塞界面）。"""
        if self._similar_thread is not None and self._similar_thread.isRunning():
            return
        try:
            threshold = int(self.settings.get("similar_threshold") or 4)
        except (TypeError, ValueError):
            threshold = 4
        self._similar_thread = SimilarThread(self.db, threshold, self)
        self._similar_thread.progress.connect(self.scan_status_label.setText)
        self._similar_thread.finished_ok.connect(self._on_similar_done)
        self._similar_thread.failed.connect(
            lambda msg: self.scan_status_label.setText("相似照片计算失败：" + msg))
        self._similar_thread.start()

    def _on_similar_done(self, stat):
        self.scan_status_label.setText(
            f"相似照片：{stat.get('groups', 0)} 组 / {stat.get('photos', 0)} 张待确认")
        self.refresh_all()

    def _on_day_selected(self, day: str):
        """日历点选某天 → 只看这一天的照片。"""
        self._day = day
        self._mode = "day"
        self._mode_sub = None
        self.refresh_view()

    def _open_folders(self):
        dlg = FoldersDialog(self.db, self.scanner, self)
        dlg.changed.connect(self.refresh_all)
        dlg.exec()
        self._sync_watcher()          # 数据源变化 → 重新注册监控
        self.refresh_all()

    def _first_run_setup(self):
        if not self.db.list_users():
            self._open_users()
        self._open_folders()

    def closeEvent(self, e):
        if self.watcher is not None:
            self.watcher.stop()
        for v in list(self._viewers):
            v.close()
        super().closeEvent(e)
