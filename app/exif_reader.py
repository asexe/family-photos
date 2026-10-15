"""读取图片 EXIF：拍摄时间、GPS、方向、相机信息。

支持 JPG / PNG / HEIC / HEIF / WEBP 等 Pillow 能打开的格式
（HEIC 需先 register_heif_opener()，见 thumbs.py）。
任何单张图片解析失败都不会抛出异常，返回空值字段。
"""
import datetime as dt
from typing import Any, Optional

TAG_DATETIME_ORIGINAL = 0x9003   # 36867 拍摄时间
TAG_DATETIME = 0x0132            # 306 修改时间（回退用）
TAG_ORIENTATION = 0x0112         # 274 方向
TAG_OFFSET_TIME_ORIGINAL = 0x9011  # 36881 原时区偏移（iPhone 会写入）
TAG_MAKE = 0x010F                # 271 相机厂商
TAG_MODEL = 0x0110               # 272 相机型号

GPS_IFD = 0x8825
GPS_LAT_REF, GPS_LAT = 1, 2
GPS_LON_REF, GPS_LON = 3, 4
GPS_ALT = 6


def _to_decimal(rat) -> float:
    # EXIF 数值可能是：纯数字、分数元组 (num, den)、PIL 的 IFDRational
    if rat is None:
        return 0.0
    try:
        return float(rat)  # 兼容 int / float / IFDRational / 数字字符串
    except (TypeError, ValueError):
        pass
    try:
        num, den = rat
        return float(num) / float(den) if den else 0.0
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def _dms_to_degrees(value) -> float:
    """GPS 度分秒元组 -> 十进制度数。"""
    try:
        return (_to_decimal(value[0]) + _to_decimal(value[1]) / 60.0
                + _to_decimal(value[2]) / 3600.0)
    except (TypeError, IndexError):
        return 0.0


def parse_datetime(raw: Any) -> Optional[dt.datetime]:
    if raw is None:
        return None
    s = str(raw).strip().rstrip("\x00")
    if not s:
        return None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d %H:%M"):
        try:
            return dt.datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _parse_tz_offset(raw: Any) -> Optional[int]:
    """解析 "+08:00" / "-05:00" 形式的时区偏移，返回分钟数。"""
    try:
        s = str(raw).strip()
        if len(s) < 6 or s[0] not in "+-":
            return None
        sign = 1 if s[0] == "+" else -1
        return sign * (int(s[1:3]) * 60 + int(s[4:6]))
    except (ValueError, IndexError):
        return None


def extract_metadata(path) -> dict:
    meta = {
        "width": None, "height": None, "orientation": None,
        "taken_at": None, "timezone_offset": None,
        "lat": None, "lng": None, "altitude": None,
        "camera_make": None, "camera_model": None,
    }
    try:
        from PIL import Image
        with Image.open(path) as im:
            meta["width"], meta["height"] = im.size
            exif = None
            try:
                exif = im.getexif()
            except Exception:
                pass
            if exif:
                try:
                    exifd = dict(exif)
                except Exception:
                    exifd = {}
                try:
                    orient = exifd.get(TAG_ORIENTATION)
                    if orient is not None:
                        meta["orientation"] = int(orient)
                except (TypeError, ValueError):
                    pass

                dtm = parse_datetime(exifd.get(TAG_DATETIME_ORIGINAL)
                                     or exifd.get(TAG_DATETIME))
                if dtm:
                    meta["taken_at"] = dtm.isoformat(sep=" ")
                off = _parse_tz_offset(exifd.get(TAG_OFFSET_TIME_ORIGINAL))
                if off is not None:
                    meta["timezone_offset"] = off

                make = str(exifd.get(TAG_MAKE) or "").strip().rstrip("\x00")
                model = str(exifd.get(TAG_MODEL) or "").strip().rstrip("\x00")
                meta["camera_make"] = make or None
                meta["camera_model"] = model or None

                # GPS（位于 GPS IFD 子目录）
                try:
                    gps = exif.get_ifd(GPS_IFD)
                    if gps:
                        lat_ref = str(gps.get(GPS_LAT_REF, "N")).strip().upper()
                        lon_ref = str(gps.get(GPS_LON_REF, "E")).strip().upper()
                        lat = _dms_to_degrees(gps.get(GPS_LAT))
                        lon = _dms_to_degrees(gps.get(GPS_LON))
                        if lat and lon:
                            meta["lat"] = lat if lat_ref == "N" else -lat
                            meta["lng"] = lon if lon_ref == "E" else -lon
                        alt = gps.get(GPS_ALT)
                        if alt is not None:
                            meta["altitude"] = _to_decimal(alt)
                except Exception:
                    pass
    except Exception:
        pass
    return meta
