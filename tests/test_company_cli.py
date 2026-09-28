import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import company_cli

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "company_cli.py"


class CompanyCliTests(unittest.TestCase):
    def test_herdr_launch_never_places_copilot_token_in_arguments(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".thesystem").mkdir()
            (workspace / ".thesystem" / "runtime").write_text("copilot\n")
            marker = "disposable-test-token-not-real"
            responses = [
                subprocess.CompletedProcess([], 0, marker + "\n", ""),
                subprocess.CompletedProcess([], 0, json.dumps({"result": {
                    "root_pane": {"pane_id": "p1"},
                    "workspace": {"workspace_id": "w1"},
                }}) + "\n", ""),
                subprocess.CompletedProcess([], 0, "", ""),
            ]
            with mock.patch.dict(os.environ, {"COPILOT_GITHUB_TOKEN": "", "GH_TOKEN": "", "GITHUB_TOKEN": ""}), \
                 mock.patch("company_cli.subprocess.run", side_effect=responses) as run, \
                 mock.patch("shutil.which", return_value="/usr/bin/herdr"), \
                 mock.patch("company_cli.emit"):
                self.assertEqual(company_cli.launch_master(workspace, json_mode=True), 0)
            self.assertEqual(run.call_count, 3)
            for call in run.call_args_list:
                self.assertNotIn(marker, " ".join(call.args[0]))

    def run_cli(self, workspace: Path | None, *args: str, cwd: Path | None = None):
        env = dict(os.environ)
        if workspace is None:
            env.pop("THESYSTEM_WORKSPACE", None)
        else:
            env["THESYSTEM_WORKSPACE"] = str(workspace)
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=str(cwd or ROOT),
            env=env,
            text=True,
            capture_output=True,
        )

    def test_add_project_creates_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            project = workspace / "acme"
            project.mkdir(parents=True)
            first = self.run_cli(workspace, "--json", "add-project", str(project))
            second = self.run_cli(workspace, "--json", "add-project", str(project))
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertFalse(json.loads(first.stdout)["idempotent"])
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertTrue(json.loads(second.stdout)["idempotent"])
            self.assertTrue(all((project / name).is_dir() for name in ("wiki", "agents", "tickets")))
            registry = json.loads((workspace / ".thesystem" / "projects.json").read_text())
            self.assertEqual([entry["path"] for entry in registry], [str(project.resolve())])

    def test_relative_project_resolves_from_caller_and_preserves_existing_content(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            project = workspace / "myFolder"
            wiki = project / "wiki"
            wiki.mkdir(parents=True)
            note = wiki / "existing.md"
            note.write_text("Keep this content.\n")
            result = self.run_cli(workspace, "add-project", "myFolder", "--json", cwd=workspace)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["project"], str(project.resolve()))
            self.assertEqual(note.read_text(), "Keep this content.\n")

    def test_json_alone_and_missing_binding_never_launch_chat(self):
        result = self.run_cli(None, "--json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["code"], "JSON_COMMAND_REQUIRED")
        result = self.run_cli(None, "add-project", "somewhere")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["code"], "WORKSPACE_NOT_BOUND")

    def test_rejects_source_clone_reserved_and_overlapping_projects(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir()
            source = workspace / "source"
            source.mkdir()
            (source / ".git").mkdir()
            result = self.run_cli(workspace, "add-project", str(source))
            self.assertEqual(json.loads(result.stdout)["code"], "PROJECT_IS_SOURCE_CLONE")
            for name in ("agents", "docs", ".agents", ".githooks", "tests"):
                reserved = workspace / name
                reserved.mkdir()
                result = self.run_cli(workspace, "add-project", str(reserved))
                self.assertEqual(json.loads(result.stdout)["code"], "PROJECT_RESERVED_PATH", name)
            project = workspace / "project"
            nested = project / "nested"
            nested.mkdir(parents=True)
            self.assertEqual(self.run_cli(workspace, "add-project", str(project)).returncode, 0)
            result = self.run_cli(workspace, "add-project", str(nested))
            self.assertEqual(json.loads(result.stdout)["code"], "PROJECT_OVERLAPS_REGISTERED")

    def test_rejects_infrastructure_symlink_without_registry_change(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace = root / "workspace"
            workspace.mkdir()
            project = workspace / "project"
            project.mkdir()
            outside = root / "outside"
            outside.mkdir()
            (project / "wiki").symlink_to(outside, target_is_directory=True)
            result = self.run_cli(workspace, "add-project", str(project))
            self.assertEqual(json.loads(result.stdout)["code"], "PROJECT_INFRASTRUCTURE_INVALID")
            self.assertFalse((workspace / ".thesystem").exists())
            self.assertFalse((project / "agents").exists())

    def test_rejects_registry_symlink_and_registry_escape(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace = root / "workspace"
            workspace.mkdir()
            project = workspace / "project"
            project.mkdir()
            state = workspace / ".thesystem"
            state.mkdir()
            outside = root / "outside.json"
            outside.write_text("[]")
            (state / "projects.json").symlink_to(outside)
            result = self.run_cli(workspace, "add-project", str(project))
            self.assertEqual(json.loads(result.stdout)["code"], "REGISTRY_INVALID")
            (state / "projects.json").unlink()
            (state / "projects.json").write_text(json.dumps([{"name": "x", "path": str(root / "escape")}]))
            result = self.run_cli(workspace, "add-project", str(project))
            self.assertEqual(json.loads(result.stdout)["code"], "REGISTRY_INVALID")


if __name__ == "__main__":
    unittest.main()
