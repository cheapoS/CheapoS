#!/usr/bin/env python3
"""Build cheapoS.app for macOS.

Supports both:
1. Frozen standalone binary via PyInstaller (when installed, e.g. in CI/CD).
2. Native macOS application bundle (zero dependencies, works on any Mac).
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_SRC = REPO_ROOT / "dist"
CHEAPOS_SRC = REPO_ROOT / "cheapos"
RUN_PY = REPO_ROOT / "run.py"
OUTPUT_DIR = REPO_ROOT / "dist_release"
APP_NAME = "cheapoS"
BUNDLE_ID = "lol.cheapos.desktop"
VERSION = "1.0.0"


def generate_info_plist(output_path: Path):
    """Generate Info.plist for the macOS application bundle."""
    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleExecutable</key>
    <string>{APP_NAME}</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleIdentifier</key>
    <string>{BUNDLE_ID}</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>{APP_NAME}</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>{VERSION}</string>
    <key>CFBundleVersion</key>
    <string>{VERSION}</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.15</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSSupportsAutomaticGraphicsSwitching</key>
    <true/>
    <key>LSApplicationCategoryType</key>
    <string>public.app-category.developer-tools</string>
</dict>
</plist>
"""
    output_path.write_text(plist_content, encoding="utf-8")


def build_native_bundle(app_dir: Path):
    """Assemble a native macOS .app structure with launcher and resources."""
    print(f"[*] Assembling native macOS bundle at {app_dir}...")
    contents = app_dir / "Contents"
    macos_dir = contents / "MacOS"
    resources_dir = contents / "Resources"

    macos_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)

    # 1. Info.plist
    generate_info_plist(contents / "Info.plist")

    # 2. Executable launcher script
    launcher = macos_dir / APP_NAME
    launcher_script = """#!/bin/bash
# cheapoS macOS application launcher
APP_ROOT="$(cd "$(dirname "$0")/../Resources" && pwd)"
export PYTHONPATH="$APP_ROOT:$PYTHONPATH"
cd "$APP_ROOT"

# Prefer user-installed Python 3, fallback to system /usr/bin/python3
if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif [ -x "/usr/local/bin/python3" ]; then
    PYTHON_BIN="/usr/local/bin/python3"
elif [ -x "/opt/homebrew/bin/python3" ]; then
    PYTHON_BIN="/opt/homebrew/bin/python3"
else
    PYTHON_BIN="/usr/bin/python3"
fi

exec "$PYTHON_BIN" "$APP_ROOT/run.py" "$@"
"""
    launcher.write_text(launcher_script, encoding="utf-8")
    launcher.chmod(0o755)

    # 3. Copy application resources
    print("    Copying application resources (run.py, dist/, cheapos/)...")
    shutil.copy2(RUN_PY, resources_dir / "run.py")

    target_cheapos = resources_dir / "cheapos"
    if target_cheapos.exists():
        shutil.rmtree(target_cheapos)
    shutil.copytree(CHEAPOS_SRC, target_cheapos, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    target_dist = resources_dir / "dist"
    if target_dist.exists():
        shutil.rmtree(target_dist)
    shutil.copytree(DIST_SRC, target_dist)

    print(f"[✓] Native macOS bundle ready at {app_dir}")


def build_pyinstaller_bundle(app_dir: Path):
    """Build standalone frozen binary using PyInstaller."""
    print(f"[*] Compiling standalone binary with PyInstaller...")
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name",
        APP_NAME,
        "--distpath",
        str(OUTPUT_DIR),
        "--add-data",
        f"{DIST_SRC}:dist",
        "--add-data",
        f"{CHEAPOS_SRC}:cheapos",
        str(RUN_PY),
    ]
    subprocess.run(cmd, check=True)
    # Generate/update Info.plist
    generate_info_plist(app_dir / "Contents" / "Info.plist")
    print(f"[✓] PyInstaller standalone bundle ready at {app_dir}")


def main():
    parser = argparse.ArgumentParser(description="Build cheapoS.app for macOS")
    parser.add_argument("--mode", choices=["auto", "standalone", "native"], default="auto",
                        help="Packaging mode (auto, standalone with PyInstaller, or native bundle)")
    parser.add_argument("--clean", action="store_true", help="Clean output directory before build")
    parser.add_argument("--dry-run", action="store_true", help="Validate assets without writing output")
    args = parser.parse_args()

    if not RUN_PY.exists() or not CHEAPOS_SRC.exists() or not DIST_SRC.exists():
        print(f"[!] Error: Missing required source directories at {REPO_ROOT}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print("[✓] Dry run: verified run.py, cheapos/, and dist/ exist.")
        sys.exit(0)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    app_dir = OUTPUT_DIR / f"{APP_NAME}.app"

    if args.clean and app_dir.exists():
        print(f"[*] Cleaning {app_dir}...")
        shutil.rmtree(app_dir)

    has_pyinstaller = False
    try:
        import PyInstaller  # noqa
        has_pyinstaller = True
    except ImportError:
        pass

    if args.mode == "standalone":
        if not has_pyinstaller:
            print("[!] Error: PyInstaller is not installed. Install with `pip install pyinstaller`.", file=sys.stderr)
            sys.exit(1)
        build_pyinstaller_bundle(app_dir)
    elif args.mode == "native":
        build_native_bundle(app_dir)
    else:  # auto
        if has_pyinstaller:
            build_pyinstaller_bundle(app_dir)
        else:
            print("[*] PyInstaller not detected. Falling back to native macOS bundle mode.")
            build_native_bundle(app_dir)


if __name__ == "__main__":
    main()
