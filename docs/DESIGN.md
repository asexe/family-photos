# 家庭照片管理软件 · 设计方案（本地桌面版 v2）

> 一句话：一个跑在 Windows 上的本地桌面软件。家人各自建账号，给每个账号指定 1 个或多个文件夹作为
> 「数据来源」，软件扫描这些文件夹下的所有图片（**原图不动、就地索引**），按人整理、检测完全相同的照片提醒删除、
> 读取拍摄时间与 GPS 坐标，并提供「大图浏览窗口」和「缩略图小窗口」。

---

## 1. 需求与真实数据

### 1.1 明确后的需求
| 需求 | 落地方式 |
|------|---------|
| 本地软件（非服务器/手机端） | 单机桌面程序，数据全在本机，无网络依赖 |
| 新增用户 | 每个家人一个「用户」，可随时增删 |
| 指定文件夹（多个）为数据来源 | 一个用户可挂多个文件夹，递归读取其中所有图片 |
| 读取文件夹下所有图片 | 就地扫描建立索引，**不复制、不移动原图** |
| 提醒完全相同的照片以便删除 | 文件内容 SHA-256 精确去重，归组提醒，**只提醒不自动删** |
| 照片有地理定位和时间 | 读取 EXIF 的 GPS 与 DateTimeOriginal，入库建索引 |
| 预留后续筛选 | 按 人 / 时间 / 地点 / 格式 组合筛选 |
| 浏览窗口 + 小窗口 | 「浏览窗口」=大图查看；「小窗口」=缩略图墙；二者可同时打开 |

### 1.2 实测 `D:\Photos`（共 5957 个文件）
| 格式 | 数量 | 处理策略 |
|------|-----|---------|
| HEIC | 2894（最多） | 苹果照片，**必须支持解码 + 读 EXIF** |
| PNG | 2106 | 直接支持 |
| JPG | 793 | 直接支持 |
| GIF | 74 | 支持（缩略图取首帧） |
| WEBP | 1 | 支持 |
| MOV / MP4 | 86 | 视频，本期**忽略**（可后续扩展） |
| PDF | 3 | 文档，**忽略** |
| 随机文件名图片 | 若干（如 `N58K9F~4C...png`） | 照常索引，按 EXIF 时间而非文件名整理 |

**结论**：图片约 5868 张，HEIC 占比近半 → HEIC 解码是硬性要求；文件混有视频、文档、乱名文件 → 扫描必须**按扩展名过滤**，且**以 EXIF 时间为准**（不能靠文件名排序）。

---

## 2. 技术选型

| 层 | 选型 | 理由 |
|---|------|------|
| 界面 | **Python + PySide6（Qt）** | 原生窗口、多窗口天然支持（浏览窗口 + 小窗口并存）；缩略图墙用 QListView 懒加载，万张不卡 |
| 图像解码 | Pillow + **pillow-heif** | pillow-heif 负责 HEIC/HEIF 解码与 EXIF；Pillow 处理 JPG/PNG/GIF/WEBP |
| EXIF 解析 | piexif / Pillow `getexif()` | 读拍摄时间、GPS 经纬度、方向 |
| 数据库 | **SQLite**（内置，零安装） | 家庭照片量完全够用，单文件即整库 |
| 缩略图缓存 | 本地缓存目录（按 hash 命名） | 缩略图只生成一次，二次秒开 |
| 打包分发 | PyInstaller | 打包成单个 `.exe`，家人双击即用，无需装 Python |

> 备选：Electron + sharp（界面更「网页风」，但体积大、占内存多）。家庭照片库建议优先 PySide6 的轻量原生方案。

---

## 3. 数据模型（SQLite）

```sql
-- 用户（家人）
CREATE TABLE users (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,           -- 显示名，如 "爸爸"
  color       TEXT,                    -- 界面标记色
  created_at  TEXT NOT NULL
);

-- 数据来源文件夹（一个用户可有多个）
CREATE TABLE folders (
  id          INTEGER PRIMARY KEY,
  user_id     INTEGER NOT NULL REFERENCES users(id),
  path        TEXT NOT NULL,           -- 绝对路径，如 D:\Photos
  scan_status TEXT NOT NULL DEFAULT 'pending',  -- pending|scanning|done|error
  last_scan_at TEXT,
  UNIQUE(path)
);

-- 照片索引（原地索引，不动原文件）
CREATE TABLE photos (
  id           INTEGER PRIMARY KEY,
  folder_id    INTEGER NOT NULL REFERENCES folders(id),
  user_id      INTEGER NOT NULL REFERENCES users(id),
  abs_path     TEXT NOT NULL UNIQUE,   -- 原图绝对路径
  filename     TEXT NOT NULL,
  ext          TEXT NOT NULL,          -- 小写扩展名
  content_sha256 TEXT NOT NULL,        -- 精确去重
  file_size    INTEGER,
  file_mtime   INTEGER,                -- 用于增量扫描判断
  width        INTEGER,
  height       INTEGER,
  orientation  INTEGER,                -- EXIF 方向
  taken_at     TEXT,                   -- 拍摄时间（UTC）
  timezone_offset INTEGER,             -- 原时区偏移（分钟）
  lat          REAL,                   -- GPS
  lng          REAL,
  altitude     REAL,
  camera_make  TEXT,
  camera_model TEXT,
  thumb_path   TEXT,                   -- 缩略图缓存路径
  indexed_at   TEXT NOT NULL
);

-- 重复组（跨用户、跨文件夹）
CREATE TABLE duplicate_groups (
  id            INTEGER PRIMARY KEY,
  hash_value    TEXT NOT NULL UNIQUE,  -- SHA-256
  status        TEXT NOT NULL DEFAULT 'pending',  -- pending|resolved
  keep_photo_id INTEGER,
  created_at    TEXT NOT NULL
);
CREATE TABLE duplicate_items (
  group_id INTEGER NOT NULL REFERENCES duplicate_groups(id),
  photo_id INTEGER NOT NULL REFERENCES photos(id),
  PRIMARY KEY(group_id, photo_id)
);

CREATE INDEX idx_photos_user  ON photos(user_id);
CREATE INDEX idx_photos_sha   ON photos(content_sha256);
CREATE INDEX idx_photos_taken ON photos(taken_at);
CREATE INDEX idx_photos_geo   ON photos(lat, lng);
```

