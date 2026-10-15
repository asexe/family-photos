"""生成离线底图：下载世界国界与中国省界，精简后存入 app/map/basemap/。

用法：
    python tools/build_basemap.py     # 需要联网（约 2 MB 下载）

输出：
    app/map/basemap/world.json   世界国界（用于离线轮廓底图）
    app/map/basemap/china.json   中国省界（离线时看得更细）
"""
import json
import sys
import urllib.request
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = APP_DIR / "app" / "map" / "basemap"

SOURCES = {
    "world.json": "https://cdn.jsdelivr.net/gh/johan/world.geo.json@master/countries.geo.json",
    "china.json": "https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json",
}


def round_coords(obj, ndigits: int = 2):
    """递归降低坐标精度，显著减小体积。"""
    if isinstance(obj, float):
        return round(obj, ndigits)
    if isinstance(obj, list):
        if obj and isinstance(obj[0], (int, float)):
            return [round(v, ndigits) for v in obj]
        return [round_coords(v, ndigits) for v in obj]
    if isinstance(obj, dict):
        return {k: (round_coords(v, ndigits) if k == "coordinates" else v)
                for k, v in obj.items()}
    return obj


def slim(geo: dict) -> dict:
    """只保留绘图必需字段并压缩坐标精度。"""
    out = {"type": "FeatureCollection", "features": []}
    for f in geo.get("features", []):
        props = f.get("properties") or {}
        name = (props.get("name") or props.get("NAME") or props.get("NAME_ZH") or "")
        out["features"].append({
            "type": "Feature",
            "properties": {"name": name},
            "geometry": round_coords(f.get("geometry")),
        })
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, url in SOURCES.items():
        print(f"下载 {filename} <- {url}")
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                raw = r.read()
        except Exception as e:  # noqa: BLE001
            print(f"  失败：{e}")
            continue
        try:
            geo = json.loads(raw.decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"  解析失败：{e}")
            continue
        slimmed = slim(geo)
        out = OUT_DIR / filename
        out.write_text(json.dumps(slimmed, ensure_ascii=False, separators=(",", ":")),
                       encoding="utf-8")
        print(f"  已生成 {out.name}：{len(slimmed['features'])} 个要素，"
              f"{out.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
