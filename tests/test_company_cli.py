import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import company_cli
import thesystem.cli as company_command

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "company_cli.py"


class CompanyCliTests(unittest.TestCase):
    def test_every_company_orchestrator_action_requires_a_registered_project_before_dispatch(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            outside = Path(td) / "outside"
            workspace.mkdir()
            outside.mkdir()
            actions = {
                "create-task": ["--task", "one", "--source-clone", str(outside), "--command", "work"],
                "approve": ["--task", "one"],
                "start": ["--task", "one"],
                "status": ["--task", "one"],
                "cancel": ["--run", "run1"],
                "integrate": ["--run", "run1"],
            }
            for prefix in ([], ["orchestrator"]):
                for action, options in actions.items():
                    with self.subTest(prefix=prefix, action=action):
                        result = self.run_cli(workspace, *prefix, action, "--project", str(outside), *options)
                        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                        self.assertEqual(json.loads(result.stdout)["code"], "PROJECT_OUTSIDE_WORKSPACE")
            self.assertFalse((outside / ".thesystem" / "orchestrator").exists())

    def test_every_company_orchestrator_action_rejects_an_unregistered_in_workspace_project(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            project = workspace / "unregistered"
            project.mkdir(parents=True)
            actions = {
                "create-task": ["--task", "one", "--source-clone", str(project), "--command", "work"],
                "approve": ["--task", "one"],
                "start": ["--task", "one"],
                "status": ["--task", "one"],
                "cancel": ["--run", "run1"],
                "integrate": ["--run", "run1"],
            }
            for prefix in ([], ["orchestrator"]):
                for action, options in actions.items():
                    with self.subTest(prefix=prefix, action=action):
                        result = self.run_cli(workspace, *prefix, action, "--project", str(project), *options)
                        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                        self.assertEqual(json.loads(result.stdout)["code"], "PROJECT_NOT_REGISTERED")
            self.assertFalse((project / ".thesystem" / "orchestrator").exists())

    def test_retry_and_evidence_refuse_outside_or_unregistered_projects_before_orchestrator_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace = root / "workspace"
            workspace.mkdir()
            outside = root / "outside"
            outside.mkdir()
            unregistered = workspace / "unregistered"
            unregistered.mkdir()
            for project, code in ((outside, "PROJECT_OUTSIDE_WORKSPACE"),
                                  (unregistered, "PROJECT_NOT_REGISTERED")):
                for command in (("retry", "--project", str(project), "--task", "missing"),
                                ("evidence", "--project", str(project), "--run", "missing")):
                    with self.subTest(project=project, command=command):
                        result = self.run_cli(workspace, *command)
                        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                        self.assertEqual(json.loads(result.stdout)["code"], code)
                        self.assertFalse((project / ".thesystem" / "orchestrator").exists())

    def test_every_project_command_validates_scope_before_orchestrator_construction(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace = root / "workspace"
            workspace.mkdir()
            outside = root / "outside"
            outside.mkdir()
            unregistered = workspace / "unregistered"
            unregistered.mkdir()
            commands = (
                ("create-task", "--project", None, "--task", "t", "--source-clone", None, "--command", "work"),
                ("approve", "--project", None, "--task", "t"),
                ("start", "--project", None, "--task", "t"),
                ("status", "--project", None),
                ("cancel", "--project", None, "--run", "r"),
                ("integrate", "--project", None, "--run", "r"),
                ("retry", "--project", None, "--task", "t"),
                ("evidence", "--project", None, "--run", "r"),
            )
            for project, code in ((outside, "PROJECT_OUTSIDE_WORKSPACE"),
                                  (unregistered, "PROJECT_NOT_REGISTERED")):
                for command in commands:
                    args = [part if part is not None else str(project) for part in command]
                    if args[0] == "create-task":
                        args[args.index("--source-clone") + 1] = str(project)
                    for prefix in ([], ["orchestrator"]):
                        if args[0] in {"retry", "evidence"} and prefix:
                            continue
                        with self.subTest(project=project, command=args, prefix=prefix), \
                             mock.patch.dict(os.environ, {"THESYSTEM_WORKSPACE": str(workspace)}), \
                             mock.patch("the_system_orchestrator.Orchestrator") as orchestrator, \
                             mock.patch("thesystem.cli.emit") as emit:
                            result = company_command.main([*prefix, *args])
                            self.assertEqual(result, 2)
                            self.assertEqual(emit.call_args.args[0]["code"], code)
                            orchestrator.assert_not_called()

    def test_raw_standalone_orchestrator_status_does_not_require_company_registration(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "raw project"
            project.mkdir()
            result = subprocess.run(
                [sys.executable, str(ROOT / "orchestrator"), "status", "--project", str(project)],
                cwd=td, env={key: value for key, value in os.environ.items() if key != "THESYSTEM_WORKSPACE"},
                text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {"runs": [], "tasks": []})

    def test_source_clone_registration_is_project_scoped_and_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            project = workspace / "payments"
            clone = project / "api"
            clone.mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(clone)], check=True)
            self.assertEqual(self.run_cli(workspace, "add-project", str(project)).returncode, 0)
            first = self.run_cli(workspace, "add-source-clone", str(project), str(clone))
            second = self.run_cli(workspace, "add-source-clone", str(project), str(clone))
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertFalse(json.loads(first.stdout)["idempotent"])
            self.assertTrue(json.loads(second.stdout)["idempotent"])
            registered = json.loads((workspace / ".thesystem" / "source-clones.json").read_text())
            self.assertEqual(registered, [{"project": str(project.resolve()), "path": str(clone.resolve())}])

    def test_source_clone_registration_refuses_unregistered_project_and_escape(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            project = workspace / "payments"
            clone = Path(td) / "api"
            project.mkdir(parents=True)
            clone.mkdir()
            subprocess.run(["git", "init", "-q", str(clone)], check=True)
            result = self.run_cli(workspace, "add-source-clone", str(project), str(clone))
            self.assertEqual(json.loads(result.stdout)["code"], "PROJECT_NOT_REGISTERED")

    def test_create_task_cannot_bypass_registered_source_clone(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            project = workspace / "payments"
            clone = project / "api"
            clone.mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(clone)], check=True)
            self.assertEqual(self.run_cli(workspace, "add-project", str(project)).returncode, 0)
            result = self.run_cli(workspace, "create-task", "--project", str(project), "--task", "one",
                                  "--source-clone", str(clone), "--command", "add a test")
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)["code"], "SOURCE_CLONE_NOT_REGISTERED")

    def test_set_role_writes_safe_project_role_configuration(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            project = workspace / "payments"
            project.mkdir(parents=True)
            self.assertEqual(self.run_cli(workspace, "add-project", str(project)).returncode, 0)
            result = self.run_cli(workspace, "set-role", str(project), "api", "--rule", "rules/no-secrets.md", "--cli", "git")
            self.assertEqual(result.returncode, 0, result.stderr)
            roles = json.loads((project / "agents" / "roles.yaml").read_text())
            self.assertEqual(roles["api"], {"rules": ["rules/no-secrets.md"], "clis": ["git"]})
            unsafe = self.run_cli(workspace, "set-role", str(project), "../escape")
            self.assertEqual(json.loads(unsafe.stdout)["code"], "ROLE_INVALID")

    def test_role_setup_refuses_a_reviewer_missing_worker_rules(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            project = workspace / "payments"
            project.mkdir(parents=True)
            self.assertEqual(self.run_cli(workspace, "add-project", str(project)).returncode, 0)
            self.assertEqual(self.run_cli(workspace, "set-role", str(project), "reviewer").returncode, 0)
            result = self.run_cli(workspace, "set-role", str(project), "worker", "--rule", "rules/no-secrets.md")
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)["code"], "REVIEWER_RULES_MISSING")

    def test_retry_refuses_non_retryable_status_without_starting_a_run(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            project = workspace / "payments"
            project.mkdir(parents=True)
            self.assertEqual(self.run_cli(workspace, "add-project", str(project)).returncode, 0)
            state = project / ".thesystem" / "orchestrator" / "state.json"
            state.parent.mkdir(parents=True)
            state.write_text(json.dumps({"version": 2, "tasks": {"one": {"id": "one", "approval": "approved"}}, "runs": {"run1": {"id": "run1", "task_id": "one", "status": "passed"}}}))
            result = self.run_cli(workspace, "retry", "--project", str(project), "--task", "one")
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)["code"], "RETRY_NOT_ALLOWED")

    def test_evidence_reads_immutable_record_and_learning_delegates_to_native_reviewer(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            project = workspace / "payments"
            project.mkdir(parents=True)
            self.assertEqual(self.run_cli(workspace, "add-project", str(project)).returncode, 0)
            evidence = project / ".thesystem" / "orchestrator" / "runs" / "abc.json"
            evidence.parent.mkdir(parents=True)
            evidence.write_text(json.dumps({"id": "abc", "status": "changes-requested"}))
            result = self.run_cli(workspace, "evidence", "--project", str(project), "--run", "abc")
            self.assertEqual(json.loads(result.stdout)["run"]["status"], "changes-requested")
            with mock.patch.dict(os.environ, {"THESYSTEM_WORKSPACE": str(workspace)}), \
                 mock.patch("thesystem.learning.subprocess.run", return_value=subprocess.CompletedProcess([], 0, '{"counts": {"memory": 0}}', "")) as run, \
                 mock.patch("thesystem.cli.emit"):
                self.assertEqual(company_cli.main(["learning", "inventory"]), 0)
            command = run.call_args.args[0]
            self.assertIn("inventory", command)
            self.assertTrue(command[1].endswith("review_memory_requests.py"))

    def test_invalid_evidence_returns_error_exit_and_filesystem_failures_are_json(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            project = workspace / "payments"
            project.mkdir(parents=True)
            self.assertEqual(self.run_cli(workspace, "add-project", str(project)).returncode, 0)

            runs = project / ".thesystem/orchestrator/runs"
            runs.mkdir(parents=True)
            (runs / "malformed.json").write_text("not json")
            malformed = self.run_cli(workspace, "evidence", "--project", str(project), "--run", "malformed")
            self.assertEqual(malformed.returncode, 1, malformed.stdout + malformed.stderr)
            self.assertEqual(json.loads(malformed.stdout)["code"], "EVIDENCE_INVALID")

            (runs / "malformed.json").unlink()
            runs.rmdir()
            runs.write_text("not a directory")
            inaccessible = self.run_cli(workspace, "evidence", "--project", str(project), "--run", "broken")
            self.assertEqual(inaccessible.returncode, 1, inaccessible.stdout + inaccessible.stderr)
            self.assertEqual(json.loads(inaccessible.stdout)["code"], "EVIDENCE_INVALID")

    def test_company_orchestration_requires_binding_before_lifecycle_construction(self):
        result = self.run_cli(None, "status", "--project", "/tmp/outside")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["code"], "WORKSPACE_NOT_BOUND")

    def test_orchestrator_duplicate_and_malformed_options_fail_before_lifecycle_loading(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            project = workspace / "project"
            project.mkdir(parents=True)
            self.assertEqual(self.run_cli(workspace, "add-project", str(project)).returncode, 0)

            cases = (
                ("status", "--project", str(project), "--project", str(project)),
                ("status", "--project", str(project), "--unknown", "value"),
                ("status", "--project", str(project), "--task"),
                ("approve", "--project", str(project), "--task", "missing", "--timeout", "bad"),
            )
            for command in cases:
                with self.subTest(command=command):
                    result = self.run_cli(workspace, *command)
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(json.loads(result.stdout)["code"],
                                     "TIMEOUT_INVALID" if "bad" in command else "ORCHESTRATOR_USAGE")
                    self.assertEqual(len(result.stdout.splitlines()), 1)
            self.assertFalse((project / ".thesystem" / "orchestrator").exists())

    def test_company_task_not_found_retains_orchestrator_error_code(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            project = workspace / "project"
            project.mkdir(parents=True)
            registered = self.run_cli(workspace, "add-project", str(project))
            self.assertEqual(registered.returncode, 0, registered.stderr)

            result = self.run_cli(workspace, "status", "--project", str(project), "--task", "missing")

            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)["code"], "TASK_NOT_FOUND")

    def test_no_arguments_show_help_without_binding_or_subprocesses(self):
        with mock.patch("thesystem.cli.workspace_path") as workspace, \
             mock.patch("thesystem.cli.subprocess.run") as run, \
             mock.patch("thesystem.cli.subprocess.call") as call, \
             mock.patch("builtins.print") as output:
            self.assertEqual(company_cli.main([]), 0)
        output.assert_called_once_with(company_command.usage())
        workspace.assert_not_called()
        run.assert_not_called()
        call.assert_not_called()
        result = self.run_cli(None)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Usage: COMPANY", result.stdout)

    def test_removed_launch_commands_are_rejected_without_subprocesses(self):
        for args in (["launch"], ["--direct"], ["--json", "launch"], ["--json", "--direct"]):
            with self.subTest(args=args), \
                 mock.patch("thesystem.cli.subprocess.run") as run, \
                 mock.patch("thesystem.cli.subprocess.call") as call, \
                 mock.patch("thesystem.cli.emit") as emit:
                self.assertEqual(company_cli.main(args), 2)
                self.assertEqual(emit.call_args.args[0]["code"], "UNKNOWN_COMMAND")
                run.assert_not_called()
                call.assert_not_called()

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
            for name in ("agents", "docs", ".agents", ".githooks", "tests", "thesystem"):
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
