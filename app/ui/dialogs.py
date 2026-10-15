"""对话框：用户管理、数据来源、重复照片处理。"""
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QFileDialog,
                               QFrame, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QProgressBar, QPushButton,
                               QRadioButton, QScrollArea, QVBoxLayout, QWidget)

from ..db import Database
from ..dedup import resolve_group, suggest_keep
from ..scanner import Scanner
from .icons import icon as make_icon
from .models import load_thumb_pixmap
from .style import (ACCENT, RED, TEXT_SECONDARY, USER_COLORS, user_color)
from .widgets import AnimatedComboBox, AppleDialog, ScanThread, color_icon


# ======================================================================
# 用户管理
# ======================================================================
class UsersDialog(AppleDialog):
    changed = Signal()

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("用户管理")
        self.setModal(True)
        self.resize(460, 520)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        title = QLabel("用户管理")
        title.setObjectName("dialogTitle")
        lay.addWidget(title)
        hint = QLabel("每位家人一个账号，用于标记照片归属。删除用户只移除索引，不会动照片文件。")
        hint.setStyleSheet(f"color: {TEXT_SECONDARY};")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.listw = QListWidget()
        lay.addWidget(self.listw, 1)

        # 添加区
        add_row = QHBoxLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("家人姓名，如：爸爸")
        self.color_combo = AnimatedComboBox()
        for i, c in enumerate(USER_COLORS):
            self.color_combo.addItem(color_icon(c), f"颜色 {i + 1}", c)
        self.color_combo.setFixedWidth(56)
        btn_add = QPushButton("添加")
        btn_add.setObjectName("primary")
        btn_add.setIcon(make_icon("plus", "#FFFFFF", 14))
        btn_add.setIconSize(QSize(14, 14))
        btn_add.clicked.connect(self._add)
        add_row.addWidget(self.name_edit, 1)
        add_row.addWidget(self.color_combo)
        add_row.addWidget(btn_add)
        lay.addLayout(add_row)

        btn_row = QHBoxLayout()
        btn_rename = QPushButton("重命名")
        btn_rename.setObjectName("ghost")
        btn_rename.clicked.connect(self._rename)
        btn_delete = QPushButton("删除")
        btn_delete.setObjectName("ghost")
        btn_delete.clicked.connect(self._delete)
        btn_row.addWidget(btn_rename)
        btn_row.addWidget(btn_delete)
        btn_row.addStretch(1)
        btn_close = QPushButton("完成")
        btn_close.setObjectName("primary")
        btn_close.setIcon(make_icon("check", "#FFFFFF", 14))
        btn_close.setIconSize(QSize(14, 14))
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        lay.addLayout(btn_row)

        self.listw.itemDoubleClicked.connect(lambda _: self._rename())
        self._reload()

    def _reload(self):
        self.listw.clear()
        for u in self.db.list_users():
            n = self.db.stats()["per_user"]
            count = next((x["n"] for x in n if x["id"] == u["id"]), 0)
            item = QListWidgetItem(color_icon(u["color"]), f"{u['name']}　（{count} 张照片）")
            item.setData(Qt.ItemDataRole.UserRole, u)
            self.listw.addItem(item)

    def _add(self):
        name = self.name_edit.text().strip()
        if not name:
            return
        color = self.color_combo.currentData()
        self.db.add_user(name, color)
        self.name_edit.clear()
        self._reload()
        self.changed.emit()

    def _rename(self):
        item = self.listw.currentItem()
        if not item:
            return
        u = item.data(Qt.ItemDataRole.UserRole)
        name, ok = QInputDialog.getText(self, "重命名", "新的显示名称：", text=u["name"])
        if ok and name.strip():
            self.db.rename_user(u["id"], name.strip())
            self._reload()
            self.changed.emit()

    def _delete(self):
        item = self.listw.currentItem()
        if not item:
            return
        u = item.data(Qt.ItemDataRole.UserRole)
        ret = QMessageBox.question(
            self, "删除用户", f"确定删除「{u['name']}」？\n只会移除其照片索引，磁盘上的照片文件不会被删除。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ret == QMessageBox.StandardButton.Yes:
            self.db.delete_user(u["id"])
            self._reload()
            self.changed.emit()


# ======================================================================
# 数据来源
# ======================================================================
class FoldersDialog(AppleDialog):
    changed = Signal()

    def __init__(self, db: Database, scanner: Scanner, parent=None):
        super().__init__(parent)
        self.db = db
        self.scanner = scanner
        self.thread = None
        self.setWindowTitle("数据来源")
        self.setModal(True)
        self.resize(640, 480)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        title = QLabel("数据来源")
        title.setObjectName("dialogTitle")
        lay.addWidget(title)
        hint = QLabel("给每位家人指定照片文件夹，扫描后即可浏览。照片原位保留，不会被移动或复制。")
        hint.setStyleSheet(f"color: {TEXT_SECONDARY};")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.user_combo = AnimatedComboBox()
        self.user_combo.currentIndexChanged.connect(self._reload)
        lay.addWidget(self.user_combo)

        self.listw = QListWidget()
        lay.addWidget(self.listw, 1)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("添加文件夹…")
        btn_add.setObjectName("primary")
        btn_add.setIcon(make_icon("folder-plus", "#FFFFFF", 14))
        btn_add.setIconSize(QSize(14, 14))
        btn_add.clicked.connect(self._add)
        btn_remove = QPushButton("移除")
        btn_remove.setObjectName("ghost")
        btn_remove.clicked.connect(self._remove)
        btn_scan = QPushButton("立即扫描")
        btn_scan.setObjectName("ghost")
        btn_scan.clicked.connect(self._scan_selected)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_remove)
        btn_row.addWidget(btn_scan)
        btn_row.addStretch(1)
        btn_close = QPushButton("完成")
        btn_close.setObjectName("primary")
        btn_close.setIcon(make_icon("check", "#FFFFFF", 14))
        btn_close.setIconSize(QSize(14, 14))
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        lay.addLayout(btn_row)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        lay.addWidget(self.progress)
        self.status = QLabel("")
        self.status.setStyleSheet(f"color: {TEXT_SECONDARY};")
        lay.addWidget(self.status)

        self._reload_users()

    def _reload_users(self):
        self.user_combo.blockSignals(True)
        self.user_combo.clear()
        for u in self.db.list_users():
            self.user_combo.addItem(color_icon(u["color"]), u["name"], u["id"])
        self.user_combo.blockSignals(False)
        self._reload()

    def _reload(self):
        self.listw.clear()
        uid = self.user_combo.currentData()
        if uid is None:
            return
        for f in self.db.list_folders():
            if f["user_id"] != uid:
                continue
            status = {"pending": "待扫描", "scanning": "扫描中", "done": "已扫描", "error": "出错"}.get(
                f["scan_status"], f["scan_status"])
            text = f"{f['path']}　—　{status}"
            if f.get("last_scan_at"):
                text += f"（上次扫描 {f['last_scan_at']}）"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, f)
            self.listw.addItem(item)

    def _add(self):
        uid = self.user_combo.currentData()
        if uid is None:
            QMessageBox.information(self, "提示", "请先在「用户管理」里添加家人。")
            return
        path = QFileDialog.getExistingDirectory(self, "选择照片文件夹")
        if not path:
            return
        folder_id = self.db.add_folder(uid, path)
        self._reload()
        self.changed.emit()
        # 询问是否立即扫描
        ret = QMessageBox.question(
            self, "扫描",
            f"已添加文件夹：\n{path}\n\n是否立即扫描其中的照片？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        if ret == QMessageBox.StandardButton.Yes:
            for i in range(self.listw.count()):
                it = self.listw.item(i)
                if it.data(Qt.ItemDataRole.UserRole)["id"] == folder_id:
                    self.listw.setCurrentItem(it)
                    self._scan_selected()
                    break

    def _remove(self):
        item = self.listw.currentItem()
        if not item:
            return
        f = item.data(Qt.ItemDataRole.UserRole)
        ret = QMessageBox.question(
            self, "移除数据源", f"从软件中移除该文件夹？\n磁盘上的照片文件不会被删除。\n\n{f['path']}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ret == QMessageBox.StandardButton.Yes:
            self.db.delete_folder(f["id"])
            self._reload()
            self.changed.emit()

    def _scan_selected(self):
        item = self.listw.currentItem()
        if not item:
            return
        self._run_scan([item.data(Qt.ItemDataRole.UserRole)["id"]])

    def _run_scan(self, folder_ids):
        if self.thread is not None and self.thread.isRunning():
            return
        self.thread = ScanThread(self.scanner, folder_ids, self)
        self.thread.progress.connect(self._on_progress)
        self.thread.finished_ok.connect(self._on_finished)
        self.thread.failed.connect(self._on_failed)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.thread.start()

    def _on_progress(self, done, total, new, dup):
        if total > 0:
            self.progress.setMaximum(total)
            self.progress.setValue(done)
        self.status.setText(f"正在扫描 {done}/{total}…（新增 {new}，发现重复 {dup}）")

    def _on_finished(self, result):
        self.progress.setVisible(False)
        if result.get("cancelled"):
            self.status.setText("已取消。")
        else:
            self.status.setText(
                f"扫描完成：共 {result.get('total', 0)} 张，新增 {result.get('new', 0)}，"
                f"重复 {result.get('duplicates', 0)}。")
        self._reload()
        self.changed.emit()

    def _on_failed(self, msg):
        self.progress.setVisible(False)
        self.status.setText("扫描失败：" + msg)


# ======================================================================
# 重复照片处理
# ======================================================================
class MemberCard(QFrame):
    """重复组里的一张照片卡片，顶部单选「保留这张」。"""

    def __init__(self, photo: dict, parent=None):
        super().__init__(parent)
        self.setProperty("class", "card")
        self.setStyleSheet(
            "QFrame[class=\"card\"] { background: #F5F5F7; border: 1px solid #E5E5EA;"
            " border-radius: 12px; }")
        self.photo = photo
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        top = QHBoxLayout()
        self.radio = QRadioButton("保留这张")
        top.addWidget(self.radio)
        top.addStretch(1)
        self.badge = QLabel("建议保留")
        self.badge.setStyleSheet(
            f"background: {ACCENT}; color: white; border-radius: 8px;"
            " font-size: 10px; font-weight: 700; padding: 2px 8px;")
        self.badge.setVisible(False)
        top.addWidget(self.badge)
        lay.addLayout(top)

        thumb = load_thumb_pixmap(photo, QSize(180, 140))
        lbl = QLabel()
        lbl.setPixmap(thumb.scaled(180, 140, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation))
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)

        name = QLabel(photo["filename"])
        name.setWordWrap(True)
        name.setStyleSheet("font-weight: 600;")
        lay.addWidget(name)

        info = []
        if photo.get("taken_at"):
            info.append("时间：" + photo["taken_at"])
        if photo.get("lat") is not None:
            info.append(f"定位：{photo['lat']:.4f}, {photo['lng']:.4f}")
        if photo.get("width"):
            info.append(f"{photo['width']}×{photo['height']}")
        kb = (photo.get("file_size") or 0) / 1024
        info.append(f"{kb/1024:.1f} MB" if kb > 1024 else f"{kb:.0f} KB")
        info.append("归属：" + (photo.get("user_name") or "未知"))
        info.append("路径：" + photo["abs_path"])
        info_lbl = QLabel("\n".join(info))
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        lay.addWidget(info_lbl)
        lay.addStretch(1)

    def mark_suggested(self):
        self.badge.setVisible(True)


class DupGroupDialog(AppleDialog):
    changed = Signal()

    def __init__(self, db: Database, trash_dir, parent=None):
        super().__init__(parent)
        self.db = db
        self.trash_dir = trash_dir
        self.setWindowTitle("重复照片")
        self.setModal(True)
        self.resize(1080, 720)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(16)

        # 左：重复组列表
        left = QVBoxLayout()
        title = QLabel("重复照片")
        title.setObjectName("dialogTitle")
        left.addWidget(title)
        hint = QLabel("内容完全相同的照片已归为一组，建议每组保留一张，其余移入回收站（可恢复）。")
        hint.setStyleSheet(f"color: {TEXT_SECONDARY};")
        hint.setWordWrap(True)
        left.addWidget(hint)
        self.group_list = QListWidget()
        self.group_list.setFixedWidth(300)
        self.group_list.currentItemChanged.connect(self._load_group)
        left.addWidget(self.group_list, 1)
        lay.addLayout(left)

        # 右：当前组成员
        right = QVBoxLayout()
        self.group_title = QLabel("")
        self.group_title.setStyleSheet("font-size: 15px; font-weight: 700;")
        right.addWidget(self.group_title)
        self.members_area = QScrollArea()
        self.members_area.setWidgetResizable(True)
        self.members_area.setFrameShape(QFrame.Shape.NoFrame)
        self.members_wrap = QWidget()
        self.members_lay = QVBoxLayout(self.members_wrap)
        self.members_lay.addStretch(1)
        self.members_area.setWidget(self.members_wrap)
        right.addWidget(self.members_area, 1)

        btns = QHBoxLayout()
        self.btn_skip = QPushButton("跳过此组")
        self.btn_skip.setObjectName("ghost")
        self.btn_skip.clicked.connect(self._skip)
        btns.addWidget(self.btn_skip)
        btns.addStretch(1)
        self.btn_resolve = QPushButton("删除其余，保留所选")
        self.btn_resolve.setObjectName("primary")
        self.btn_resolve.setProperty("red", True)
        self.btn_resolve.setStyleSheet(
            f"QPushButton {{ background: {RED}; color: white; border: none;"
            " border-radius: 8px; padding: 8px 18px; font-weight: 600; }"
            " QPushButton:hover { background: #E02E25; }"
            " QPushButton:disabled { background: #F5A9A5; }")
        self.btn_resolve.clicked.connect(self._resolve)
        btns.addWidget(self.btn_resolve)
        right.addLayout(btns)
        lay.addLayout(right, 1)

        self.groups = self.db.pending_dup_groups()
        self._button_group = None
        self._cards = []
        self._reload_list()
        if self.groups:
            self.group_list.setCurrentRow(0)

    def _reload_list(self):
        self.group_list.clear()
        for g in self.groups:
            date = ""
            photos = self.db.dup_group_photos(g["id"])
            if photos and photos[0].get("taken_at"):
                date = photos[0]["taken_at"][:10] + "　"
            item = QListWidgetItem(f"{date}{g['count']} 张完全相同")
            item.setData(Qt.ItemDataRole.UserRole, g)
            self.group_list.addItem(item)

    def _clear_cards(self):
        while self.members_lay.count() > 1:
            item = self.members_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._cards = []

    def _load_group(self, current, _prev=None):
        if not current:
            return
        g = current.data(Qt.ItemDataRole.UserRole)
        self._clear_cards()
        photos = self.db.dup_group_photos(g["id"])
        keep = suggest_keep(self.db, photos)
        self.group_title.setText(
            f"{len(photos)} 张内容完全相同的照片（SHA-256 一致）· 请选择保留哪一张：")
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        for p in photos:
            card = MemberCard(p)
            self._button_group.addButton(card.radio)
            if p["id"] == keep["id"]:
                card.radio.setChecked(True)
                card.mark_suggested()
            self.members_lay.insertWidget(self.members_lay.count() - 1, card)
            self._cards.append(card)
        self._update_resolve_button()

    def _checked_photo_id(self):
        if self._button_group:
            b = self._button_group.checkedButton()
            if b:
                for card in self._cards:
                    if card.radio is b:
                        return card.photo["id"]
        return None

    def _update_resolve_button(self):
        self.btn_resolve.setEnabled(self._checked_photo_id() is not None)

    def _resolve(self):
        item = self.group_list.currentItem()
        if not item:
            return
        g = item.data(Qt.ItemDataRole.UserRole)
        keep_id = self._checked_photo_id()
        if keep_id is None:
            return
        n = g["count"] - 1
        ret = QMessageBox.question(
            self, "确认删除", f"将删除本组中除保留照片外的 {n} 张，"
            f"原文件移入回收站文件夹（可恢复）。\n\n继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ret != QMessageBox.StandardButton.Yes:
            return
        result = resolve_group(self.db, self.trash_dir, g["id"], keep_id)
        failed = len(result["failed"])
        QMessageBox.information(self, "完成",
                                f"已删除 {len(result['removed'])} 张（移入回收站）。"
                                + (f"\n{failed} 张删除失败。" if failed else ""))
        self.groups = self.db.pending_dup_groups()
        self._reload_list()
        self.changed.emit()
        if self.groups:
            self.group_list.setCurrentRow(0)
        else:
            self._clear_cards()
            self.group_title.setText("🎉 没有待处理的重复照片了。")

    def _skip(self):
        row = self.group_list.currentRow()
        if row >= 0:
            self.group_list.takeItem(row)
            del self.groups[row]
            self._reload_list()
            if self.groups:
                self.group_list.setCurrentRow(min(row, len(self.groups) - 1))
            else:
                self._clear_cards()
                self.group_title.setText("🎉 没有待处理的重复照片了。")
