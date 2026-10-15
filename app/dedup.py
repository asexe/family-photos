"""重复照片：归组、建议保留、确认删除（移入内置回收站，可恢复）。"""
import shutil
import time
from pathlib import Path

from .db import Database


def suggest_keep(db: Database, photos: list) -> dict:
    """从一组完全相同的照片中建议保留哪张：
    优先级：有 GPS > 分辨率更高 > 文件更大 > 时间更早。返回照片字典。
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


def move_to_trash(trash_dir: Path, photo: dict) -> Path:
    """把原图移入内置回收站（同盘为秒级移动）。失败时抛出。"""
    trash_dir = Path(trash_dir)
    trash_dir.mkdir(parents=True, exist_ok=True)
    src = Path(photo["abs_path"])
    if not src.exists():
        return trash_dir
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dst = trash_dir / f"{stamp}_{photo['filename']}"
    # 同名冲突时加序号
    n = 1
    while dst.exists():
        dst = trash_dir / f"{stamp}_{n}_{photo['filename']}"
        n += 1
    shutil.move(str(src), str(dst))
    return dst


def resolve_group(db: Database, trash_dir: Path, group_id: int, keep_photo_id: int) -> dict:
    """确认重复组：保留 keep_photo_id，其余移入回收站并从索引移除。"""
    photos = db.dup_group_photos(group_id)
    removed, failed = [], []
    for p in photos:
        if p["id"] == keep_photo_id:
            continue
        try:
            dst = move_to_trash(trash_dir, p)
            db.delete_photo_row(p["id"])
            removed.append({"filename": p["filename"], "trash": str(dst)})
        except Exception as e:
            failed.append({"filename": p["filename"], "error": str(e)})
    db.resolve_dup_group(group_id, keep_photo_id)
    return {"removed": removed, "failed": failed}


def single_delete(db: Database, trash_dir: Path, photo_id: int) -> dict:
    """删除单张：移入回收站并从索引移除。"""
    p = db.get_photo(photo_id)
    if not p:
        return {"removed": [], "failed": []}
    try:
        dst = move_to_trash(trash_dir, p)
        db.delete_photo_row(photo_id)
        return {"removed": [{"filename": p["filename"], "trash": str(dst)}], "failed": []}
    except Exception as e:
        return {"removed": [], "failed": [{"filename": p["filename"], "error": str(e)}]}


def restore_from_trash(db: Database, trash_dir: Path, photo: dict) -> bool:
    """把回收站里的文件移回原路径（原路径记录在 photo 中）。"""
    src = Path(photo["abs_path"])
    dst = trash_dir / photo["filename"]
    if not dst.exists():
        return False
    src.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(dst), str(src))
    return True
