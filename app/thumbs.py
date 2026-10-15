"""缩略图 / 预览图生成与缓存。

- 缩略图：长边 320px JPEG，供缩略图墙使用；
- 预览图：长边 1800px JPEG，供大图浏览窗口使用（原图太大或 HEIC 时加速显示）；
- 缓存目录按 SHA-256 前缀命名，同内容只生成一次。
"""
from pathlib import Path

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

THUMB_SIZE = 320
PREVIEW_SIZE = 1800
THUMB_QUALITY = 82
PREVIEW_QUALITY = 88


def ensure_pil_plugins():
    """注册 HEIC/HEIF 打开器，让 Pillow 直接打开苹果照片。"""
    register_heif_opener()


def _load_image(path):
    im = Image.open(path)
    # GIF 取首帧
    if getattr(im, "is_animated", False):
        im.seek(0)
    return im


def _autorotate(im):
    """按 EXIF 方向摆正，确保缩略图方向与人眼一致。"""
    try:
        return ImageOps.exif_transpose(im)
    except Exception:
        return im


def _save_jpeg(im, out: Path, size: int, quality: int) -> Path:
    im = _autorotate(im)
    im.thumbnail((size, size))
    if im.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        try:
            bg.paste(im, mask=im.convert("RGBA").split()[-1])
        except Exception:
            bg.paste(im.convert("RGB"))
        im = bg
    elif im.mode != "RGB":
        im = im.convert("RGB")
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, "JPEG", quality=quality)
    return out


def generate_thumbs(photo_path, sha256: str, cache_dir: Path) -> dict:
    """生成（或复用）缩略图与预览图，返回 {thumb, preview} 路径。

    任何失败都返回 None 对应项，不抛出。
    """
    cache_dir = Path(cache_dir)
    key = sha256[:16]
    thumb = cache_dir / f"{key}_t.jpg"
    prev = cache_dir / f"{key}_p.jpg"
    result = {"thumb": str(thumb) if thumb.exists() else None,
              "preview": str(prev) if prev.exists() else None}
    try:
        if result["thumb"] is None or result["preview"] is None:
            with _load_image(photo_path) as im:
                if result["thumb"] is None:
                    result["thumb"] = str(_save_jpeg(im, thumb, THUMB_SIZE, THUMB_QUALITY))
                # 原图不大时预览直接用原图，避免重复解码
                if result["preview"] is None:
                    w, h = im.size
                    if max(w, h) <= PREVIEW_SIZE and Path(photo_path).suffix.lower() in (".jpg", ".jpeg"):
                        result["preview"] = str(photo_path)
                    else:
                        result["preview"] = str(_save_jpeg(im, prev, PREVIEW_SIZE, PREVIEW_QUALITY))
    except Exception:
        pass
    return result


def generate_video_thumb(video_path, sha256: str, cache_dir: Path) -> dict:
    """视频缩略图：抓首帧存 JPEG（OpenCV）。失败返回 None 对应项。"""
    cache_dir = Path(cache_dir)
    key = sha256[:16]
    thumb = cache_dir / f"{key}_t.jpg"
    result = {"thumb": str(thumb) if thumb.exists() else None,
              "preview": str(thumb) if thumb.exists() else None}
    if result["thumb"]:
        return result
    try:
        import cv2
        cap = cv2.VideoCapture(str(video_path))
        ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            return result
        h, w = frame.shape[:2]
        scale = THUMB_SIZE / max(w, h)
        if scale < 1:
            frame = cv2.resize(frame, (max(1, int(w * scale)), max(1, int(h * scale))),
                               interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        thumb.parent.mkdir(parents=True, exist_ok=True)
        img.save(thumb, "JPEG", quality=THUMB_QUALITY)
        result = {"thumb": str(thumb), "preview": str(thumb)}
    except Exception:
        pass
    return result


def extract_video_meta(video_path) -> dict:
    """视频元数据：宽高、时长（秒）。拍摄时间由调用方用文件时间回退。"""
    meta = {"width": None, "height": None, "duration": None}
    try:
        import cv2
        cap = cv2.VideoCapture(str(video_path))
        if cap.isOpened():
            meta["width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or None
            meta["height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or None
            fps = cap.get(cv2.CAP_PROP_FPS) or 0
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            if fps > 0 and frames > 0:
                meta["duration"] = round(frames / fps, 1)
        cap.release()
    except Exception:
        pass
    return meta
