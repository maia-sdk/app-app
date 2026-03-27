from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def _repo_python() -> Path | None:
    root = Path(__file__).resolve().parents[1]
    candidates = [
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
    ]
    current = Path(sys.executable).resolve()
    for candidate in candidates:
        if candidate.exists() and candidate.resolve() != current:
            return candidate.resolve()
    return None


def _playwright_cli_commands() -> list[list[str]]:
    commands: list[list[str]] = []
    exe_dir = Path(sys.executable).resolve().parent
    sibling = exe_dir / ("playwright.exe" if sys.platform.startswith("win") else "playwright")
    if sibling.exists():
        commands.append([str(sibling)])
    discovered = shutil.which("playwright")
    if discovered:
        commands.append([discovered])
    commands.append([sys.executable, "-m", "playwright"])
    deduped: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for command in commands:
        key = tuple(command)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(command)
    return deduped


def _import_playwright() -> tuple[bool, str]:
    try:
        import playwright.sync_api  # noqa: F401
        return True, ""
    except Exception as exc:
        return False, str(exc)


def _launch_browser() -> tuple[bool, str]:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            browser.close()
        return True, ""
    except Exception as exc:
        return False, str(exc)


def ensure_runtime(*, install: bool) -> int:
    package_ok, import_error = _import_playwright()
    if not package_ok and install:
        print("Installing Playwright package...")
        _run([sys.executable, "-m", "pip", "install", "playwright>=1.58.0,<2"])
        package_ok, import_error = _import_playwright()

    if not package_ok:
        print("Maia computer runtime is not ready.")
        print(f"Missing Python package: {import_error}")
        print("Run: python scripts/ensure_computer_use_runtime.py --install")
        return 1

    browser_ok, browser_error = _launch_browser()
    if browser_ok:
        print("Maia computer runtime is ready.")
        return 0

    if install:
        print("Installing Chromium runtime for Maia computer...")
        last_error = browser_error
        for command in _playwright_cli_commands():
            try:
                _run([*command, "install", "chromium"])
                browser_ok, browser_error = _launch_browser()
                if browser_ok:
                    print("Maia computer runtime is ready.")
                    return 0
                last_error = browser_error
            except Exception as exc:
                last_error = str(exc)
        print("Maia computer runtime installation failed.")
        print(last_error)
        return 1

    print("Maia computer runtime is not ready.")
    print(browser_error)
    print("Run: python scripts/ensure_computer_use_runtime.py --install")
    return 1


def main() -> int:
    preferred_python = _repo_python()
    if preferred_python is not None:
        return subprocess.call([str(preferred_python), __file__, *sys.argv[1:]])

    parser = argparse.ArgumentParser(
        description="Verify or install the Maia computer browser runtime."
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Install missing Playwright package/browser runtime if needed.",
    )
    args = parser.parse_args()
    return ensure_runtime(install=bool(args.install))


if __name__ == "__main__":
    raise SystemExit(main())
