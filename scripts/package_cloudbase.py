"""Build a self-contained Python 3.11 CloudBase function package."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FUNCTION = ROOT / "functions" / "zhuqingForecastRefresh"
SOURCE_SITEGEN = ROOT / "sitegen"
TARGET = ROOT / ".cloudbase" / "functions" / "zhuqingForecastRefresh"


def main() -> None:
    if sys.version_info[:2] != (3, 11):
        raise SystemExit(
            f"CloudBase function package must be built with Python 3.11; got {sys.version.split()[0]}"
        )
    if TARGET.exists():
        shutil.rmtree(TARGET)
    TARGET.mkdir(parents=True)

    shutil.copy2(SOURCE_FUNCTION / "index.py", TARGET / "index.py")
    shutil.copytree(
        SOURCE_SITEGEN,
        TARGET / "sitegen",
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "tests"),
    )
    requirements = SOURCE_FUNCTION / "requirements.txt"
    shutil.copy2(requirements, TARGET / "requirements.txt")

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-compile",
            "--only-binary=:all:",
            "--target",
            str(TARGET),
            "-r",
            str(requirements),
        ],
        check=True,
    )
    total_bytes = sum(path.stat().st_size for path in TARGET.rglob("*") if path.is_file())
    file_count = sum(1 for path in TARGET.rglob("*") if path.is_file())
    print(f"CloudBase Python 3.11 package ready: {file_count} files, {total_bytes / 1024 / 1024:.1f} MiB")


if __name__ == "__main__":
    main()
