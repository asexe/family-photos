"""地图主页本地 HTTP 服务器：静态页面 + 照片地理数据 + 缩略图。

只监听 127.0.0.1 随机端口，数据不出本机。
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

MAP_DIR = Path(__file__).resolve().parent / "map"

_MIME = {".html": "text/html; charset=utf-8",
         ".js": "application/javascript",
         ".css": "text/css",
         ".json": "application/json; charset=utf-8",
         ".png": "image/png",
         ".jpg": "image/jpeg"}


class MapServer:
    def __init__(self, db, data_dir: Path):
        self.db = db
        self.thumb_dir = Path(data_dir) / "thumbs"
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._make_handler())
        self.port = self.httpd.server_address[1]
        t = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        t.start()

    def _make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                try:
                    server._handle(self)
                except Exception:
                    try:
                        self.send_error(500)
                    except Exception:
                        pass

        return Handler

    @staticmethod
    def _send_bytes(h, data: bytes, content_type: str):
        h.send_response(200)
        h.send_header("Content-Type", content_type)
        h.send_header("Content-Length", str(len(data)))
        h.end_headers()
        h.wfile.write(data)

    def _handle(self, h):
        url = urlparse(h.path)
        path = unquote(url.path)

        # 地理数据：所有带 GPS 的照片
        if path == "/api/photos":
            rows = self.db.query_photos()
            out = []
            for r in rows:
                if r.get("lat") is None or r.get("lng") is None:
                    continue
                out.append({
                    "id": r["id"],
                    "lat": round(r["lat"], 6),
                    "lng": round(r["lng"], 6),
                    "thumb": f"/thumb/{r['id']}",
                    "user": r.get("user_name") or "",
                    "color": r.get("user_color") or "#007AFF",
                    "taken": r.get("taken_at") or "",
                    "place": r.get("place") or "",
                })
            body = json.dumps(out, ensure_ascii=False).encode("utf-8")
            self._send_bytes(h, body, "application/json; charset=utf-8")
            return

        # 缩略图
        if path.startswith("/thumb/"):
            try:
                pid = int(path.split("/")[-1])
            except ValueError:
                h.send_error(404)
                return
            row = self.db.get_photo(pid)
            if row and row.get("thumb_path"):
                p = Path(row["thumb_path"])
                if p.exists():
                    self._send_bytes(h, p.read_bytes(), "image/jpeg")
                    return
            h.send_error(404)
            return

        # 静态文件（页面与地图库）
        rel = path.lstrip("/") or "index.html"
        f = (MAP_DIR / rel).resolve()
        if not str(f).startswith(str(MAP_DIR.resolve())) or not f.is_file():
            h.send_error(404)
            return
        self._send_bytes(h, f.read_bytes(),
                         _MIME.get(f.suffix, "application/octet-stream"))
