"""删除与回收站：移入回收站、恢复、彻底删除、重复组处理。

删除从不直接抹掉文件：一律移动到 data/trash/ 并在 trash 表登记，
用户可在「回收站」里预览、恢复或彻底删除。
"""
import shutil
import time
from pathlib import Path

from .db import Database


def suggest_keep(db: Database, photos: list) -> dict:
    """从一组完全相同的照片中建议保留哪张：
    优先级：有 GPS > 分辨率更高 > 文件更大。返回照片字典。
    """
    def score(p):
        s = 0.0
        if p.get("lat") is not None and p.get("lng") is not None:
            s += 1e12
        w, h = p.get("width") or 0, p.get("height") or 0
        s += (w * h)
        s += (p.get("file_size") or 0) * 1e-3
        return s
    return max(photos, key=score)


def _move_file(trash_dir: Path, src: Path) -> Path:
    """把文件移入回收站目录（同名冲突自动加序号），返回新路径。"""
    trash_dir = Path(trash_dir)
    trash_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dst = trash_dir / f"{stamp}_{src.name}"
    n = 1
    while dst.exists():
        dst = trash_dir / f"{stamp}_{n}_{src.name}"
        n += 1
    shutil.move(str(src), str(dst))
    return dst


def trash_photo(db: Database, trash_dir: Path, photo: dict) -> dict:
    """把一张照片/视频移入回收站并登记，同时从索引移除。返回登记信息。"""
    src = Path(photo["abs_path"])
    if not src.exists():
        db.delete_photo_row(photo["id"])
        return {"missing": True, "filename": photo["filename"]}
    dst = _move_file(trash_dir, src)
    db.add_trash({
        "filename": photo["filename"],
        "original_path": str(src),
        "trash_path": str(dst),
        "thumb_path": photo.get("thumb_path"),
        "user_name": photo.get("user_name"),
        "taken_at": photo.get("taken_at"),
        "file_size": photo.get("file_size"),
        "folder_id": photo.get("folder_id"),
    })
    db.delete_photo_row(photo["id"])
    return {"missing": False, "filename": photo["filename"], "trash": str(dst)}


def resolve_group(db: Database, trash_dir: Path, group_id: int, keep_photo_id: int) -> dict:
    """确认重复组：保留 keep_photo_id，其余移入回收站并从索引移除。"""
    photos = db.dup_group_photos(group_id)
    removed, failed = [], []
    for p in photos:
        if p["id"] == keep_photo_id:
            continue
        try:
            info = trash_photo(db, trash_dir, p)
            removed.append({"filename": p["filename"], "trash": info.get("trash", "")})
        except Exception as e:  # noqa: BLE001
            failed.append({"filename": p["filename"], "error": str(e)})
    db.resolve_dup_group(group_id, keep_photo_id)
    return {"removed": removed, "failed": failed}


def single_delete(db: Database, trash_dir: Path, photo_id: int) -> dict:
    """删除单张：移入回收站并从索引移除。"""
    p = db.get_photo(photo_id)
    if not p:
        return {"removed": [], "failed": []}
    try:
        info = trash_photo(db, trash_dir, p)
        return {"removed": [{"filename": p["filename"], "trash": info.get("trash", "")}],
                "failed": []}
    except Exception as e:  # noqa: BLE001
        return {"removed": [], "failed": [{"filename": p["filename"], "error": str(e)}]}


def restore(db: Database, trash_id: int) -> tuple:
    """把回收站里的文件移回原位置。返回 (是否成功, 说明文字)。"""
    row = db.get_trash(trash_id)
    if not row:
        return False, "记录不存在"
    src = Path(row["trash_path"])
    dst = Path(row["original_path"])
    if not src.exists():
        db.delete_trash_row(trash_id)
        return False, "回收站里的文件已不存在，已移除记录"
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            return False, f"原位置已有同名文件：{dst.name}"
        shutil.move(str(src), str(dst))
    except Exception as e:  # noqa: BLE001
        return False, f"恢复失败：{e}"
    db.delete_trash_row(trash_id)
    return True, f"已恢复到 {dst}"


def purge(db: Database, trash_id: int) -> tuple:
    """彻底删除回收站中的一项。"""
    row = db.get_trash(trash_id)
    if not row:
        return False, "记录不存在"
    try:
        p = Path(row["trash_path"])
        if p.exists():
            p.unlink()
    except Exception as e:  # noqa: BLE001
        return False, f"删除文件失败：{e}"
    db.delete_trash_row(trash_id)
    return True, "已彻底删除"


def purge_all(db: Database) -> int:
    """清空回收站，返回删除的文件数。"""
    rows = db.list_trash()
    done = 0
    for row in rows:
        try:
            p = Path(row["trash_path"])
            if p.exists():
                p.unlink()
            done += 1
        except Exception:
            pass
    db.clear_trash_rows()
    return done


def restore_from_trash(db: Database, trash_dir: Path, photo: dict) -> bool:
    """兼容旧调用：按文件名在回收站里找同名文件并移回原路径。"""
    src = Path(photo["abs_path"])
    dst = Path(trash_dir) / photo["filename"]
    if not dst.exists():
        return False
    src.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(dst), str(src))
    return True
