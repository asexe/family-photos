"""自检工具：对指定文件夹抽样验证哈希 / EXIF / GPS / 缩略图 / 视频元数据是否正常。

用法：
    python tools/selftest.py "D:\\照片" --limit 50
"""
import argparse
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

from app.exif_reader import extract_metadata          # noqa: E402
from app.hashing import sha256_file                   # noqa: E402
from app.scanner import MEDIA_EXTS, VIDEO_EXTS, extract_quicktime_meta   # noqa: E402
from app.thumbs import (ensure_pil_plugins, extract_video_meta,          # noqa: E402
                        generate_thumbs, generate_video_thumb)

CACHE = APP_DIR / "data" / "selftest-thumbs"


def main():
    parser = argparse.ArgumentParser(description="家庭相册 - 自检")
    parser.add_argument("folder", help="待检查的文件夹")
    parser.add_argument("--limit", type=int, default=30, help="最多抽样文件数")
    args = parser.parse_args()

    ensure_pil_plugins()
    root = Path(args.folder)
    files = [p for p in root.rglob("*") if p.suffix.lower() in MEDIA_EXTS][:args.limit]
    if not files:
        print("没有找到可处理的图片或视频")
        return

    ok_thumb = ok_time = ok_gps = ok_video = 0
    for p in files:
        sha = sha256_file(p)
        if p.suffix.lower() in VIDEO_EXTS:
            meta = extract_video_meta(p)
            qt = extract_quicktime_meta(p)
            thumb = generate_video_thumb(p, sha, CACHE)
            if thumb["thumb"]:
                ok_thumb += 1
            if qt.get("taken_at"):
                ok_time += 1
                ok_video += 1
            if qt.get("lat") is not None:
                ok_gps += 1
            print(f"[视频] {p.name}  时长 {meta.get('duration')}s  "
                  f"时间 {qt.get('taken_at')}  GPS {qt.get('lat')},{qt.get('lng')}  "
                  f"缩略图 {'OK' if thumb['thumb'] else '失败'}")
        else:
            meta = extract_metadata(p)
            thumb = generate_thumbs(p, sha, CACHE)
            if thumb["thumb"]:
                ok_thumb += 1
            if meta.get("taken_at"):
                ok_time += 1
            if meta.get("lat") is not None:
                ok_gps += 1
            print(f"[图片] {p.name}  {meta.get('width')}x{meta.get('height')}  "
                  f"时间 {meta.get('taken_at')}  GPS {meta.get('lat')},{meta.get('lng')}  "
                  f"缩略图 {'OK' if thumb['thumb'] else '失败'}")

    n = len(files)
    print(f"\n抽样 {n} 个文件：缩略图成功 {ok_thumb} · 有拍摄时间 {ok_time} · "
          f"有 GPS {ok_gps} · 视频 {ok_video}")


if __name__ == "__main__":
    main()
