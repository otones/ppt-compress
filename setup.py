"""py2app setup for building the macOS .app bundle.

Build with:
    pip install py2app
    python setup.py py2app

The resulting PPTXCompressor.app lives in dist/ and is launchable from
Finder. No code signing (Non-Goal) — users bypass Gatekeeper with:
    xattr -dr com.apple.quarantine /path/to/PPTXCompressor.app
"""

from setuptools import setup

# GUI 只使用 PySide6 的 QtCore / QtGui / QtWidgets。
# 其余 Qt 模块全部排除,避免把 QtWebEngine / QML / Quick / 3D 等大头打进包。
PYSIDE6_KEEP = {"QtCore", "QtGui", "QtWidgets"}

# PySide6 中所有可选子模块;除 KEEP 外一律排除。
PYSIDE6_EXCLUDES = [
    f"PySide6.Qt{m}"
    for m in [
        # WebEngine 是体积大头之一(数百 MB)
        "WebEngineCore", "WebEngineWidgets", "WebEngineQuick",
        "WebChannel", "WebSockets",
        # QML / Quick 工具链
        "Qml", "Quick", "Quick3D", "QuickWidgets", "QuickControls2",
        "QuickTest", "QuickShapes", "QuickParticles", "QuickTemplates2",
        "QmlWorkerScript",
        # 3D 系列
        "3DCore", "3DRender", "3DInput", "3DLogic", "3DAnimation",
        "3DExtras", "Quick3DUtils",
        # 图表 / 数据可视化
        "Charts", "DataVisualization",
        # PDF / 文档
        "Pdf", "PdfWidgets", "TextToSpeech", "Help",
        # 多媒体 / 网络 / 传感器(离线工具不需要)
        "Multimedia", "MultimediaWidgets",
        "Network", "NetworkAuth",
        "Bluetooth", "Nfc", "Positioning", "Location",
        "Sensors", "SerialBus", "SerialPort",
        "Sql", "Test", "Xml", "SvgWidgets", "Svg", "OpenGL", "OpenGLWidgets",
        "PrintSupport", "Designer", "UiTools",
        "Scxml", "StateMachine", "RemoteObjects",
        "Concurrent", "AxContainer", "DataVisualizationQml", "ChartsQml",
    ]
]

APP = ["run_gui.py"]
OPTIONS = {
    "argv_emulation": False,
    "semi_standalone": False,   # 必须为 False:把完整 Python 运行时打进 .app
    "site_packages": False,     # 不用系统 site-packages,保证完全自包含
    "strip": True,            # 剥离调试符号
    "iconfile": None,
    "plist": {
        "CFName": "PPTXCompressor",
        "CFBundleDisplayName": "PPTX 压缩器",
        "CFBundleName": "PPTXCompressor",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeName": "PowerPoint",
                "CFBundleTypeRole": "Viewer",
                "LSItemContentTypes": ["org.openxmlformats.presentationml.presentation"],
                "LSHandlerRank": "Alternate",
            }
        ],
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
    },
    # 只显式包含必需的 PySide6 顶层模块;不写 "PySide6" 整包。
    "packages": ["PySide6"],  # 顶层包保留,实际靠 includes/excludes 收窄
    "includes": [
        "PIL",
        "lxml", "click", "pptx_compressor",
        # 仅显式包含需要的 PySide6 子模块(及其运行时依赖 shiboken6)
        "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
        "PySide6.support",
        "shiboken6",
    ],
    "excludes": (
        [
            "tkinter", "matplotlib", "numpy", "scipy", "pandas",
            "PyQt5", "PyQt6", "PySide2",
            "test", "tests", "unittest", "pydoc", "doctest",
            "distutils", "lib2to3", "turtle", "turtledemo",
            "http", "urllib", "xmlrpc", "email", "ftplib", "telnetlib",
            "ssl", "_ssl",  # 离线工具不需要网络/SSL
        ]
        + PYSIDE6_EXCLUDES
    ),
}

setup(
    name="PPTXCompressor",
    version="1.0.0",
    author="pptx-compressor",
    license="MIT",
    app=APP,
    options={"py2app": OPTIONS},
)
