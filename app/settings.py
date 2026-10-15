"""应用设置：轻量 JSON 存储（data/settings.json）。"""
import json
from pathlib import Path

DEFAULTS = {
    "auto_watch": True,           # 自动监控数据源文件夹，发现新文件即扫描
    "auto_scan_on_start": True,   # 启动时自动增量扫描一次
    "clean_missing": True,        # 扫描后清理磁盘上已不存在的记录
}


class Settings:
    def __init__(self, path):
        self.path = Path(path)
        self.data = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            if self.path.exists():
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.data.update(loaded)
        except Exception:
            pass

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
        except Exception:
            pass

    def get(self, key, default=None):
        return self.data.get(key, DEFAULTS.get(key, default))

    def set(self, key, value):
        self.data[key] = bool(value)
        self.save()
