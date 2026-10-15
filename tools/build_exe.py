"""打包成免安装 exe（PyInstaller）。

用法：
    python tools/build_exe.py            # 生成 dist/家庭相册/家庭相册.exe
    python tools/build_exe.py --onedir   # 默认即为单目录版（推荐，启动快）
"""
import shutil
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

APP_NAME = "家庭相册"


def main():
    try:
        import PyInstaller.__main__ as pyi
    except ImportError:
        print("缺少 PyInstaller，请先执行：python -m pip install pyinstaller")
        return 1

    for d in ("build", "dist"):
        p = APP_DIR / d
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)

    args = [
        str(APP_DIR / "main.py"),
        "--name", APP_NAME,
        "--noconfirm",
        "--clean",
        "--windowed",                      # 不弹控制台
        "--distpath", str(APP_DIR / "dist"),   # 产物固定在项目内
        "--workpath", str(APP_DIR / "build"),
        "--specpath", str(APP_DIR),
        # 非代码资源（地图页、图标、地点库）
        "--add-data", f"{APP_DIR / 'app' / 'map'}{':' if sys.platform != 'win32' else ';'}app/map",
        "--add-data", f"{APP_DIR / 'app' / 'ui' / 'icons'}{':' if sys.platform != 'win32' else ';'}app/ui/icons",
        "--add-data", f"{APP_DIR / 'app' / 'data'}{':' if sys.platform != 'win32' else ';'}app/data",
        # 隐式导入（惰性导入的 Qt 模块）
        "--hidden-import", "PySide6.QtWebEngineWidgets",
        "--hidden-import", "PySide6.QtWebEngineCore",
        "--hidden-import", "PySide6.QtMultimedia",
        "--hidden-import", "PySide6.QtMultimediaWidgets",
        "--hidden-import", "PySide6.QtSvg",
        # 三方二进制/数据
        "--collect-all", "pillow_heif",
        "--collect-all", "cv2",
        "--exclude-module", "tkinter",
        "--exclude-module", "matplotlib",
        "--exclude-module", "PySide6.QtQuick3D",
        "--exclude-module", "PySide6.Qt3DCore",
        "--exclude-module", "PySide6.QtCharts",
        "--exclude-module", "PySide6.QtDataVisualization",
        "--exclude-module", "PySide6.QtDesigner",
        "--exclude-module", "PySide6.QtBluetooth",
        "--exclude-module", "PySide6.QtNfc",
        "--exclude-module", "PySide6.QtPdf",
        "--exclude-module", "PySide6.QtRemoteObjects",
        "--exclude-module", "PySide6.QtScxml",
        "--exclude-module", "PySide6.QtSensors",
        "--exclude-module", "PySide6.QtSerialPort",
        "--exclude-module", "PySide6.QtTest",
        "--exclude-module", "PySide6.QtWebEngineQuick",
    ]
    print("开始打包（首次约 3~8 分钟，请耐心等待）…")
    pyi.run(args)

    exe = APP_DIR / "dist" / APP_NAME / f"{APP_NAME}.exe"
    if exe.exists():
        size_mb = sum(f.stat().st_size for f in (APP_DIR / "dist" / APP_NAME).rglob("*")
                      if f.is_file()) / 1024 / 1024
        print(f"\n打包完成：{exe}")
        print(f"整包体积：{size_mb:.0f} MB")
        print("该目录可直接拷贝到任意 Windows 电脑运行（数据保存在 exe 同级的 data 目录）。")
        return 0
    print("打包似乎失败，请检查上面的输出。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
