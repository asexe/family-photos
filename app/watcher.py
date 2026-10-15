"""数据源文件夹监控：目录内容变化后（防抖）自动触发增量扫描。

QFileSystemWatcher 不支持递归，因此这里在每次扫描后重新收集所有子目录并注册监听。
"""
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal

MAX_WATCH_DIRS = 2000      # 监听目录上限，避免句柄过多
DEFAULT_DEBOUNCE_MS = 4000  # 变化后等待安静 4 秒再扫描（拷贝大文件时不会反复触发）


class FolderWatcher(QObject):
    """监听数据源文件夹，发现变化后发出需要重扫的 folder_id 列表。"""

    changed = Signal(list)

    def __init__(self, parent=None, debounce_ms: int = DEFAULT_DEBOUNCE_MS):
        super().__init__(parent)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._on_dir_changed)
        self._folders = []          # [(folder_id, Path)]
        self._dirty = set()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(debounce_ms)
        self._timer.timeout.connect(self._flush)
        self.enabled = True

    # ---------- 配置 ----------
    def set_folders(self, folders):
        """folders: [(folder_id, path_str)]，设置后立即（重新）注册监听目录。"""
        self._folders = [(fid, Path(p)) for fid, p in folders]
        self._dirty.clear()
        self.refresh_dirs()

    def refresh_dirs(self):
        """重新收集所有子目录并更新监听列表（扫描完成后调用）。"""
        dirs = []
        for _fid, root in self._folders:
            if not root.is_dir():
                continue
            dirs.append(str(root))
            try:
                for p in root.rglob("*"):
                    if p.is_dir() and not p.name.startswith("."):
                        dirs.append(str(p))
                        if len(dirs) >= MAX_WATCH_DIRS:
                            break
            except Exception:
                pass
            if len(dirs) >= MAX_WATCH_DIRS:
                break

        current = set(self._watcher.directories())
        want = set(dirs)
        remove = [d for d in current - want]
        add = [d for d in want - current]
        if remove:
            self._watcher.removePaths(remove)
        if add:
            self._watcher.addPaths(add)

    def stop(self):
        self.enabled = False
        self._timer.stop()
        dirs = self._watcher.directories()
        if dirs:
            self._watcher.removePaths(dirs)

    # ---------- 事件 ----------
    def _on_dir_changed(self, path):
        if not self.enabled:
            return
        p = Path(path)
        for fid, root in self._folders:
            try:
                p.relative_to(root)
                self._dirty.add(fid)
                break
            except ValueError:
                continue
        if self._dirty:
            self._timer.start()      # 防抖：连续变化只在安静后触发一次

    def _flush(self):
        if not self._dirty:
            return
        ids = sorted(self._dirty)
        self._dirty.clear()
        self.changed.emit(ids)
