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

    def fake_hermes(self, personality=""):
        """A `hermes` stub on PATH that logs `config set` calls and answers `config get`."""
        bin_dir = self.home / "fakebin"
        bin_dir.mkdir(exist_ok=True)
        log = self.home / "hermes.log"
        stub = bin_dir / "hermes"
        stub.write_text("#!/bin/sh\n"
                        f"if [ \"$2\" = get ]; then printf '%s\\n' '{personality}'; exit 0; fi\n"
                        f"printf '%s\\0' \"$3\" \"$4\" >> '{log}'\n")
        stub.chmod(0o755)
        self.env["PATH"] = f"{bin_dir}:{self.env['PATH']}"
        return log

    def config_sets(self, log):
        fields = log.read_text().split("\0")[:-1] if log.exists() else []
        return dict(zip(fields[::2], fields[1::2]))

    def test_hermes_gets_main_and_casual_personalities_with_main_selected(self):
        log = self.fake_hermes()
        self.assertEqual(self.install().returncode, 0)
        sets = self.config_sets(log)
        rule = (self.home / "workspace/agents/.harness/personalities/main.md").read_text().strip()
        self.assertTrue(rule.startswith("# Communication style"))
        self.assertEqual(sets["personalities.main"], rule)
        self.assertEqual(sets["personalities.casual"], "")
        self.assertEqual(sets["display.personality"], "main")

    def test_reinstall_keeps_the_selected_personality(self):
        log = self.fake_hermes(personality="casual")
        self.assertEqual(self.install().returncode, 0)
        sets = self.config_sets(log)
        self.assertIn("personalities.main", sets)
        self.assertNotIn("display.personality", sets)

    def test_without_hermes_personalities_are_skipped(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.home / ".hermes").exists())

    def test_artifact_library_service_is_installed_and_started(self):
        bin_dir = self.home / "fakebin"
        bin_dir.mkdir()
        log = self.home / "systemctl.log"
        for name in ("systemctl", "loginctl"):
            stub = bin_dir / name
            stub.write_text(f"#!/bin/sh\necho {name} \"$@\" >> '{log}'\n")
            stub.chmod(0o755)
        self.env["PATH"] = f"{bin_dir}:{self.env['PATH']}"
        self.assertEqual(self.install().returncode, 0)
        unit = (self.home / ".config/systemd/user/thesystem-artifacts.service").read_text()
        self.assertIn(f"THESYSTEM_WORKSPACE={(self.home / 'workspace').resolve()}", unit)
        self.assertIn("python3 -m thesystem.artifacts", unit)
        calls = log.read_text()
        self.assertIn("systemctl --user enable thesystem-artifacts.service", calls)
        self.assertIn("systemctl --user restart thesystem-artifacts.service", calls)
        self.assertIn("loginctl enable-linger", calls)

    def test_reinstall_keeps_workspace_changes(self):
        self.assertEqual(self.install().returncode, 0)
        roles = self.home / "workspace" / "agents" / "roles.yaml"
        roles.write_text("worker: {}\n")
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(roles.read_text(), "worker: {}\n")


if __name__ == "__main__":
    unittest.main()
