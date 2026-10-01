"""Managed-file ownership must be usable without invoking an installer CLI."""
import importlib.util
import json
from pathlib import Path

import tempfile
import unittest

from thesystem.setup.managed_files import clean, identity, snapshot

ROOT = Path(__file__).resolve().parents[1]


class ManagedFilesTests(unittest.TestCase):
    def test_managed_files_module_preserves_snapshot_and_clean_contract(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "source"
            target = Path(td) / "workspace"
            source.mkdir()
            target.mkdir()
            for directory in (source, target):
                (directory / "README.md").write_text("managed\n")
            self.assertEqual(snapshot(source, target), 1)
            self.assertEqual(clean(target), {"removed": 1, "retained_modified": []})

    def test_legacy_manifest_roots_remain_supported(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td)
            paths = [target / "CONTEXT.md", target / "GLOSSARY-MAP.md"]
            for path in paths:
                path.write_text("legacy managed file\n")
            manifest = target / ".thesystem/managed.json"
            manifest.parent.mkdir()
            manifest.write_text(json.dumps({"version": 1, "entries": {p.name: identity(p) for p in paths}}))
            self.assertEqual(clean(target), {"removed": 2, "retained_modified": []})

    def test_cleanup_requires_valid_ownership_and_rejects_unsafe_paths(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td)
            with self.assertRaisesRegex(SystemExit, "without ownership manifest"):
                clean(target)
            manifest = target / ".thesystem/managed.json"
            manifest.parent.mkdir()
            manifest.write_text(json.dumps({"version": 2, "entries": {}}))
            with self.assertRaisesRegex(SystemExit, "invalid ownership manifest"):
                clean(target)
            for path in ("../outside", "/absolute", "payments/knowledge.md"):
                with self.subTest(path=path):
                    manifest.write_text(json.dumps({"version": 1, "entries": {path: ["file", "invalid"]}}))
                    with self.assertRaisesRegex(SystemExit, "unsafe ownership manifest path"):
                        clean(target)

    def test_cleanup_validates_every_entry_before_removing_any_file(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td)
            safe = target / "README.md"
            safe.write_text("owned content\n")
            manifest = target / ".thesystem/managed.json"
            manifest.parent.mkdir()
            manifest.write_text(json.dumps({"version": 1, "entries": {
                "README.md": identity(safe), "../outside": ["file", "0" * 64]
            }}))
            with self.assertRaisesRegex(SystemExit, "unsafe ownership manifest path"):
                clean(target)
            self.assertEqual(safe.read_text(), "owned content\n")

    def test_cleanup_refuses_a_symlink_parent_outside_workspace(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "workspace"
            outside = Path(td) / "outside"
            target.mkdir()
            outside.mkdir()
            victim = outside / "rule.md"
            victim.write_text("must survive\n")
            (target / "agents").symlink_to(outside, target_is_directory=True)
            manifest = target / ".thesystem/managed.json"
            manifest.parent.mkdir()
            manifest.write_text(json.dumps({"version": 1, "entries": {"agents/rule.md": identity(victim)}}))
            with self.assertRaisesRegex(SystemExit, "unsafe symlink parent"):
                clean(target)
            self.assertEqual(victim.read_text(), "must survive\n")

    def test_snapshot_tracks_symlinks_but_excludes_generated_files(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "source"
            target = Path(td) / "workspace"
            for directory in (source, target):
                package = directory / "thesystem"
                (package / "__pycache__").mkdir(parents=True)
                (package / "__init__.py").write_text("package\n")
                (package / "__pycache__/cache.pyc").write_bytes(b"cache")
                (directory / "README.md").symlink_to("missing.md")
            self.assertEqual(snapshot(source, target), 2)
            entries = json.loads((target / ".thesystem/managed.json").read_text())["entries"]
            self.assertEqual(entries["README.md"], ["symlink", "missing.md"])
            self.assertEqual(set(entries), {"README.md", "thesystem/__init__.py"})
            (target / "README.md").unlink()
            (target / "README.md").symlink_to("user-target.md")
            self.assertEqual(clean(target), {"removed": 1, "retained_modified": ["README.md"]})
            self.assertTrue((target / "README.md").is_symlink())

    def test_package_snapshot_and_cleanup_preserve_user_changes(self):
        self.assertIsNotNone(importlib.util.find_spec("thesystem"))
        from thesystem.setup.managed_files import clean, snapshot

        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "source"
            target = Path(td) / "workspace"
            source.mkdir()
            target.mkdir()
            for name in ("README.md", "MANUAL.md"):
                (source / name).write_text("managed\n")
                (target / name).write_text("managed\n")
            self.assertEqual(snapshot(source, target), 2)
            manifest = json.loads((target / ".thesystem/managed.json").read_text())
            self.assertEqual(manifest["version"], 1)
            (target / "MANUAL.md").write_text("user edit\n")
            project = target / "payments"
            project.mkdir()
            (project / "knowledge.md").write_text("company knowledge\n")

            self.assertEqual(clean(target), {"removed": 1, "retained_modified": ["MANUAL.md"]})
            self.assertFalse((target / "README.md").exists())
            self.assertEqual((target / "MANUAL.md").read_text(), "user edit\n")
            self.assertEqual((project / "knowledge.md").read_text(), "company knowledge\n")


if __name__ == "__main__":
    unittest.main()
