"""文件夹扫描：遍历图片与视频、计算哈希、提取元数据、生成缩略图、入库、重复分组。

- 原地索引，不复制不移动原文件；
- 增量扫描：路径 + 大小 + 修改时间未变则跳过；
- 多线程处理（哈希/缩略图是 IO 与解码密集操作）。
"""
import datetime as dt
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .db import Database
from .exif_reader import extract_metadata
from .hashing import sha256_file
from .thumbs import extract_video_meta, generate_thumbs, generate_video_thumb

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif",
              ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_EXTS = {".mov", ".mp4", ".m4v", ".avi", ".mkv", ".wmv", ".webm", ".3gp"}
MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS


def extract_quicktime_meta(path) -> dict:
    """iPhone 视频的 QuickTime 元数据：GPS（ISO6709）与拍摄时间（creationdate）。

    扫描文件首尾各 8MB（元数据通常位于头部或尾部），失败返回空值。
    """
    result = {"lat": None, "lng": None, "altitude": None,
              "taken_at": None, "timezone_offset": None}
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            head = f.read(8 * 1024 * 1024)
            tail = b""
            if size > 8 * 1024 * 1024:
                f.seek(max(0, size - 8 * 1024 * 1024))
                tail = f.read(8 * 1024 * 1024)
        blob = head + tail
        # GPS：ISO6709 坐标值本身，如 "+23.0272+113.3333+009.835/"
        m = re.search(
            rb"([+-]\d{1,3}\.\d{2,8})([+-]\d{1,3}\.\d{2,8})([+-]\d{1,4}\.\d{1,8})?/",
            blob)
        if m:
            result["lat"] = float(m.group(1))
            result["lng"] = float(m.group(2))
            if m.group(3):
                result["altitude"] = float(m.group(3))
        # 拍摄时间：creationdate 值，如 "2018-06-17T14:46:38+0800"
        m2 = re.search(
            rb"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:?\d{2})",
            blob)
        if m2:
            s = m2.group(1).decode()
            result["taken_at"] = s[:19].replace("T", " ")
            tz = s[19:]
            if len(tz) >= 5:
                off = int(tz[1:3]) * 60 + int(tz[4:6])
                result["timezone_offset"] = -off if tz[0] == "-" else off
    except Exception:
        pass
    return result


class ScanError(Exception):
    pass


class Scanner:
    def __init__(self, db: Database, thumb_dir: Path, workers: int = 6):
        self.db = db
        self.thumb_dir = Path(thumb_dir)
        self.thumb_dir.mkdir(parents=True, exist_ok=True)
        self.workers = workers
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def scan_folder(self, folder_id: int, on_progress=None) -> dict:
        """扫描一个数据源。on_progress(done, total, new, dup) 在每张处理完后回调。"""
        self._cancel.clear()
        folder = self.db.get_folder(folder_id)
        if not folder:
            raise ScanError("数据源不存在")
        root = Path(folder["path"])
        if not root.is_dir():
            self.db.set_folder_status(folder_id, "error")
            raise ScanError(f"文件夹不存在：{root}")

        self.db.set_folder_status(folder_id, "scanning")
        try:
            files = []
            for dirpath, dirnames, filenames in os.walk(root):
                if self._cancel.is_set():
                    return {"cancelled": True}
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                for fn in filenames:
                    p = Path(dirpath) / fn
                    if p.suffix.lower() in MEDIA_EXTS:
                        files.append(p)

            pending = []
            for p in files:
                try:
                    st = p.stat()
                except OSError:
                    continue
                if self.db.photo_unchanged(str(p), st.st_size, int(st.st_mtime)):
                    continue
                pending.append((p, st.st_size, int(st.st_mtime)))

            total = len(files)
            done = total - len(pending)
            new_count, dup_count = 0, 0
            if on_progress and done:
                on_progress(done, total, new_count, dup_count)

            if pending:
                with ThreadPoolExecutor(max_workers=self.workers) as ex:
                    futs = {ex.submit(self._process_one, folder, p, size, mtime): p
                            for p, size, mtime in pending}
                    for fut in as_completed(futs):
                        if self._cancel.is_set():
                            for f in futs:
                                f.cancel()
                            return {"cancelled": True}
                        try:
                            n, d = fut.result()
                            new_count += n
                            dup_count += d
                        except Exception:
                            pass  # 单张失败不影响整体
                        done += 1
                        if on_progress:
                            on_progress(done, total, new_count, dup_count)
            self.db.set_folder_status(folder_id, "done", last_scan=True)
            return {"total": total, "new": new_count, "duplicates": dup_count}
        finally:
            if not self._cancel.is_set():
                self.db.set_folder_status(folder_id, "done", last_scan=True)

    def _process_one(self, folder, path: Path, size: int, mtime: int) -> tuple:
        """处理单个媒体文件（图片或视频）。返回 (new_count, dup_count)。"""
        p = str(path)
        sha = sha256_file(p)
        ext = path.suffix.lower()
        if ext in VIDEO_EXTS:
            meta = extract_video_meta(p)
            qt = extract_quicktime_meta(p)
            meta.update({"orientation": None, "camera_make": None,
                         "camera_model": None})
            # 优先 QuickTime 拍摄时间/GPS；回退文件修改时间
            if qt.get("taken_at"):
                meta["taken_at"] = qt["taken_at"]
                meta["timezone_offset"] = qt.get("timezone_offset")
            else:
                meta["taken_at"] = dt.datetime.fromtimestamp(mtime).strftime(
                    "%Y-%m-%d %H:%M:%S")
                meta["timezone_offset"] = None
            meta["lat"] = qt.get("lat")
            meta["lng"] = qt.get("lng")
            meta["altitude"] = qt.get("altitude")
            thumbs = generate_video_thumb(p, sha, self.thumb_dir)
        else:
            meta = extract_metadata(p)
            thumbs = generate_thumbs(p, sha, self.thumb_dir)
        row = {
            "folder_id": folder["id"],
            "user_id": folder["user_id"],
            "abs_path": p,
            "filename": path.name,
            "ext": ext,
            "content_sha256": sha,
            "file_size": size,
            "file_mtime": mtime,
            "width": meta["width"],
            "height": meta["height"],
            "orientation": meta["orientation"],
            "taken_at": meta["taken_at"],
            "timezone_offset": meta["timezone_offset"],
            "lat": meta["lat"],
            "lng": meta["lng"],
            "altitude": meta["altitude"],
            "camera_make": meta["camera_make"],
            "camera_model": meta["camera_model"],
            "thumb_path": thumbs["thumb"],
            "preview_path": thumbs["preview"],
            "duration": meta.get("duration"),
        }
        photo_id, is_new = self.db.upsert_photo(row)
        if not is_new:
            # 内容变化：旧哈希上的重复关系作废
            self.db.remove_dup_items_for_photo(photo_id)

        # 精确去重：同哈希归组
        gid = self.db.ensure_dup_group(sha)
        self.db.add_dup_item(gid, photo_id)
        same = [i for i in self.db.photo_ids_by_hash(sha) if i != photo_id]
        dup_count = 1 if same else 0
        return (1 if is_new else 0), dup_count
