"""Role updates validate references and serialize through the workspace lock."""
import json
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

from thesystem.guidance import GuidanceError, update_project_role
from thesystem.workspace import Workspace


class GuidanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.workspace_path = self.root / "workspace"
        self.project = self.workspace_path / "project"
        self.project.mkdir(parents=True)
        self.workspace = Workspace(self.workspace_path)
        self.workspace.register_project(self.project)
        self.roles_file = self.project / "agents" / "roles.yaml"

    def test_role_update_preserves_other_roles_and_rejects_unsafe_references_without_writing(self):
        self.roles_file.write_text(json.dumps({"api": {"clis": ["git"]}, "worker": {"rules": []}, "reviewer": {"rules": []}}))
        result = update_project_role(self.workspace, self.project, "api", {"rules": ["rules/safe.md"], "clis": ["git"]})
        document = json.loads(self.roles_file.read_text())
        self.assertEqual(document["api"], {"rules": ["rules/safe.md"], "clis": ["git"]})
        self.assertEqual(document["worker"], {"rules": []})
        before = self.roles_file.read_bytes()
        with self.assertRaises(GuidanceError) as failure:
            update_project_role(self.workspace, self.project, "api", {"rules": ["../outside.md"]})
        self.assertEqual(failure.exception.code, "ROLE_INVALID")
        self.assertEqual(self.roles_file.read_bytes(), before)

    def test_reviewer_coverage_refusal_preserves_previous_role_document(self):
        self.roles_file.write_text(json.dumps({"worker": {"rules": ["rules/required.md"]}, "reviewer": {"rules": []}}))
        before = self.roles_file.read_bytes()
        with self.assertRaises(GuidanceError) as failure:
            update_project_role(self.workspace, self.project, "worker", {"rules": ["rules/new.md"]})
        self.assertEqual(failure.exception.code, "REVIEWER_RULES_MISSING")
        self.assertEqual(self.roles_file.read_bytes(), before)

    def test_concurrent_role_updates_preserve_both_roles(self):
        def update(role):
            return update_project_role(self.workspace, self.project, role, {"clis": [role]})

        with ThreadPoolExecutor(max_workers=2) as workers:
            list(workers.map(update, ("api", "web")))

        self.assertEqual(set(json.loads(self.roles_file.read_text())), {"api", "web"})

    def test_symlinked_project_agents_directory_is_refused_without_external_write(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.project / "agents").rmdir()
        (self.project / "agents").symlink_to(outside, target_is_directory=True)
        target = outside / "roles.yaml"
        target.write_text("preserve")

        with self.assertRaises(GuidanceError) as failure:
            update_project_role(self.workspace, self.project, "api", {"clis": ["git"]})

        self.assertEqual(failure.exception.code, "ROLE_CONFIG_INVALID")
        self.assertEqual(target.read_text(), "preserve")

    def test_dangling_role_file_symlink_is_refused_without_replacement(self):
        link = self.project / "agents" / "roles.yaml"
        target = self.root / "missing-roles.yaml"
        link.symlink_to(target)

        with self.assertRaises(GuidanceError) as failure:
            update_project_role(self.workspace, self.project, "api", {"clis": ["git"]})

        self.assertEqual(failure.exception.code, "ROLE_CONFIG_INVALID")
        self.assertTrue(link.is_symlink())
        self.assertFalse(target.exists())

    def test_unsupported_yaml_is_not_overwritten(self):
        self.roles_file.write_text("worker:\n  rules: [safe]\n")
        before = self.roles_file.read_bytes()
        with self.assertRaises(GuidanceError) as failure:
            update_project_role(self.workspace, self.project, "api", {"clis": ["git"]})
        self.assertEqual(failure.exception.code, "ROLE_CONFIG_UNSUPPORTED")
        self.assertEqual(self.roles_file.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
