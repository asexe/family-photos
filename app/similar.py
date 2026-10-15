"""相似照片聚类：感知哈希（dHash）+ 分块索引 + 并查集。

用于找出「看起来一样」的照片：连拍、微信压缩版、二次保存、轻微裁剪。
与「完全相同」（SHA-256）互不干扰，各自独立成组。
"""
from collections import defaultdict
from pathlib import Path

from .db import Database
from .phash import BLOCKS, dhash, from_hex, hamming, to_hex

DEFAULT_THRESHOLD = 4        # 汉明距离阈值：越小越严格（4=严格，6=标准，8=宽松）
MAX_GROUP = 60               # 单组上限，避免噪声巨型组


def rebuild_groups(db: Database, threshold: int = DEFAULT_THRESHOLD,
                   max_group: int = MAX_GROUP, on_progress=None) -> dict:
    """重新计算相似组（星型聚类：成员必须与组内种子足够接近，不做链式传递）。

    传递闭包会把 A~B、B~C 但 A 与 C 毫不相干的照片并成巨型组，因此这里以
    种子为中心成组：种子是组内第一张未归组的照片，其余成员须与种子距离达标。
    """
    rows = db.photos_with_phash(exclude_exact_dups=True)
    hashes = {r["id"]: from_hex(r["phash"]) for r in rows if from_hex(r["phash"])}
    ids = sorted(hashes)
    db.clear_similar_groups()
    if len(ids) < 2:
        return {"groups": 0, "photos": 0, "checked": len(ids), "pairs": 0}

    # 分块索引：只在同块命中的候选里算距离
    buckets = [defaultdict(list) for _ in range(BLOCKS)]
    for pid in ids:
        h = hashes[pid]
        for b in range(BLOCKS):
            buckets[b][(h >> (8 * b)) & 0xFF].append(pid)

    assigned = set()
    groups = []
    ignored = db.ignored_similar()
    checked_pairs = 0
    for seed in ids:
        if seed in assigned:
            continue
        h = hashes[seed]
        candidates = set()
        for b in range(BLOCKS):
            for other in buckets[b][(h >> (8 * b)) & 0xFF]:
                if other != seed and other not in assigned:
                    candidates.add(other)
        members = [seed]
        for c in candidates:
            checked_pairs += 1
            if hamming(h, hashes[c]) <= threshold:
                members.append(c)
                if len(members) >= max_group:
                    break
        if len(members) >= 2:
            members.sort()
            # 用户已忽略过的组合不再提示
            if ",".join(str(x) for x in members) in ignored:
                assigned.update(members)
                continue
            groups.append(members)
            assigned.update(members)
        else:
            assigned.add(seed)

    for group in groups:
        db.add_similar_group(f"p:{to_hex(hashes[group[0]])}", group)

    if on_progress:
        on_progress(len(groups))
    return {"groups": len(groups), "photos": sum(len(g) for g in groups),
            "checked": len(ids), "pairs": checked_pairs,
            "largest": max((len(g) for g in groups), default=0)}


def backfill_phash(db: Database, limit: int = 0, on_progress=None) -> int:
    """为已有照片补算 dHash（优先用已生成的缩略图，速度快）。"""
    rows = db.photos_missing_phash(limit=limit)
    total = len(rows)
    done = 0
    for i, r in enumerate(rows, 1):
        value = 0
        for path in (r.get("thumb_path"), r.get("abs_path")):
            if not path:
                continue
            p = Path(path)
            if not p.exists():
                continue
            try:
                from PIL import Image
                with Image.open(p) as im:
                    value = dhash(im)
                break
            except Exception:
                continue
        if value:
            db.set_phash(r["id"], to_hex(value))
            done += 1
        if on_progress and (i % 200 == 0 or i == total):
            on_progress(i, total)
    return done
