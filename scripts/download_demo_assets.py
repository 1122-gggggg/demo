#!/usr/bin/env python3
"""Download and verify the minimal replay assets from a GitHub release."""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
from pathlib import Path, PureWindowsPath
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "展示資產.sha256"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GITHUB_REPO_RE = re.compile(
    r"(?:https://github\.com/|git@github\.com:)([^/]+/[^/#]+?)(?:\.git)?/?$"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_manifest(path: Path = MANIFEST) -> dict[Path, str]:
    entries: dict[Path, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            checksum, name = line.split(maxsplit=1)
        except ValueError as error:
            raise ValueError(f"invalid manifest line {line_number}") from error
        asset_name = name.strip()
        relative = Path(asset_name)
        windows_relative = PureWindowsPath(asset_name)
        if (
            not SHA256_RE.fullmatch(checksum)
            or relative.is_absolute()
            or relative.anchor
            or windows_relative.anchor
            or ".." in relative.parts
            or ".." in windows_relative.parts
        ):
            raise ValueError(f"invalid manifest line {line_number}")
        entries[relative] = checksum
    if not entries:
        raise ValueError("asset manifest is empty")
    return entries


def asset_destination(relative: Path, root: Path = ROOT) -> Path:
    root = root.resolve()
    destination = (root / relative).resolve()
    if destination == root:
        raise ValueError(f"asset destination must be below project root: {relative}")
    try:
        destination.relative_to(root)
    except ValueError as error:
        raise ValueError(f"asset destination escapes project root: {relative}") from error
    return destination


def repository_from_remote(root: Path = ROOT) -> str | None:
    result = subprocess.run(
        ["git", "config", "--get", "remote.origin.url"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    match = GITHUB_REPO_RE.fullmatch(result.stdout.strip())
    return match.group(1) if match else None


def release_url(repository: str, relative_path: Path) -> str:
    return (
        f"https://github.com/{repository}/releases/latest/download/"
        f"{quote(relative_path.name)}"
    )


def download(url: str, destination: Path, checksum: str) -> None:
    temporary = destination.with_suffix(destination.suffix + ".part")
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"下載 {destination.relative_to(ROOT)}")
    try:
        with urlopen(Request(url, headers={"User-Agent": "central-demo-assets"}), timeout=60) as response:
            with temporary.open("wb") as handle:
                while block := response.read(8 * 1024 * 1024):
                    handle.write(block)
    except URLError as error:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"無法下載 {url}: {error.reason}") from error
    if sha256_file(temporary) != checksum:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"下載後雜湊不符：{destination.name}")
    temporary.replace(destination)


def sync_assets(repository: str) -> None:
    for relative, checksum in read_manifest().items():
        destination = asset_destination(relative)
        if destination.is_file() and sha256_file(destination) == checksum:
            print(f"已驗證 {relative}")
            continue
        download(release_url(repository, relative), destination, checksum)
    print("展示資產已準備完成。")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="GitHub repository in owner/name form")
    args = parser.parse_args()
    repository = args.repo or repository_from_remote()
    if not repository:
        raise SystemExit(
            "找不到 GitHub remote；請從 GitHub clone 專案，或加上 --repo owner/name。"
        )
    sync_assets(repository)


if __name__ == "__main__":
    main()
