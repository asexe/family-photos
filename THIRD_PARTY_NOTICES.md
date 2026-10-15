# 第三方组件与许可声明

本项目以 MIT License 发布。为便于离线开箱即用，仓库内直接包含了以下第三方资源，
其版权归各自作者所有，使用需遵守其许可条款。

## 随仓库分发的资源

| 组件 | 位置 | 许可 |
|------|------|------|
| Leaflet 1.9.4 | `app/map/vendor/leaflet.js`, `leaflet.css` | BSD-2-Clause |
| Leaflet.markercluster 1.5.3 | `app/map/vendor/leaflet.markercluster.js`, `MarkerCluster*.css` | MIT |
| Font Awesome Free 6.5.2（图标 SVG） | `app/ui/icons/*.svg` | 图标：CC BY 4.0；字体：SIL OFL 1.1；代码：MIT |

Font Awesome 官方要求署名，本项目在 README 与界面说明中标注：
> Icons by [Font Awesome Free](https://fontawesome.com) (CC BY 4.0)

## 运行期依赖（通过 pip 安装，不随仓库分发）

| 组件 | 许可 | 用途 |
|------|------|------|
| PySide6 / Qt 6 | LGPL-3.0（另有商业许可） | 界面框架 |
| Pillow | MIT-CMU | 图片解码、缩略图 |
| pillow-heif | BSD-3-Clause | HEIC/HEIF 解码（苹果照片） |
| OpenCV (opencv-python-headless) | Apache-2.0 | 视频首帧抓取 |
| shiboken6 | LGPL-3.0 | PySide6 依赖 |

## 网络服务

- 地图底图瓦片：高德地图公开瓦片服务（`webrd0x.is.autonavi.com`），失败时自动回退 OpenStreetMap。
  瓦片仅用于本地展示，版权归相应服务方所有；如需商业使用请自行申请授权。
- 本软件**不上传任何照片、视频或元数据**；除地图瓦片外无任何对外网络请求。

## 许可兼容性说明

- 若你以 LGPL-3.0 方式分发 PySide6，请保留其许可文本与动态链接方式（本仓库以源码形式依赖 pip 包，
  未修改 Qt 代码，符合 LGPL 要求）。
- MIT / BSD / Apache-2.0 组件与本项目 MIT 许可兼容。
- CC BY 4.0 图标资源要求保留署名，请勿移除 README 与本节中的署名信息。
