"""F1 · Install theSystem."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.env = {"HOME": str(self.home), "PATH": f"{self.home}/.local/bin:/usr/bin:/bin"}

    def install(self, **answers):
        env = {**self.env, **answers}
        return subprocess.run(["bash", str(REPO / "install")], env=env, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, start_new_session=True)  # no /dev/tty: defaults apply

    def test_defaults_create_workspace_command_git_and_skills_link(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        workspace = self.home / "workspace"
        for path in ("AGENTS.md", "GLOSSARY.md", "docs", "agents/rules", "agents/skills", "agents/tools",
                     "agents/roles.yaml", ".git"):
            self.assertTrue((workspace / path).exists(), path)
        link = workspace / ".agents" / "skills"
        self.assertEqual(os.readlink(link), "../agents/skills")
        self.assertTrue((link / "to-tasks" / "SKILL.md").is_file())
        agents_md = (workspace / "AGENTS.md").read_text()
        self.assertIn("umbrella run", agents_md)
        self.assertNotIn("{{COMMAND}}", agents_md)

        command = subprocess.run(["umbrella"], env=self.env, capture_output=True, text=True)
        self.assertEqual(command.returncode, 0, command.stderr)
        self.assertIn("run", command.stdout)

    def test_answers_choose_location_and_command_name(self):
        result = self.install(THESYSTEM_WORKSPACE=str(self.home / "acme-ws"), THESYSTEM_COMPANY="acme")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.home / "acme-ws" / "AGENTS.md").is_file())
        self.assertTrue((self.home / ".local" / "bin" / "acme").is_file())

    def test_existing_files_and_repo_are_kept(self):
        workspace = self.home / "workspace"
        workspace.mkdir()
        subprocess.run(["git", "init", "-q", str(workspace)], check=True)
        (workspace / "AGENTS.md").write_text("mine\n")
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((workspace / "AGENTS.md").read_text(), "mine\n")
        self.assertTrue((workspace / "GLOSSARY.md").is_file())

    def test_reinstall_keeps_workspace_changes(self):
        self.assertEqual(self.install().returncode, 0)
        roles = self.home / "workspace" / "agents" / "roles.yaml"
        roles.write_text("worker: {}\n")
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(roles.read_text(), "worker: {}\n")


if __name__ == "__main__":
    unittest.main()
