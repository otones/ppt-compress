"""py2app setup for building the macOS .app bundle.

Build with:
    pip install py2app
    python setup.py py2app

The resulting PPTXCompressor.app lives in dist/ and is launchable from
Finder. No code signing (Non-Goal) — users bypass Gatekeeper with:
    xattr -dr com.apple.quarantine /path/to/PPTXCompressor.app
"""

from setuptools import setup

APP = ["run_gui.py"]
OPTIONS = {
    "argv_emulation": False,
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
    "packages": [],
    "includes": [
        "PySide6",
        "PIL",
        "lxml",
        "click",
        "pptx_compressor",
    ],
    "excludes": [
        "tkinter", "matplotlib", "numpy", "scipy", "pandas",
        "PyQt5", "PyQt6", "PySide2", "test", "tests",
    ],
}

setup(
    name="PPTXCompressor",
    app=APP,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