---

## 4. 核心功能设计

### 4.1 用户与数据来源管理
- 「用户管理」页：新增/改名/删除家人（删用户只解绑照片，不删原图）。
- 「数据来源」页：选用户 → 添加文件夹（可多选）→ 立即扫描。
- 文件夹 → 用户为多对一（一个文件夹归属一个用户）；后续若需「同一文件夹多用户共享」，可在 `folders` 上扩展关联表。

### 4.2 扫描与索引（原地，不复制）
1. 递归遍历文件夹，**按扩展名过滤**：`jpg jpeg png heic heif gif webp bmp tiff`（视频/PDF 跳过，本期不支持）。
2. 对每个图片：计算 **SHA-256**（去重）、读 EXIF（时间/GPS/方向/尺寸）、生成缩略图、写库。
3. **增量扫描**：记录 `(abs_path, file_size, file_mtime)`，未变化的文件跳过，只处理新增/改动，重复扫描飞快。
4. 后台线程执行，界面显示进度条「正在扫描 312/5868…」，扫描中仍可浏览已入库照片。

### 4.3 HEIC（苹果照片）支持 —— 关键点
- 用 **pillow-heif** 解码 HEIC 成 RGB，Pillow 统一处理；缩略图/大图/EXIF 走同一套代码。
- HEIC 同样含 GPS 与拍摄时间，按标准 EXIF 读取。
- 若某台电脑 HEIC 解码失败，回退显示「占位图 + 文件名」，不中断整体扫描。

### 4.4 重复照片检测（只提醒、不自动删）
- 所有图片算内容 **SHA-256**，哈希相同 = 内容完全相同（哪怕文件名/格式后缀不同，如同一张图的 JPG 与 PNG 转换）。
- 相同哈希归入一个「重复组」，进入「重复照片」待处理页：显示「这 3 张完全一样」，**默认建议保留分辨率最高、文件最大、有 GPS 的那张**。
- 用户勾选保留项 → 确认后删除其余（**移入回收站**，不彻底删，可后悔恢复）。
- 精确去重为主；「疑似相似（连拍/轻微压缩）」作为后续可选的 pHash 增强。

### 4.5 时间与地理定位
- 拍摄时间读 EXIF `DateTimeOriginal`；无 EXIF 时回退到文件修改时间并标注「时间可能不准」。
- 时间统一存 UTC + 时区偏移，界面按本地时区显示，跨时区照片排序不错乱。
- GPS 读 EXIF GPS IFD（纬度/经度/海拔），入库建索引，为后续「地图/按地点筛选」留好数据。
- 整理以「拍摄时间」为准，与乱序文件名无关。

### 4.6 浏览窗口 + 小窗口
- **小窗口（缩略图墙）**：主界面网格缩略图，虚拟滚动，底部信息栏显示「共 5868 张 / 筛选后 1234 张」；缩略图上标用户色点。
- **浏览窗口（大图查看器）**：双击缩略图打开独立大图窗口，支持缩放、拖动、左右切换、显示拍摄时间与地点、收藏/删除/标记重复。
- 两个窗口可**同时并存**（小窗口选片、大窗口看细节）。
- 悬浮小窗（可选后续）：把大图窗口设为「置顶小窗」，边整理边对照。

### 4.7 筛选（预留）
统一筛选栏：`按人` / `按时间段`（年/月/日快捷）/ `按地点`（圆形或矩形范围）/ `按格式` / `只看重复` / `只看无GPS`。
接口与索引已建好，后续可平滑加「地图视图」「按地点分组」。

---

## 5. 界面布局（主窗口）

