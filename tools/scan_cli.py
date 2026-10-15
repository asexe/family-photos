"""命令行扫描工具：把一个或多个文件夹挂到指定家人名下并扫描。

用法：
    python tools/scan_cli.py "D:\\照片" --user 爸爸
    python tools/scan_cli.py "D:\\照片A" "E:\\照片B" --user 妈妈 --workers 8
"""
import argparse
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

from app.db import Database                     # noqa: E402
from app.scanner import Scanner                 # noqa: E402
from app.thumbs import ensure_pil_plugins       # noqa: E402

DATA_DIR = APP_DIR / "data"


def main():
    parser = argparse.ArgumentParser(description="家庭相册 - 命令行扫描")
    parser.add_argument("folders", nargs="+", help="要扫描的照片/视频文件夹")
    parser.add_argument("--user", default="默认用户", help="归属家人名称（不存在会自动创建）")
    parser.add_argument("--workers", type=int, default=6, help="并发线程数（默认 6）")
    args = parser.parse_args()

    ensure_pil_plugins()
    db = Database(DATA_DIR / "photos.db")
    db.init()

    user = next((u for u in db.list_users() if u["name"] == args.user), None)
    if user is None:
        uid = db.add_user(args.user, "#007AFF")
        print(f"已创建用户：{args.user}")
    else:
        uid = user["id"]

    scanner = Scanner(db, DATA_DIR / "thumbs", workers=args.workers)
    for folder in args.folders:
        path = Path(folder).expanduser()
        if not path.is_dir():
            print(f"跳过（不是文件夹）：{path}")
            continue
        fid = db.add_folder(uid, str(path))
        last = [0]

        def progress(done, total, new, dup):
            if done - last[0] >= 100 or done == total:
                print(f"  {path.name}: {done}/{total}  新增 {new}  重复 {dup}", flush=True)
                last[0] = done

        print(f"开始扫描：{path}")
        result = scanner.scan_folder(fid, on_progress=progress)
        print(f"完成：{result}")

    st = db.stats()
    print(f"\n库内合计：{st['total']} 个文件 · 待处理重复 {st['pending_dups']} 组 · "
          f"无定位 {st['no_gps']}")
    db.close_all()


if __name__ == "__main__":
    main()
