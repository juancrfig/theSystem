"""Tests for the standalone theSystem/install entry point."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install"


class InstallScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="test-install-script-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.env = dict(
            os.environ,
            HOME=str(self.home),
            PATH=f"{self.home / '.local/bin'}:{os.environ.get('PATH', '')}",
            PYTHONDONTWRITEBYTECODE="1",
        )
        self.env.pop("HERMES_HOME", None)
        self.env.pop("THESYSTEM_WORKSPACE", None)

    def run_installer(self, *args, input_text=None):
        return subprocess.run(
            [str(INSTALLER), *args],
            input=input_text,
            cwd=self.root,
            env=self.env,
            text=True,
            capture_output=True,
        )

    def test_help_is_read_only_and_exits_zero(self):
        before = set(self.root.rglob("*"))
        result = self.run_installer("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage: install", result.stdout)
        self.assertEqual(set(self.root.rglob("*")), before)

    def test_default_invocation_succeeds_without_arguments(self):
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)

        workspace_dir = self.home / "workspace"
        self.assertTrue(workspace_dir.is_dir())
        workspace_cmd = self.home / ".local/bin/workspace"
        self.assertTrue(workspace_cmd.is_file())
        self.assertTrue((workspace_dir / "GLOSSARY.md").is_file())
        self.assertFalse((workspace_dir / "thesystem").exists())
        self.assertFalse((workspace_dir / "the_system_orchestrator.py").exists())

    def test_prompts_company_name_and_creates_lowercase_folder_at_home(self):
        result = self.run_installer("--interactive", input_text="acme\n")
        self.assertEqual(result.returncode, 0, result.stderr)

        acme_dir = self.home / "acme"
        self.assertTrue(acme_dir.is_dir())
        acme_cmd = self.home / ".local/bin/acme"
        self.assertTrue(acme_cmd.is_file())
        self.assertTrue((acme_dir / "GLOSSARY.md").is_file())
        self.assertFalse((acme_dir / "thesystem").exists())
        self.assertFalse((acme_dir / "the_system_orchestrator.py").exists())

    def test_prompts_mixed_case_company_creates_lowercase_folder(self):
        result = self.run_installer("--interactive", input_text="AcmeCorp\n")
        self.assertEqual(result.returncode, 0, result.stderr)

        acme_dir = self.home / "acmecorp"
        self.assertTrue(acme_dir.is_dir())
        acme_cmd = self.home / ".local/bin/acmecorp"
        self.assertTrue(acme_cmd.is_file())

    def test_infrastructure_install_proves_prerequisite_alias_and_context_seeding(self):
        # Workspace initially has no GLOSSARY.md
        self.assertFalse((self.workspace / "GLOSSARY.md").exists())

        result = self.run_installer(str(self.workspace), "--runtime", "none", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)

        # 1. Global command prerequisite verified
        global_cli = self.home / ".local/bin/thesystem"
        global_share = self.home / ".local/share/thesystem"
        self.assertTrue(global_cli.is_file())
        self.assertTrue(os.access(global_cli, os.X_OK))
        self.assertTrue((global_share / "thesystem").is_dir())

        # 2. Company alias auto-derived from folder name ("workspace")
        company_alias = self.home / ".local/bin/workspace"
        self.assertTrue(company_alias.is_file())
        self.assertTrue(os.access(company_alias, os.X_OK))
        alias_content = company_alias.read_text()
        self.assertIn(f"THESYSTEM_WORKSPACE={str(self.workspace)!r}", alias_content)

        # 3. Context seeding per ADR 0002: GLOSSARY.md was missing, so it was seeded
        glossary = self.workspace / "GLOSSARY.md"
        self.assertTrue(glossary.is_file())
        self.assertEqual(glossary.read_text(), (ROOT / "GLOSSARY.md").read_text())

        # 4. System implementation files are NOT dumped into the workspace
        self.assertFalse((self.workspace / "thesystem").exists())
        self.assertFalse((self.workspace / "bin").exists())
        self.assertFalse((self.workspace / "the_system_orchestrator.py").exists())

        # 5. Doctor readiness report in JSON output is valid
        report = json.loads(result.stdout)
        self.assertTrue(report.get("ready"))

    def test_custom_company_and_preservation_of_existing_files_per_adr_0002(self):
        custom_agents = "Custom Company Agent Guidance\n"
        custom_glossary = "Custom Company Glossary\n"
        (self.workspace / "AGENTS.md").write_text(custom_agents)
        (self.workspace / "GLOSSARY.md").write_text(custom_glossary)

        result = self.run_installer(str(self.workspace), "AcmeCorp", "--runtime", "none")
        self.assertEqual(result.returncode, 0, result.stderr)

        # Existing files strictly preserved
        self.assertEqual((self.workspace / "AGENTS.md").read_text(), custom_agents)
        self.assertEqual((self.workspace / "GLOSSARY.md").read_text(), custom_glossary)

        # Custom company alias created
        alias = self.home / ".local/bin/AcmeCorp"
        self.assertTrue(alias.is_file())
        self.assertIn("AcmeCorp", result.stdout)

    def test_idempotent_reinstallation(self):
        first = self.run_installer(str(self.workspace), "Acme", "--runtime", "none")
        self.assertEqual(first.returncode, 0, first.stderr)

        second = self.run_installer(str(self.workspace), "Acme", "--runtime", "none")
        self.assertEqual(second.returncode, 0, second.stderr)


if __name__ == "__main__":
    unittest.main()
