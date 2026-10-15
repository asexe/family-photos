"""离线地点反查：GPS 坐标 → 省·市（中文优先，无需联网）。

数据来自 GeoNames 城市库 + 中文省市表（由 tools/build_places.py 生成）。
"""
import threading
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

CITIES_FILE = Path(__file__).resolve().parent / "data" / "cities.txt"
MAX_KM = 150.0       # 超过该距离视为没有匹配城市（只收录地级市，半径放大以便村镇归位）
EARTH_R = 6371.0

_lock = threading.Lock()
_grid = None         # {(int(lat), int(lng)): [(lat, lng, city, province, country), ...]}


def _load():
    global _grid
    with _lock:
        if _grid is not None:
            return _grid
        grid = {}
        try:
            with CITIES_FILE.open(encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("#"):
                        continue
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) < 5:
                        continue
                    try:
                        lat, lng = float(parts[0]), float(parts[1])
                    except ValueError:
                        continue
                    grid.setdefault((int(lat), int(lng)), []).append(
                        (lat, lng, parts[2], parts[3], parts[4]))
        except Exception:
            grid = {}
        _grid = grid
        return _grid


def _haversine(lat1, lng1, lat2, lng2) -> float:
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = (sin(dlat / 2) ** 2
         + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2)
    return 2 * EARTH_R * asin(sqrt(a))


def lookup(lat, lng, max_km: float = MAX_KM):
    """返回 (显示名, 省份, 城市)；找不到返回 (None, None, None)。

    显示名形如「福建省·厦门市」，直辖市则为「北京市」。
    """
    if lat is None or lng is None:
        return (None, None, None)
    grid = _load()
    if not grid:
        return (None, None, None)
    ilat, ilng = int(lat), int(lng)
    best = None
    for dlat in range(-2, 3):
        for dlng in range(-2, 3):
            for entry in grid.get((ilat + dlat, ilng + dlng), ()):
                d = _haversine(lat, lng, entry[0], entry[1])
                if best is None or d < best[0]:
                    best = (d, entry)
    if best is None or best[0] > max_km:
        return (None, None, None)
    _d, (_clat, _clng, city, province, _country) = best
    if province and province != city:
        display = f"{province}·{city}"
    else:
        display = city
    return (display, province or None, city or None)


def place_count() -> int:
    return sum(len(v) for v in _load().values())


def backfill(db) -> int:
    """为已有 GPS 但尚无地点的记录补上地点，返回处理条数。"""
    rows = db.photos_missing_place()
    done = 0
    for r in rows:
        display = lookup(r["lat"], r["lng"])[0]
        if display:
            db.set_place(r["id"], display)
            done += 1
    return done
