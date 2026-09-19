#!/usr/bin/env python3
"""Package cheapoS.app into a compressed macOS drag-and-drop .dmg image using hdiutil."""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_RELEASE = REPO_ROOT / "dist_release"
APP_PATH = DIST_RELEASE / "cheapoS.app"
DEFAULT_DMG_NAME = "cheapoS-macOS.dmg"


def compute_sha256(filepath: Path) -> str:
    """Compute SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with filepath.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def create_dmg(app_path: Path, output_dmg: Path, volname: str = "cheapoS", dry_run: bool = False):
    if not app_path.exists():
        print(f"[!] Error: App bundle not found at {app_path}. Run build_macos_app.py first.", file=sys.stderr)
        sys.exit(1)

    if dry_run:
        print(f"[✓] Dry run: verified {app_path} exists. Would package into {output_dmg}.")
        return

    stage_dir = DIST_RELEASE / "dmg_stage"
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)

    try:
        print(f"[*] Staging {app_path.name}...")
        target_app = stage_dir / app_path.name
        shutil.copytree(app_path, target_app, symlinks=True)

        print("    Adding symlink to /Applications...")
        applications_link = stage_dir / "Applications"
        os.symlink("/Applications", applications_link)

        output_dmg.parent.mkdir(parents=True, exist_ok=True)
        if output_dmg.exists():
            output_dmg.unlink()

        print(f"[*] Creating compressed DMG at {output_dmg}...")
        cmd = [
            "/usr/bin/hdiutil",
            "create",
            "-volname",
            volname,
            "-srcfolder",
            str(stage_dir),
            "-ov",
            "-format",
            "UDZO",
            "-fs",
            "HFS+",
            str(output_dmg),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        sha = compute_sha256(output_dmg)
        checksum_file = output_dmg.parent / "checksums.txt"
        with checksum_file.open("a", encoding="utf-8") as f:
            f.write(f"{sha}  {output_dmg.name}\n")

        size_mb = output_dmg.stat().st_size / (1024 * 1024)
        print(f"[✓] Successfully built {output_dmg.name} ({size_mb:.2f} MB)")
        print(f"    SHA-256: {sha}")

    finally:
        if stage_dir.exists():
            shutil.rmtree(stage_dir)


def main():
    parser = argparse.ArgumentParser(description="Create macOS .dmg installer for cheapoS")
    parser.add_argument("--app", type=Path, default=APP_PATH, help="Path to cheapoS.app")
    parser.add_argument("--output", type=Path, default=DIST_RELEASE / DEFAULT_DMG_NAME, help="Output DMG path")
    parser.add_argument("--volname", default="cheapoS", help="Volume name in Finder")
    parser.add_argument("--dry-run", action="store_true", help="Validate without creating DMG")
    args = parser.parse_args()

    create_dmg(args.app, args.output, volname=args.volname, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
