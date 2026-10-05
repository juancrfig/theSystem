"""F1 · Install theSystem."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from thesystem import harness  # noqa: E402


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

    def fake_hermes(self, personality="", profiles=()):
        """A `hermes` stub on PATH that logs every call, answers `config get` and knows *profiles*."""
        bin_dir = self.home / "fakebin"
        bin_dir.mkdir(exist_ok=True)
        log = self.home / "hermes.log"
        stub = bin_dir / "hermes"
        stub.write_text("#!/usr/bin/env python3\nimport json, sys\na = sys.argv[1:]\n"
                        f"open({str(log)!r}, 'a').write(json.dumps(a) + '\\n')\n"
                        f"if a[:2] == ['config', 'get']: print({personality!r})\n"
                        f"if a[:2] == ['profile', 'show'] and a[2] not in {list(profiles)!r}: sys.exit(1)\n")
        stub.chmod(0o755)
        self.env["PATH"] = f"{bin_dir}:{self.env['PATH']}"
        return log

    def calls(self, log):
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def config_sets(self, log):
        return {c[2]: c[3] for c in self.calls(log) if c[:2] == ["config", "set"]}

    def test_main_agent_gets_the_whole_canonical_config_and_toolsets(self):
        log = self.fake_hermes()
        self.assertEqual(self.install().returncode, 0)
        sets = self.config_sets(log)
        lines = list(harness.settings(harness.load(
            (REPO / "agents/.harness/canonical_config.yaml").read_text())))
        self.assertEqual(len(lines), 46)
        for key, expected in lines:
            self.assertEqual(sets[key], expected, key)
        self.assertEqual(sets["approvals.mode"], "off")
        self.assertNotIn("auxiliary", " ".join(sets), "auxiliary models are left to the human")
        enables = [c for c in self.calls(log) if c[:2] == ["tools", "enable"]]
        self.assertEqual({c[3] for c in enables}, {"cli", "telegram"})
        self.assertIn("delegation", enables[0])
        self.assertIn("computer_use", enables[0])

    def test_worker_and_reviewer_profiles_are_created_empty_once(self):
        log = self.fake_hermes(profiles=("reviewer",))
        self.assertEqual(self.install().returncode, 0)
        creates = [c for c in self.calls(log) if c[:2] == ["profile", "create"]]
        self.assertEqual(creates, [["profile", "create", "worker", "--no-alias", "--no-skills"]])

    def test_worker_and_reviewer_inherit_main_credentials_without_bot_tokens(self):
        self.fake_hermes()
        root = self.home / ".hermes"
        root.mkdir()
        (root / "auth.json").write_text('{"providers": {}}')
        (root / ".env").write_text("ANTHROPIC_API_KEY=sk-test\nTELEGRAM_BOT_TOKEN=bot\nTELEGRAM_ALLOWED_USERS=1\n"
                                   "GATEWAY_ALLOWED_USERS=1\nEXA_API_KEY=exa\n")
        for profile in ("worker", "reviewer"):
            (root / "profiles" / profile).mkdir(parents=True)
        (root / "profiles/worker/auth.json").write_text("{}")  # a stale copy gets replaced by the shared store
        self.env.pop("HERMES_HOME", None)
        for _ in range(2):  # reinstalling keeps it the same
            self.assertEqual(self.install().returncode, 0)
        for profile in ("worker", "reviewer"):
            directory = root / "profiles" / profile
            self.assertTrue((directory / "auth.json").is_symlink())
            self.assertTrue((directory / "auth.json").samefile(root / "auth.json"))
            keys = (directory / ".env").read_text()
            self.assertIn("ANTHROPIC_API_KEY=sk-test", keys)
            self.assertIn("EXA_API_KEY=exa", keys)
            self.assertNotIn("TELEGRAM", keys)
            self.assertNotIn("GATEWAY_", keys)
            self.assertEqual((directory / ".env").stat().st_mode & 0o777, 0o600)

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
