"""地图主页组件：内嵌 Chromium 加载 Leaflet 地图页面。

点击单个照片圆点 → 导航 photo://open/<id> → 拦截后回调打开大图浏览窗口。
"""
from PySide6.QtCore import QUrl
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView


class MapWebPage(QWebEnginePage):
    """拦截 photo:// 导航，用于在桌面端打开照片。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.photo_clicked = None  # callable(photo_id)

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if url.scheme() == "photo":
            try:
                pid = int(url.path().strip("/").split("/")[-1])
            except ValueError:
                pid = None
            if pid and self.photo_clicked:
                self.photo_clicked(pid)
            return False
        if url.host() == "127.0.0.1":
            return True
        if nav_type == QWebEnginePage.NavigationType.NavigationTypeReload:
            return True
        return False


class MapPage(QWebEngineView):
    def __init__(self, server, parent=None):
        super().__init__(parent)
        self._page = MapWebPage(self)
        self.setPage(self._page)
        self.load(QUrl(f"http://127.0.0.1:{server.port}/"))

    def set_photo_handler(self, fn):
        self._page.photo_clicked = fn

    def reload_photos(self):
        try:
            self.page().runJavaScript("window.loadPhotos && window.loadPhotos()")
        except Exception:
            pass
