"""SQLite 数据库访问层。每个线程独立连接，WAL 模式支持并发读写。"""
import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    color      TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS folders (
    id           INTEGER PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    path         TEXT NOT NULL,
    scan_status  TEXT NOT NULL DEFAULT 'pending',
    last_scan_at TEXT,
    UNIQUE(path)
);

CREATE TABLE IF NOT EXISTS photos (
    id              INTEGER PRIMARY KEY,
    folder_id       INTEGER NOT NULL REFERENCES folders(id),
    user_id         INTEGER NOT NULL REFERENCES users(id),
    abs_path        TEXT NOT NULL UNIQUE,
    filename        TEXT NOT NULL,
    ext             TEXT NOT NULL,
    content_sha256  TEXT NOT NULL,
    file_size       INTEGER,
    file_mtime      INTEGER,
    width           INTEGER,
    height          INTEGER,
    orientation     INTEGER,
    taken_at        TEXT,
    timezone_offset INTEGER,
    lat             REAL,
    lng             REAL,
    altitude        REAL,
    camera_make     TEXT,
    camera_model    TEXT,
    thumb_path      TEXT,
    preview_path    TEXT,
    is_favorite     INTEGER DEFAULT 0,
    indexed_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_photos_user  ON photos(user_id);
CREATE INDEX IF NOT EXISTS idx_photos_sha   ON photos(content_sha256);
CREATE INDEX IF NOT EXISTS idx_photos_taken ON photos(taken_at);
CREATE INDEX IF NOT EXISTS idx_photos_geo   ON photos(lat, lng);

CREATE TABLE IF NOT EXISTS duplicate_groups (
    id            INTEGER PRIMARY KEY,
    hash_value    TEXT NOT NULL UNIQUE,
    status        TEXT NOT NULL DEFAULT 'pending',
    keep_photo_id INTEGER,
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS duplicate_items (
    group_id INTEGER NOT NULL REFERENCES duplicate_groups(id),
    photo_id INTEGER NOT NULL REFERENCES photos(id),
    PRIMARY KEY (group_id, photo_id)
);

CREATE TABLE IF NOT EXISTS trash (
    id            INTEGER PRIMARY KEY,
    filename      TEXT NOT NULL,
    original_path TEXT NOT NULL,
    trash_path    TEXT NOT NULL,
    thumb_path    TEXT,
    user_name     TEXT,
    taken_at      TEXT,
    file_size     INTEGER,
    folder_id     INTEGER,
    deleted_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._conn_registry = set()
        self._registry_lock = threading.Lock()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
            with self._registry_lock:
                self._conn_registry.add(conn)
        return conn

    def init(self):
        with self._conn():
            self._conn().executescript(SCHEMA)
            self._migrate()

    def _migrate(self):
        """为旧库补充新字段（幂等）。"""
        cols = {r[1] for r in self._conn().execute("PRAGMA table_info(photos)")}
        if "duration" not in cols:
            self._conn().execute("ALTER TABLE photos ADD COLUMN duration REAL")
        if "place" not in cols:
            self._conn().execute("ALTER TABLE photos ADD COLUMN place TEXT")
            self._conn().execute("CREATE INDEX IF NOT EXISTS idx_photos_place ON photos(place)")

    def close(self):
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def close_all(self):
        """关闭所有线程的连接（扫描完成后调用，释放文件句柄）。"""
        for t in list(self._conn_registry):
            try:
                t.close()
            except Exception:
                pass
        self._conn_registry.clear()
        self.close()

    # ---------- 用户 ----------
    def add_user(self, name: str, color: str = "#007AFF") -> int:
        with self._conn() as c:
            cur = c.execute("INSERT INTO users(name, color) VALUES (?, ?)", (name, color))
            return cur.lastrowid

    def list_users(self) -> list:
        cur = self._conn().execute("SELECT * FROM users ORDER BY id")
        return [dict(r) for r in cur.fetchall()]

    def rename_user(self, user_id: int, name: str):
        with self._conn() as c:
            c.execute("UPDATE users SET name=? WHERE id=?", (name, user_id))

    def set_user_color(self, user_id: int, color: str):
        with self._conn() as c:
            c.execute("UPDATE users SET color=? WHERE id=?", (color, user_id))

    def delete_user(self, user_id: int):
        """删除用户及其索引数据（不动磁盘上的原图）。"""
        with self._conn() as c:
            photo_ids = [r[0] for r in c.execute(
                "SELECT id FROM photos WHERE user_id=?", (user_id,))]
            c.execute("DELETE FROM folders WHERE user_id=?", (user_id,))
            c.execute("DELETE FROM photos WHERE user_id=?", (user_id,))
            for pid in photo_ids:
                c.execute("DELETE FROM duplicate_items WHERE photo_id=?", (pid,))
            # 清理空组
            c.execute("""DELETE FROM duplicate_groups
                         WHERE id NOT IN (SELECT DISTINCT group_id FROM duplicate_items)""")

    # ---------- 数据来源文件夹 ----------
    def add_folder(self, user_id: int, path: str) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT OR IGNORE INTO folders(user_id, path) VALUES (?, ?)", (user_id, path))
            if cur.lastrowid == 0:
                row = c.execute("SELECT id FROM folders WHERE path=?", (path,)).fetchone()
                return row["id"]
            return cur.lastrowid

    def list_folders(self) -> list:
        cur = self._conn().execute(
            """SELECT f.*, u.name AS user_name FROM folders f
               LEFT JOIN users u ON u.id = f.user_id ORDER BY f.id""")
        return [dict(r) for r in cur.fetchall()]

    def get_folder(self, folder_id: int):
        row = self._conn().execute("SELECT * FROM folders WHERE id=?", (folder_id,)).fetchone()
        return dict(row) if row else None

    def delete_folder(self, folder_id: int):
        with self._conn() as c:
            photo_ids = [r[0] for r in c.execute(
                "SELECT id FROM photos WHERE folder_id=?", (folder_id,))]
            c.execute("DELETE FROM photos WHERE folder_id=?", (folder_id,))
            c.execute("DELETE FROM folders WHERE id=?", (folder_id,))
            for pid in photo_ids:
                c.execute("DELETE FROM duplicate_items WHERE photo_id=?", (pid,))
            c.execute("""DELETE FROM duplicate_groups
                         WHERE id NOT IN (SELECT DISTINCT group_id FROM duplicate_items)""")

    def set_folder_status(self, folder_id: int, status: str, last_scan: bool = False):
        sql = "UPDATE folders SET scan_status=?"
        if last_scan:
            sql += ", last_scan_at=datetime('now','localtime')"
        with self._conn() as c:
            c.execute(sql + " WHERE id=?", (status, folder_id))

    # ---------- 照片 ----------
    def photo_unchanged(self, abs_path: str, size: int, mtime: int) -> bool:
        row = self._conn().execute(
            "SELECT 1 FROM photos WHERE abs_path=? AND file_size=? AND file_mtime=?",
            (abs_path, size, mtime)).fetchone()
        return row is not None

    def get_photo_by_path(self, abs_path: str):
        row = self._conn().execute(
            "SELECT * FROM photos WHERE abs_path=?", (abs_path,)).fetchone()
        return dict(row) if row else None

    def upsert_photo(self, p: dict):
        """插入新照片，或更新已存在（内容变化）的照片。返回 (photo_id, is_new)。"""
        with self._conn() as c:
            old = c.execute("SELECT id, content_sha256 FROM photos WHERE abs_path=?",
                            (p["abs_path"],)).fetchone()
            if old is None:
                cur = c.execute("""
                    INSERT INTO photos(folder_id, user_id, abs_path, filename, ext,
                        content_sha256, file_size, file_mtime, width, height, orientation,
                        taken_at, timezone_offset, lat, lng, altitude,
                        camera_make, camera_model, thumb_path, preview_path, duration, place)
                    VALUES (:folder_id, :user_id, :abs_path, :filename, :ext,
                        :content_sha256, :file_size, :file_mtime, :width, :height, :orientation,
                        :taken_at, :timezone_offset, :lat, :lng, :altitude,
                        :camera_make, :camera_model, :thumb_path, :preview_path, :duration,
                        :place)""", p)
                return cur.lastrowid, True
            c.execute("""
                UPDATE photos SET content_sha256=:content_sha256, file_size=:file_size,
                    file_mtime=:file_mtime, width=:width, height=:height, orientation=:orientation,
                    taken_at=:taken_at, timezone_offset=:timezone_offset, lat=:lat, lng=:lng,
                    altitude=:altitude, camera_make=:camera_make, camera_model=:camera_model,
                    thumb_path=:thumb_path, preview_path=:preview_path, duration=:duration,
                    place=:place
                WHERE abs_path=:abs_path""", p)
            return old["id"], False

    # ---------- 地点 ----------
    def places_list(self) -> list:
        """已入库照片涉及的地点及数量（按省份归并展示用）。"""
        rows = self._conn().execute(
            """SELECT place, COUNT(*) AS n FROM photos
               WHERE place IS NOT NULL AND place <> ''
               GROUP BY place ORDER BY n DESC""").fetchall()
        return [dict(r) for r in rows]

    def photos_missing_place(self) -> list:
        """有 GPS 但还没反查地点的照片（用于回填）。"""
        rows = self._conn().execute(
            """SELECT id, lat, lng FROM photos
               WHERE lat IS NOT NULL AND lng IS NOT NULL
                 AND (place IS NULL OR place = '')""").fetchall()
        return [dict(r) for r in rows]

    def set_place(self, photo_id: int, place: str):
        with self._conn() as c:
            c.execute("UPDATE photos SET place=? WHERE id=?", (place, photo_id))

    # ---------- 回收站 ----------
    def add_trash(self, entry: dict) -> int:
        with self._conn() as c:
            cur = c.execute("""
                INSERT INTO trash(filename, original_path, trash_path, thumb_path,
                                  user_name, taken_at, file_size, folder_id)
                VALUES (:filename, :original_path, :trash_path, :thumb_path,
                        :user_name, :taken_at, :file_size, :folder_id)""", entry)
            return cur.lastrowid

    def list_trash(self) -> list:
        rows = self._conn().execute(
            "SELECT * FROM trash ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

    def get_trash(self, trash_id: int):
        row = self._conn().execute("SELECT * FROM trash WHERE id=?", (trash_id,)).fetchone()
        return dict(row) if row else None

    def delete_trash_row(self, trash_id: int):
        with self._conn() as c:
            c.execute("DELETE FROM trash WHERE id=?", (trash_id,))

    def clear_trash_rows(self):
        with self._conn() as c:
            c.execute("DELETE FROM trash")

    def photo_ids_by_hash(self, sha256: str) -> list:
        rows = self._conn().execute(
            "SELECT id FROM photos WHERE content_sha256=?", (sha256,)).fetchall()
        return [r["id"] for r in rows]

    def get_photo(self, photo_id: int):
        row = self._conn().execute("SELECT * FROM photos WHERE id=?", (photo_id,)).fetchone()
        return dict(row) if row else None

    def delete_photo_row(self, photo_id: int):
        with self._conn() as c:
            c.execute("DELETE FROM duplicate_items WHERE photo_id=?", (photo_id,))
            c.execute("DELETE FROM photos WHERE id=?", (photo_id,))
            c.execute("""DELETE FROM duplicate_groups
                         WHERE id NOT IN (SELECT DISTINCT group_id FROM duplicate_items)""")

    def set_favorite(self, photo_id: int, fav: bool):
        with self._conn() as c:
            c.execute("UPDATE photos SET is_favorite=? WHERE id=?", (1 if fav else 0, photo_id))

    def query_photos(self, user_id=None, year=None, month=None, ext=None,
                     dup_only=False, has_gps=None, no_time=False, fav_only=False,
                     video_only=False, place=None, date_from=None, date_to=None,
                     text=None, limit=None) -> list:
        sql = """SELECT p.*, u.name AS user_name, u.color AS user_color
                 FROM photos p LEFT JOIN users u ON u.id = p.user_id WHERE 1=1"""
        args = []
        if user_id:
            sql += " AND p.user_id=?"
            args.append(user_id)
        if year:
            sql += " AND strftime('%Y', p.taken_at)=?"
            args.append(str(year))
        if month:
            sql += " AND strftime('%m', p.taken_at)=?"
            args.append(f"{month:02d}")
        if ext:
            sql += " AND p.ext=?"
            args.append(ext)
        if dup_only:
            sql += """ AND p.id IN (
                SELECT i.photo_id FROM duplicate_items i
                WHERE i.group_id IN (
                    SELECT g.id FROM duplicate_groups g
                    JOIN duplicate_items i2 ON i2.group_id = g.id
                    WHERE g.status = 'pending'
                    GROUP BY g.id HAVING COUNT(i2.photo_id) >= 2))"""
        if has_gps is True:
            sql += " AND p.lat IS NOT NULL"
        elif has_gps is False:
            sql += " AND p.lat IS NULL"
        if fav_only:
            sql += " AND p.is_favorite = 1"
        if video_only:
            sql += " AND p.duration IS NOT NULL"
        if place:
            sql += " AND p.place = ?"
            args.append(place)
        if date_from:
            sql += " AND substr(COALESCE(p.taken_at, '9999'), 1, 10) >= ?"
            args.append(date_from)
        if date_to:
            sql += " AND substr(COALESCE(p.taken_at, '9999'), 1, 10) <= ?"
            args.append(date_to)
        if no_time:
            sql += " AND p.taken_at IS NULL"
        if text:
            sql += " AND p.filename LIKE ?"
            args.append(f"%{text}%")
        sql += " ORDER BY COALESCE(p.taken_at, '9999') ASC, p.filename ASC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = self._conn().execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict:
        c = self._conn()
        total = c.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
        no_gps = c.execute("SELECT COUNT(*) FROM photos WHERE lat IS NULL").fetchone()[0]
        no_time = c.execute("SELECT COUNT(*) FROM photos WHERE taken_at IS NULL").fetchone()[0]
        pend = c.execute(
            """SELECT COUNT(*) FROM (
                   SELECT g.id FROM duplicate_groups g
                   JOIN duplicate_items i ON i.group_id = g.id
                   WHERE g.status = 'pending'
                   GROUP BY g.id HAVING COUNT(i.photo_id) >= 2)""").fetchone()[0]
        per_user = [dict(r) for r in c.execute(
            """SELECT u.id, u.name, u.color, COUNT(p.id) AS n
               FROM users u LEFT JOIN photos p ON p.user_id=u.id
               GROUP BY u.id ORDER BY u.id""")]
        return {"total": total, "no_gps": no_gps, "no_time": no_time,
                "pending_dups": pend, "per_user": per_user}

    # ---------- 重复组 ----------
    def remove_missing_in_folder(self, folder_id: int, existing_paths: set) -> int:
        """删除某数据源中磁盘上已不存在的记录，返回删除条数。"""
        rows = self._conn().execute(
            "SELECT id, abs_path FROM photos WHERE folder_id=?", (folder_id,)).fetchall()
        gone = [r["id"] for r in rows if r["abs_path"] not in existing_paths]
        if not gone:
            return 0
        with self._conn() as c:
            for pid in gone:
                c.execute("DELETE FROM duplicate_items WHERE photo_id=?", (pid,))
                c.execute("DELETE FROM photos WHERE id=?", (pid,))
        return len(gone)

    def cleanup_empty_dup_groups(self) -> int:
        """清理没有任何成员的重复组。"""
        with self._conn() as c:
            cur = c.execute("""DELETE FROM duplicate_groups
                               WHERE id NOT IN (SELECT DISTINCT group_id FROM duplicate_items)""")
            return cur.rowcount or 0

    def ensure_dup_group(self, sha256: str) -> int:
        with self._conn() as c:
            c.execute("INSERT OR IGNORE INTO duplicate_groups(hash_value) VALUES (?)", (sha256,))
            row = c.execute("SELECT id FROM duplicate_groups WHERE hash_value=?", (sha256,)).fetchone()
            return row["id"]

    def add_dup_item(self, group_id: int, photo_id: int):
        with self._conn() as c:
            c.execute("INSERT OR IGNORE INTO duplicate_items(group_id, photo_id) VALUES (?, ?)",
                      (group_id, photo_id))

    def remove_dup_items_for_photo(self, photo_id: int):
        with self._conn() as c:
            c.execute("DELETE FROM duplicate_items WHERE photo_id=?", (photo_id,))

    def pending_dup_groups(self) -> list:
        rows = self._conn().execute("""
            SELECT g.id, g.hash_value, COUNT(i.photo_id) AS n,
                   GROUP_CONCAT(i.photo_id) AS photo_ids
            FROM duplicate_groups g
            JOIN duplicate_items i ON i.group_id = g.id
            WHERE g.status='pending'
            GROUP BY g.id HAVING n >= 2
            ORDER BY g.id DESC""").fetchall()
        out = []
        for r in rows:
            out.append({"id": r["id"], "hash": r["hash_value"], "count": r["n"],
                        "photo_ids": [int(x) for x in r["photo_ids"].split(",")]})
        return out

    def dup_group_photos(self, group_id: int) -> list:
        rows = self._conn().execute("""
            SELECT p.*, u.name AS user_name FROM duplicate_items i
            JOIN photos p ON p.id = i.photo_id
            LEFT JOIN users u ON u.id = p.user_id
            WHERE i.group_id=?""", (group_id,)).fetchall()
        return [dict(r) for r in rows]

    def resolve_dup_group(self, group_id: int, keep_photo_id: int):
        with self._conn() as c:
            c.execute("UPDATE duplicate_groups SET status='resolved', keep_photo_id=? WHERE id=?",
                      (keep_photo_id, group_id))