```
┌─────────────────────────────────────────────────────┐
│ 菜单栏：文件 | 用户管理 | 数据来源 | 重复照片 | 帮助   │
├────────────┬────────────────────────────────────────┤
│ 左侧栏      │  筛选栏： [用户▾] [年月▾] [地点] [格式▾] │
│  · 全部照片  │────────────────────────────────────────│
│  · 用户列表  │                                        │
│    爸爸     │         缩略图墙（小窗口）                │
│    妈妈     │     □ □ □ □ □ □ □ □ □ □                 │
│    孩子     │     □ □ □ □ □ □ □ □ □ □                 │
│  · 重复照片  │     （双击 → 打开大图浏览窗口）            │
│  · 无GPS    │                                        │
├────────────┴────────────────────────────────────────┤
│ 状态栏：共 5868 张 · 已选 0 · 上次扫描 3 分钟前         │
└─────────────────────────────────────────────────────┘
```

---

## 6. 目录结构（代码）

```
photo-manager/
├── app/
│   ├── main.py              # 程序入口
│   ├── db.py                # SQLite 连接与建表
│   ├── models.py            # 数据模型
│   ├── scanner.py           # 扫描/增量/后台线程
│   ├── hashing.py           # SHA-256
│   ├── exif_reader.py       # 时间 + GPS 提取（含 HEIC）
│   ├── thumbs.py            # 缩略图生成与缓存
│   ├── dedup.py             # 重复分组
│   └── ui/
│       ├── main_window.py   # 主窗口（缩略图墙）
│       ├── viewer_window.py # 大图浏览窗口
│       ├── user_dialog.py   # 用户管理
│       └── folder_dialog.py # 数据来源管理
├── requirements.txt         # pyside6, pillow, pillow-heif, piexif
└── build.spec               # PyInstaller 打包配置
```

---

## 7. 分阶段实施计划

**第一阶段 · MVP（先跑通核心）**
1. 用户管理 + 数据来源（添加文件夹）。
2. 扫描 `D:\Photos`：过滤扩展名、SHA-256、EXIF（时间/GPS）、缩略图、写 SQLite。
3. 缩略图墙（小窗口）+ 大图浏览窗口（含 HEIC 正常显示）。
4. 重复照片检测 + 提醒 + 移入回收站删除。
5. 按人 / 按时间 / 按格式筛选。

**第二阶段 · 完善**
6. 增量扫描提速 + 手动「重新扫描」按钮。
7. 按地理位置筛选 / 地图视图。
8. 收藏、备注。
9. 近似去重（pHash）。

**第三阶段 · 增强（可选）**
10. 悬浮置顶小窗。
11. 视频（MOV/MP4）纳入管理。
12. 打包单文件 `.exe` 分发。

---

## 8. 需你确认的 2 点

1. **界面技术方案**：用 **PySide6 原生窗口**（轻量、启动快，推荐）还是 **Electron 网页风**（更华丽但体积大、占内存）？
2. **是否现在开始动手**：我可以先做 MVP——把 `D:\Photos` 这 5868 张扫进 SQLite、HEIC 能看、能去重提醒、有缩略图墙和大图窗口。确认后我就开始写代码。

---

## 9. 实施状态（2026-10 已开工）

> 按「PySide6 + 苹果简约风」方案实现，代码在 `D:\test\photo-manager\`。

**已完成并验证**：
- ✅ 核心后端：SHA-256 去重、EXIF 时间/GPS 提取（HEIC/JPG/PNG/GIF/WEBP）、缩略图+预览图缓存、SQLite 入库、增量扫描（多线程）
- ✅ 实测 `D:\Photos`：HEIC 正常解码；GPS 命中约 51%（修复了 pillow-heif 的 IFDRational 解析 bug）；拍摄时间约 52%
- ✅ 苹果风界面：无边框窗口 + 红黄绿交通灯标题栏、侧边栏（全部/重复/家人）、顶部筛选栏（时间/格式/搜索）、缩略图墙（小窗口）、大图浏览窗口（深色、缩放/拖动/←→切换/删除/收藏）
- ✅ 用户管理、数据来源（文件夹）管理、重复照片处理对话框（建议保留 + 移入回收站）
- ✅ 端到端测试通过：33 张样本扫描、3 组完全相同照片正确归组

**待办（下一步）**：
- 把 `D:\Photos` 全量 5868 张扫入正式库（需要你提供家人名单与文件夹归属）✅ 已完成
- 地图视图 ✅ 已完成（Leaflet 地图主页 + 家人复选框 + 聚类圆点）
- 时间轴照片墙 ✅ 已完成（年月分割线 + 右侧年份/月份刻度尺 + 当前月份高亮）
- 近似去重（pHash）、视频支持、打包 `.exe`

**视频支持方案（未来启用，架构已预留）**：
- 扫描扩展名加 `.mov/.mp4/.m4v` 等；缩略图用 Qt Multimedia 抓首帧存 JPEG（复用现有缓存目录）
- 拍摄时间：视频无 EXIF，取文件修改时间或 QuickTime 创建时间（标注「时间可能不准」）
- 去重：SHA-256 同样适用；浏览窗口检测到视频 → 内嵌播放器（进度条/音量/全屏）
- 时间轴/年份刻度尺：与照片一样按时间分组
- 当前 `D:\Photos` 中 86 个视频（63 MOV + 23 MP4）暂未入库
