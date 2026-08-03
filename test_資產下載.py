import tempfile
import unittest
from pathlib import Path

from scripts.download_demo_assets import (
    asset_destination,
    read_manifest,
    release_url,
    repository_from_remote,
)


class AssetDownloadTests(unittest.TestCase):
    def test_manifest_rejects_parent_path(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "assets.sha256"
            manifest.write_text("0" * 64 + "  ../unexpected.bin\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_manifest(manifest)

    def test_manifest_rejects_windows_rooted_path(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "assets.sha256"
            for asset_name in (
                r"\outside\unexpected.bin",
                r"C:\outside\unexpected.bin",
                r"C:outside\unexpected.bin",
                r"\\server\share\unexpected.bin",
            ):
                manifest.write_text(
                    "0" * 64 + f"  {asset_name}\n", encoding="utf-8"
                )
                with self.subTest(asset_name=asset_name):
                    with self.assertRaises(ValueError):
                        read_manifest(manifest)

    def test_resolved_destination_cannot_escape_project_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            root.mkdir()
            with self.assertRaises(ValueError):
                asset_destination(Path("../outside.bin"), root)
            with self.assertRaises(ValueError):
                asset_destination(Path("."), root)

    def test_resolved_destination_rejects_symlink_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            outside = Path(directory) / "outside"
            root.mkdir()
            outside.mkdir()
            linked = root / "linked"
            try:
                linked.symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("symlink creation is unavailable")
            with self.assertRaises(ValueError):
                asset_destination(Path("linked/asset.bin"), root)

    def test_release_url_uses_asset_filename(self):
        url = release_url(
            "owner/repository",
            Path("定位回放/P1370137_demo_960x540.mp4"),
        )
        self.assertEqual(
            url,
            "https://github.com/owner/repository/releases/latest/download/"
            "P1370137_demo_960x540.mp4",
        )

    def test_missing_remote_returns_none(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(repository_from_remote(Path(directory)))


if __name__ == "__main__":
    unittest.main()
