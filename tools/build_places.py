"""生成离线地点库：GeoNames 城市数据 + 中文省市表 → app/data/cities.txt

用法：
    python tools/build_places.py            # 需要联网下载 GeoNames（约 2.5 MB）

输出格式（UTF-8，制表符分隔，一行一个城市）：
    纬度 \t 经度 \t 城市名(中文优先) \t 省份(中文，可空) \t 国家代码 \t 人口
"""
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "app" / "data"
GEONAMES_URL = "https://download.geonames.org/export/dump/cities15000.zip"
MAX_WORLD_CITIES = 12000          # 全世界保留人口最多的若干城市（中国城市全保留）


def has_cjk(s: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in s)


def load_cn_city_map():
    """中文城市表：{城市名: (省份名, 城市名)}，并补上直辖市。"""
    cities = json.loads((DATA_DIR / "cities.json").read_text(encoding="utf-8"))
    provinces = {p["code"]: p["name"] for p in
                 json.loads((DATA_DIR / "provinces.json").read_text(encoding="utf-8"))}
    mapping = {}
    for c in cities:
        prov = provinces.get(c.get("provinceCode"), "")
        name = c["name"].replace("市辖区", "").strip() or c["name"]
        mapping[c["name"]] = (prov, name)
        mapping.setdefault(name, (prov, name))
    # 直辖市：省市同名
    for code in ("11", "12", "31", "50"):
        prov = provinces.get(code)
        if prov:
            mapping[prov] = (prov, prov)
            mapping.setdefault(prov.rstrip("市"), (prov, prov))
    return mapping


def download_geonames() -> bytes:
    print(f"下载 GeoNames 城市库：{GEONAMES_URL}")
    with urllib.request.urlopen(GEONAMES_URL, timeout=120) as r:
        return r.read()


def match_cn(candidates, cn_map):
    """把 GeoNames 的中文别名匹配到中文城市表（尝试补/去「市」后缀）。"""
    for cand in candidates:
        base = cand.strip()
        variants = [base, base + "市", base.rstrip("市"), base + "省",
                    base.rstrip("市辖区"), base.replace("市辖区", "")]
        for v in variants:
            if v and v in cn_map:
                return cn_map[v]
    return ("", "")


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cn_map = load_cn_city_map()
    print(f"中文城市表：{len(cn_map)} 条")

    raw = download_geonames()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        name = [n for n in z.namelist() if n.endswith(".txt")][0]
        text = z.read(name).decode("utf-8")

    rows = []
    for line in text.splitlines():
        f = line.split("\t")
        if len(f) < 15:
            continue
        try:
            lat, lng = float(f[4]), float(f[5])
        except ValueError:
            continue
        country = f[8]
        alts = [a for a in f[3].split(",") if a.strip()]
        cn_alts = [a for a in alts if has_cjk(a)]
        geoname = f[1]
        display = cn_alts[0] if cn_alts else geoname
        province, city_cn = "", ""
        if country == "CN":
            # 国内只保留能对应到中文行政区划（地级市/直辖市）的城市，
            # 村镇与无中文名的条目丢弃，由其最近的地级市代表。
            province, city_cn = match_cn(cn_alts + [geoname], cn_map)
            if not city_cn:
                continue
            display = city_cn
        try:
            pop = int(f[14])
        except ValueError:
            pop = 0
        if country != "CN" and pop < 100000:
            continue          # 国外只保留较大城市，控制体积
        rows.append((pop, lat, lng, display, province, country, pop))

    rows.sort(key=lambda r: -r[0])
    if len(rows) > MAX_WORLD_CITIES:
        cn_rows = [r for r in rows if r[5] == "CN"]
        other = [r for r in rows if r[5] != "CN"][:max(0, MAX_WORLD_CITIES - len(cn_rows))]
        rows = cn_rows + other

    out = DATA_DIR / "cities.txt"
    with out.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("# 纬度\t经度\t城市\t省份\t国家\t人口\n")
        for _pop, lat, lng, display, province, country, pop in rows:
            fh.write(f"{lat:.5f}\t{lng:.5f}\t{display}\t{province}\t{country}\t{pop}\n")
    cn_count = sum(1 for r in rows if r[5] == "CN")
    print(f"已生成 {out}：{len(rows)} 个城市（中国 {cn_count} 个），"
          f"{out.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    sys.exit(main())
