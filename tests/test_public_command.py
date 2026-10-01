"""Public command probes use only temporary HOME and workspace state."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tarfile
import unittest
from contextlib import redirect_stdout
import io
from unittest.mock import patch

import thesystem.setup.workflow as workflow
from thesystem.setup.workflow import _hermes_target

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "bin/thesystem"


class PublicCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="public-thesystem-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.env = dict(os.environ, HOME=str(self.home), PATH=f"{self.home / '.local/bin'}:{os.environ['PATH']}", PYTHONDONTWRITEBYTECODE="1")
        self.env.pop("HERMES_HOME", None)

    def run_command(self, *args, executable=LAUNCHER):
        return subprocess.run([str(executable), *args], cwd=self.root, env=self.env, text=True, capture_output=True)

    def test_no_arguments_and_help_are_read_only_and_invalid_command_is_usage_error(self):
        before = set(self.root.rglob("*"))
        for arguments in ((), ("--help",)):
            result = self.run_command(*arguments)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Usage: thesystem", result.stdout)
        invalid = self.run_command("not-a-command")
        self.assertEqual(invalid.returncode, 2)
        self.assertEqual(set(self.root.rglob("*")), before)

    def test_runtime_free_install_configures_global_command_and_optional_workspace_alias(self):
        result = self.run_command("install", "--workspace", str(self.workspace), "--runtime", "none",
                                  "--company", "Acme", "--non-interactive")
        self.assertEqual(result.returncode, 0, result.stderr)
        installed = self.home / ".local/bin/thesystem"
        alias = self.home / ".local/bin/Acme"
        self.assertTrue(installed.is_file())
        self.assertTrue(alias.is_file())
        self.assertEqual((self.workspace / ".thesystem/runtime").read_text().strip(), "none")
        help_result = subprocess.run([str(installed), "--help"], env=self.env, text=True, capture_output=True)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        project = self.workspace / "project"
        project.mkdir()
        registration = subprocess.run([str(alias), "add-project", str(project)], env=self.env, text=True, capture_output=True)
        self.assertEqual(registration.returncode, 0, registration.stderr)
        self.assertFalse(json.loads(registration.stdout).get("idempotent"))

        # The alias supplies its workspace to lifecycle commands when no override is given.
        bound_upgrade = subprocess.run([str(alias), "upgrade", "--runtime", "none"], env=self.env,
                                       text=True, capture_output=True)
        self.assertEqual(bound_upgrade.returncode, 0, bound_upgrade.stderr)
        self.assertIn(str(self.workspace), bound_upgrade.stdout)

        repeated = self.run_command("install", "--workspace", str(self.workspace), "--runtime", "none",
                                    "--company", "Acme", "--non-interactive")
        self.assertEqual(repeated.returncode, 0, repeated.stderr)

    def test_upgrade_rollback_and_uninstall_preserve_modified_files_and_shared_launcher(self):
        installed = self.run_command("install", "--workspace", str(self.workspace), "--runtime", "none")
        self.assertEqual(installed.returncode, 0, installed.stderr)
        manual = self.workspace / "MANUAL.md"
        manual.write_text("workspace-owned edit\n")
        project = self.workspace / "project"
        (project / "wiki").mkdir(parents=True)
        knowledge = project / "wiki/notes.md"
        knowledge.write_text("keep project knowledge\n")
        unowned = self.workspace / "agents/tools/local-tool.md"
        unowned.parent.mkdir(parents=True, exist_ok=True)
        unowned.write_text("keep unowned workspace tool\n")

        upgraded = self.run_command("upgrade", "--workspace", str(self.workspace))
        self.assertEqual(upgraded.returncode, 0, upgraded.stderr)
        self.assertEqual(manual.read_text(), "workspace-owned edit\n")
        rolled = self.run_command("rollback", "--workspace", str(self.workspace))
        self.assertEqual(rolled.returncode, 0, rolled.stderr)
        self.assertIn("Hermes readiness ready (exit 0)", rolled.stdout)
        rolled_json = self.run_command("rollback", "--workspace", str(self.workspace), "--json")
        self.assertEqual(rolled_json.returncode, 0, rolled_json.stderr)
        readiness = json.loads(rolled_json.stdout)
        self.assertEqual(readiness["readiness_exit_code"], 0)
        self.assertTrue(readiness["readiness"]["ready"])
        self.assertEqual(manual.read_text(), "workspace-owned edit\n")
        removed = self.run_command("uninstall", "--workspace", str(self.workspace))
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertEqual(manual.read_text(), "workspace-owned edit\n")
        self.assertEqual(knowledge.read_text(), "keep project knowledge\n")
        self.assertEqual(unowned.read_text(), "keep unowned workspace tool\n")
        self.assertTrue((self.home / ".local/bin/thesystem").is_file())

    def test_downloaded_launcher_acquires_python_and_validates_source_archive(self):
        archive = self.root / "distribution.tar.gz"
        from thesystem.setup.distribution import DISTRIBUTION_PATHS
        with tarfile.open(archive, "w:gz") as bundle:
            for name in DISTRIBUTION_PATHS:
                path = ROOT / name
                if path.exists():
                    bundle.add(path, arcname=f"theSystem-master/{name}")
        downloaded = self.root / "thesystem"
        shutil.copy2(LAUNCHER, downloaded)
        downloaded.chmod(0o755)
        self.env["THESYSTEM_ARCHIVE_URL"] = archive.as_uri()
        self.env["XDG_CACHE_HOME"] = str(self.root / "cache")
        self.env["TMPDIR"] = str(self.root)
        self.env["PATH"] = f"{self.root / 'bin'}:/usr/bin:/bin"
        bindir = self.root / "bin"
        bindir.mkdir()
        fake_apt = bindir / "apt-get"
        fake_apt.write_text(f"#!/bin/sh\nln -sf {sys.executable} {bindir / 'python3'}\n")
        fake_apt.chmod(0o755)
        result = self.run_command("install", "--workspace", str(self.workspace), "--runtime", "none", "--non-interactive", executable=downloaded)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.home / ".local/bin/thesystem").is_file())

    def test_skill_link_replaces_only_empty_directory_and_preserves_nonempty_conflict(self):
        from thesystem.setup.provisioning import link_project_skills
        canonical = self.workspace / "agents/skills/sample"
        canonical.mkdir(parents=True)
        (canonical / "SKILL.md").write_text("skill")
        link = self.workspace / ".agents/skills"
        link.mkdir(parents=True)
        self.assertTrue(link_project_skills(self.workspace))
        self.assertTrue(link.is_symlink())
        link.unlink()
        link.mkdir()
        sentinel = link / "keep"
        sentinel.write_text("user data")
        with self.assertRaises(ValueError):
            link_project_skills(self.workspace)
        self.assertEqual(sentinel.read_text(), "user data")

    def test_hermes_install_blocks_non_git_workspace_before_distribution_writes(self):
        result = self.run_command("install", "--workspace", str(self.workspace), "--runtime", "hermes", "--non-interactive")
        self.assertEqual(result.returncode, 1)
        self.assertIn("HERMES_PROJECT_DISCOVERY_UNSUPPORTED", result.stderr)
        self.assertFalse((self.workspace / "thesystem").exists())
        self.assertFalse((self.home / ".local/share/thesystem").exists())

    def test_uninstall_one_workspace_preserves_the_shared_command_and_other_alias(self):
        other = self.root / "other-workspace"
        other.mkdir()
        first = self.run_command("install", "--workspace", str(self.workspace), "--runtime", "none", "--company", "First")
        second = self.run_command("install", "--workspace", str(other), "--runtime", "none", "--company", "Second")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        override = subprocess.run([str(self.home / ".local/bin/First"), "upgrade", "--workspace", str(other),
                                   "--runtime", "none"], env=self.env, text=True, capture_output=True)
        self.assertEqual(override.returncode, 0, override.stderr)
        self.assertIn(str(other), override.stdout)
        lookalike = self.home / ".local/bin/Lookalike"
        lookalike.write_text(f"#!/bin/sh\n# THESYSTEM_WORKSPACE={str(self.workspace)!r}\nexec echo thesystem\n")
        removed = self.run_command("uninstall", "--workspace", str(self.workspace))
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertFalse((self.home / ".local/bin/First").exists())
        self.assertTrue((self.home / ".local/bin/Second").is_file())
        self.assertTrue(lookalike.is_file())
        help_result = subprocess.run([str(self.home / ".local/bin/Second"), "--help"],
                                     env=self.env, text=True, capture_output=True)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)

    def test_rollback_rejects_invalid_snapshot_before_removing_current_files(self):
        installed = self.run_command("install", "--workspace", str(self.workspace), "--runtime", "none")
        self.assertEqual(installed.returncode, 0, installed.stderr)
        upgraded = self.run_command("upgrade", "--workspace", str(self.workspace))
        self.assertEqual(upgraded.returncode, 0, upgraded.stderr)
        current = self.workspace / "thesystem/command.py"
        before = current.read_bytes()
        manifest = self.workspace / ".thesystem/backups/1.managed.json"
        data = json.loads(manifest.read_text())
        data["entries"]["thesystem/command.py"] = ["file", "0" * 64]
        manifest.write_text(json.dumps(data))
        rollback = self.run_command("rollback", "--workspace", str(self.workspace))
        self.assertEqual(rollback.returncode, 1)
        self.assertIn("SNAPSHOT_INVALID", rollback.stderr)
        self.assertEqual(current.read_bytes(), before)

    def test_missing_workspace_binding_is_actionable_instead_of_argparse_usage(self):
        result = self.run_command("upgrade")
        self.assertEqual(result.returncode, 1)
        self.assertIn("WORKSPACE_REQUIRED", result.stderr)

    def test_development_checkout_doctor_does_not_require_installer_manifest(self):
        before = set(self.workspace.rglob("*"))
        output = io.StringIO()
        with patch.object(workflow, "_source_root", return_value=self.workspace), redirect_stdout(output):
            result = workflow.doctor(self.workspace, runtime="none")
        report = json.loads(output.getvalue())
        self.assertEqual(result, 0)
        self.assertTrue(report["ready"])
        self.assertEqual(report["checks"]["distribution"]["status"], "pass")
        self.assertIn("ownership manifest not applicable", report["checks"]["distribution"]["message"])
        self.assertFalse((self.workspace / ".thesystem/managed.json").exists())
        self.assertEqual(set(self.workspace.rglob("*")), before)

    def test_existing_workspace_uses_software_declarations_without_copying_distribution(self):
        settings, toolsets = workflow._configuration_sources(self.workspace)
        self.assertEqual(settings, ROOT / "agents/.harness/canonical_config.tsv")
        self.assertEqual(toolsets, ROOT / "agents/.harness/required_toolsets.txt")
        self.assertFalse((self.workspace / "agents/.harness").exists())
        harness = self.workspace / "agents/.harness"
        harness.mkdir(parents=True)
        (harness / "canonical_config.tsv").write_text("fixture.key\ttrue\n")
        (harness / "required_toolsets.txt").write_text("file\n")
        self.assertEqual(workflow._configuration_sources(self.workspace),
                         (harness / "canonical_config.tsv", harness / "required_toolsets.txt"))

    def test_doctor_infrastructure_mode_reports_readiness_without_writes(self):
        installed = self.run_command("install", "--workspace", str(self.workspace), "--runtime", "none")
        self.assertEqual(installed.returncode, 0, installed.stderr)
        before = {path.relative_to(self.root): (path.stat().st_mtime_ns, path.read_bytes())
                  for path in self.root.rglob("*") if path.is_file()}
        result = self.run_command("doctor", "--workspace", str(self.workspace), "--runtime", "none")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["ready"])
        self.assertEqual(report["checks"]["distribution"]["status"], "pass")
        after = {path.relative_to(self.root): (path.stat().st_mtime_ns, path.read_bytes())
                 for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(after, before)

    def test_profile_scoped_hermes_home_infers_active_profile_and_root(self):
        root = self.root / "custom-hermes"
        active = root / "profiles/reviewer"
        active.mkdir(parents=True)
        with patch.dict(os.environ, HERMES_HOME=str(active)):
            target = _hermes_target()
            other = _hermes_target("implementer")
        self.assertEqual(target.home, root)
        self.assertEqual(target.profile, "reviewer")
        self.assertEqual(target.profile_home, active)
        self.assertEqual(other.home, root)
        self.assertEqual(other.profile_home, root / "profiles/implementer")

    def test_untracked_identical_and_experimental_files_keep_ownership_boundaries(self):
        manual = self.workspace / "MANUAL.md"
        canonical_manual = ROOT / "MANUAL.md"
        manual.write_bytes(canonical_manual.read_bytes())
        regular = self.run_command("install", "--workspace", str(self.workspace), "--runtime", "none")
        self.assertEqual(regular.returncode, 0, regular.stderr)
        experimental_rule = ROOT / "agents/rules/second-order-thinking-checks.md"
        installed_rule = self.workspace / "agents/rules/second-order-thinking-checks.md"
        self.assertTrue(experimental_rule.is_file())
        self.assertFalse(installed_rule.exists())
        removed = self.run_command("uninstall", "--workspace", str(self.workspace))
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertEqual(manual.read_bytes(), canonical_manual.read_bytes())

        opted_in = self.run_command("install", "--workspace", str(self.workspace), "--runtime", "none", "--experimental")
        self.assertEqual(opted_in.returncode, 0, opted_in.stderr)
        self.assertEqual(installed_rule.read_bytes(), experimental_rule.read_bytes())


if __name__ == "__main__":
    unittest.main()
