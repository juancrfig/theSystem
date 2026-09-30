"""Workspace registration operations preserve registered user data."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from thesystem.workspace import Workspace, WorkspaceError


class WorkspaceTests(unittest.TestCase):
    def test_project_and_source_clone_registration_are_idempotent_and_preserve_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace_path = root / "workspace"
            project = workspace_path / "payments"
            clone = project / "api"
            clone.mkdir(parents=True)
            (project / "wiki").mkdir()
            note = project / "wiki" / "existing.md"
            note.write_text("keep this\n")
            subprocess.run(["git", "init", "-q", str(clone)], check=True)
            workspace = Workspace(workspace_path)

            first = workspace.register_project(project)
            repeated = workspace.register_project(project)
            clone_first = workspace.register_source_clone(project, clone)
            clone_repeated = workspace.register_source_clone(project, clone)

            self.assertEqual(first, {"project": str(project.resolve()), "idempotent": False})
            self.assertEqual(repeated, {"project": str(project.resolve()), "idempotent": True})
            self.assertEqual(clone_first, {"project": str(project.resolve()), "source_clone": str(clone.resolve()), "idempotent": False})
            self.assertTrue(clone_repeated["idempotent"])
            self.assertEqual(note.read_text(), "keep this\n")
            self.assertEqual(workspace.require_registered_project(project), project.resolve())
            self.assertEqual(workspace.require_registered_clone(project, clone), clone.resolve())

    def test_registration_refuses_outside_overlapping_and_unregistered_clone_before_registry_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace_path = root / "workspace"
            workspace_path.mkdir()
            project = workspace_path / "project"
            nested = project / "nested"
            nested.mkdir(parents=True)
            outside = root / "outside"
            outside.mkdir()
            workspace = Workspace(workspace_path)
            workspace.register_project(project)
            before = (workspace_path / ".thesystem" / "projects.json").read_bytes()

            with self.assertRaises(WorkspaceError) as failure:
                workspace.register_project(outside)
            self.assertEqual(failure.exception.code, "PROJECT_OUTSIDE_WORKSPACE")
            with self.assertRaises(WorkspaceError) as failure:
                workspace.register_project(nested)
            self.assertEqual(failure.exception.code, "PROJECT_OVERLAPS_REGISTERED")
            unregistered_clone = project / "unregistered"
            unregistered_clone.mkdir()
            subprocess.run(["git", "init", "-q", str(unregistered_clone)], check=True)
            with self.assertRaises(WorkspaceError) as failure:
                workspace.require_registered_clone(project, unregistered_clone)
            self.assertEqual(failure.exception.code, "SOURCE_CLONE_NOT_REGISTERED")
            self.assertEqual((workspace_path / ".thesystem" / "projects.json").read_bytes(), before)

    def test_registration_refuses_symlink_registry_lock_without_writing_outside(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace_path = root / "workspace"
            workspace_path.mkdir()
            project = workspace_path / "project"
            project.mkdir()
            registry_dir = workspace_path / ".thesystem"
            registry_dir.mkdir()
            outside = root / "outside.lock"
            outside.write_text("unchanged")
            (registry_dir / "projects.lock").symlink_to(outside)

            with self.assertRaises(WorkspaceError) as failure:
                Workspace(workspace_path).register_project(project)
            self.assertEqual(failure.exception.code, "REGISTRY_INVALID")
            self.assertEqual(outside.read_text(), "unchanged")
            self.assertFalse((registry_dir / "projects.json").exists())

    def test_concurrent_project_registrations_preserve_both_registry_entries(self):
        from concurrent.futures import ThreadPoolExecutor

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace_path = root / "workspace"
            projects = [workspace_path / "one", workspace_path / "two"]
            for project in projects:
                project.mkdir(parents=True)

            def register(project):
                return Workspace(workspace_path).register_project(project)

            with ThreadPoolExecutor(max_workers=2) as workers:
                results = list(workers.map(register, projects))

            self.assertEqual(len(results), 2)
            entries = json.loads((workspace_path / ".thesystem" / "projects.json").read_text())
            self.assertEqual({entry["path"] for entry in entries}, {str(path.resolve()) for path in projects})

    def test_malformed_registry_is_not_reinitialized(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace_path = root / "workspace"
            project = workspace_path / "project"
            project.mkdir(parents=True)
            registry_dir = workspace_path / ".thesystem"
            registry_dir.mkdir()
            registry = registry_dir / "projects.json"
            registry.write_text("{invalid")

            with self.assertRaises(WorkspaceError) as failure:
                Workspace(workspace_path).register_project(project)
            self.assertEqual(failure.exception.code, "REGISTRY_INVALID")
            self.assertEqual(registry.read_text(), "{invalid")

    def test_malformed_source_clone_registry_is_refused_by_registration_and_lookup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace_path = root / "workspace"
            project = workspace_path / "project"
            clone = project / "clone"
            clone.mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(clone)], check=True)
            workspace = Workspace(workspace_path)
            workspace.register_project(project)
            registry = workspace_path / ".thesystem" / "source-clones.json"
            registry.write_text(json.dumps([{"path": str(clone)}]))
            original = registry.read_bytes()

            with self.assertRaises(WorkspaceError) as failure:
                workspace.register_source_clone(project, clone)
            self.assertEqual(failure.exception.code, "SOURCE_CLONE_REGISTRY_INVALID")
            with self.assertRaises(WorkspaceError) as failure:
                workspace.require_registered_clone(project, clone)
            self.assertEqual(failure.exception.code, "SOURCE_CLONE_REGISTRY_INVALID")
            self.assertEqual(registry.read_bytes(), original)

    def test_source_clone_registry_symlink_is_refused_without_external_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace_path = root / "workspace"
            project = workspace_path / "project"
            clone = project / "clone"
            clone.mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(clone)], check=True)
            workspace = Workspace(workspace_path)
            workspace.register_project(project)
            outside = root / "source-clones.json"
            outside.write_text("[]")
            registry = workspace_path / ".thesystem" / "source-clones.json"
            registry.symlink_to(outside)

            with self.assertRaises(WorkspaceError) as failure:
                workspace.register_source_clone(project, clone)
            self.assertEqual(failure.exception.code, "SOURCE_CLONE_REGISTRY_INVALID")
            self.assertEqual(outside.read_text(), "[]")
            self.assertTrue(registry.is_symlink())

    def test_concurrent_source_clone_registrations_preserve_both_entries(self):
        from concurrent.futures import ThreadPoolExecutor

        with tempfile.TemporaryDirectory() as temporary:
            workspace_path = Path(temporary) / "workspace"
            project = workspace_path / "project"
            clones = [project / "one", project / "two"]
            for clone in clones:
                clone.mkdir(parents=True)
                subprocess.run(["git", "init", "-q", str(clone)], check=True)
            workspace = Workspace(workspace_path)
            workspace.register_project(project)

            with ThreadPoolExecutor(max_workers=2) as workers:
                results = list(workers.map(lambda clone: workspace.register_source_clone(project, clone), clones))

            self.assertEqual(len(results), 2)
            entries = json.loads((workspace_path / ".thesystem" / "source-clones.json").read_text())
            self.assertEqual({entry["path"] for entry in entries}, {str(clone.resolve()) for clone in clones})


if __name__ == "__main__":
    unittest.main()
