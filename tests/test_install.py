"""F1 · Install theSystem."""
import json
import os
import pty
import select
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from thesystem import harness  # noqa: E402

# The installer runs the python3 on the PATH the tests give it, which may differ from the one running the tests.
INSTALLER_PATH = "/usr/bin:/bin"
INSTALLER_HAS_YAML = subprocess.run(["python3", "-c", "import yaml"], env={"PATH": INSTALLER_PATH},
                                    capture_output=True).returncode == 0


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.env = {"HOME": str(self.home), "PATH": f"{self.home}/.local/bin:{INSTALLER_PATH}"}

    def install(self, **answers):
        env = {**self.env, **answers}
        return subprocess.run(["bash", str(REPO / "install"), "--dev"], env=env, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, start_new_session=True)  # no /dev/tty: defaults apply

    def test_defaults_create_workspace_command_git_and_skills_link(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        workspace = self.home / "workspace"
        for path in ("AGENTS.md", "GLOSSARY.md", "docs", "agents/rules", "agents/skills",
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

    def test_hermes_agent_skill_is_not_shipped_so_the_bundled_one_stays_current(self):
        # A workspace copy would shadow the hermes-agent skill that Hermes bundles and updates.
        names = {line.split(":", 1)[1].strip().strip('"')
                 for skill in (REPO / "agents" / "skills").rglob("SKILL.md")
                 for line in skill.read_text().splitlines() if line.startswith("name:")}
        self.assertNotIn("hermes-agent", names)

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

    def fake_hermes(self, personality="", profiles=(), delay=0.0):
        """A `hermes` stub on PATH that logs every call, answers `config get`, and keeps profiles in folders as
        Hermes does: *profiles* exist already, `profile create` adds one."""
        bin_dir = self.home / "fakebin"
        bin_dir.mkdir(exist_ok=True)
        log = self.home / "hermes.log"
        profiles_dir = self.home / ".hermes/profiles"
        for profile in profiles:
            (profiles_dir / profile).mkdir(parents=True, exist_ok=True)
        stub = bin_dir / "hermes"
        stub.write_text("#!/usr/bin/env python3\nimport json, os, sys, time\na = sys.argv[1:]\n"
                        f"time.sleep({delay})\n"
                        f"open({str(log)!r}, 'a').write(json.dumps(a) + '\\n')\n"
                        f"if a[:2] == ['config', 'get']: print({personality!r})\n"
                        f"if a[:2] == ['profile', 'create']: os.makedirs(os.path.join({str(profiles_dir)!r}, a[2]))\n")
        stub.chmod(0o755)
        self.env["PATH"] = f"{bin_dir}:{self.env['PATH']}"
        return log

    def calls(self, log):
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def config_sets(self, log):
        return {c[2]: c[3] for c in self.calls(log) if c[:2] == ["config", "set"]}

    def hermes_config(self):
        """The main agent's config, read with the installer's python3 (the one that wrote it)."""
        read = subprocess.run(["python3", "-c", "import json, sys, yaml; print(json.dumps(yaml.safe_load(open(sys.argv[1]))))",
                               str(self.home / ".hermes/config.yaml")], env={"PATH": INSTALLER_PATH},
                              capture_output=True, text=True, check=True)
        return json.loads(read.stdout)

    @unittest.skipUnless(INSTALLER_HAS_YAML, "PyYAML edits Hermes' config; without it `hermes config set` does (tested below)")
    def test_main_agent_gets_the_whole_canonical_config_and_toolsets(self):
        log = self.fake_hermes()
        self.assertEqual(self.install().returncode, 0)
        sets = dict(harness.leaves(self.hermes_config()))
        lines = list(harness.leaves(harness.load(
            (REPO / "agents/.harness/canonical_config.yaml").read_text())))
        self.assertEqual(len(lines), 46)
        for key, expected in lines:
            self.assertEqual(sets[key], expected, key)
        self.assertEqual(sets["approvals.mode"], "off")
        self.assertNotIn("auxiliary", " ".join(sets), "auxiliary models are left to the human")
        self.assertEqual(self.config_sets(log), {}, "one pass over the config, not a Hermes start per setting")
        enables = [c for c in self.calls(log) if c[:2] == ["tools", "enable"]]
        self.assertEqual({c[3] for c in enables}, {"cli", "telegram"})
        self.assertIn("delegation", enables[0])
        self.assertIn("computer_use", enables[0])

    @unittest.skipUnless(INSTALLER_HAS_YAML, "needs PyYAML to read the config")
    def test_only_memory_changes_need_the_humans_approval(self):
        # F5: memory loads into every turn, so the human approves it; skills apply directly and the curator
        # maintains the agent-created ones.
        self.fake_hermes()
        self.assertEqual(self.install().returncode, 0)
        sets = dict(harness.leaves(self.hermes_config()))
        self.assertIs(sets["memory.write_approval"], True)
        self.assertIs(sets["skills.write_approval"], False)
        self.assertIs(sets["curator.enabled"], True)

    @unittest.skipUnless(INSTALLER_HAS_YAML, "needs PyYAML to read the config")
    def test_existing_hermes_config_is_kept_and_stays_valid(self):
        # Real configs hold lists of mappings, multi-line text and comments; reinstalling must not break them.
        self.fake_hermes()
        root = self.home / ".hermes"
        root.mkdir()
        config = root / "config.yaml"
        config.write_text("# mine\nmodel:\n  default: claude\n  provider: anthropic\nfallback_providers:\n"
                          "  - provider: openrouter\n    model: other\nsoul: |\n  line one\n  line two\n"
                          "approvals:\n  mode: manual\n")
        config.chmod(0o600)
        for _ in range(2):
            result = self.install()
            self.assertEqual(result.returncode, 0, result.stderr)
        cfg = self.hermes_config()
        self.assertEqual(cfg["model"], {"default": "claude", "provider": "anthropic"})
        self.assertEqual(cfg["fallback_providers"], [{"provider": "openrouter", "model": "other"}])
        self.assertEqual(cfg["soul"], "line one\nline two\n")
        self.assertEqual(cfg["approvals"]["mode"], "off")
        self.assertTrue(cfg["personalities"]["main"].startswith("# Communication style"))
        self.assertEqual(config.stat().st_mode & 0o777, 0o600)

    def test_unreadable_hermes_config_is_left_unchanged_and_reported(self):
        self.fake_hermes()
        root = self.home / ".hermes"
        root.mkdir()
        (root / "config.yaml").write_text("model: [unclosed\n")
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((root / "config.yaml").read_text(), "model: [unclosed\n")
        if INSTALLER_HAS_YAML:
            self.assertIn("left unchanged", result.stderr)

    def test_without_pyyaml_each_setting_goes_through_hermes_config_set(self):
        log = self.fake_hermes(personality="casual")
        with mock.patch.object(harness, "_yaml", return_value=None), \
                mock.patch.dict(os.environ, {"PATH": self.env["PATH"]}):
            harness.apply(self.home / ".hermes", [("approvals.mode", "off"), ("goals.max_turns", 90),
                                                  ("personalities.casual", "")],
                          [("display.personality", "main")], [self.home])
        self.assertEqual(self.config_sets(log),
                         {"approvals.mode": "off", "goals.max_turns": "90", "personalities.casual": ""})
        self.assertIn(["config", "get", "display.personality"], self.calls(log))
        self.assertIn(["skills", "trust", str(self.home)], self.calls(log))

    @unittest.skipUnless(INSTALLER_HAS_YAML, "needs PyYAML to read the config")
    def test_workspace_is_trusted_so_hermes_loads_its_skills(self):
        self.fake_hermes()
        (self.home / ".hermes").mkdir()
        (self.home / ".hermes/config.yaml").write_text("skills:\n  trusted_project_dirs:\n  - /srv/other\n")
        workspace = str((self.home / "workspace").resolve())
        for _ in range(2):  # trusted once, however often it's installed
            self.assertEqual(self.install().returncode, 0)
        self.assertEqual(self.hermes_config()["skills"]["trusted_project_dirs"], ["/srv/other", workspace])

    @unittest.skipUnless(INSTALLER_HAS_YAML, "needs PyYAML to read the config")
    def test_messaging_sessions_start_in_the_workspace(self):
        self.fake_hermes()
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(self.hermes_config()["terminal"]["cwd"], str((self.home / "workspace").resolve()))

    def test_worker_and_reviewer_profiles_are_created_empty_once(self):
        log = self.fake_hermes(profiles=("reviewer",))
        for _ in range(2):
            self.assertEqual(self.install().returncode, 0)
        creates = [c for c in self.calls(log) if c[:2] == ["profile", "create"]]
        self.assertEqual(creates, [["profile", "create", "worker", "--no-alias", "--no-skills"]])
        self.assertEqual([c for c in self.calls(log) if c[0] == "profile" and c[1] != "create"], [],
                         "an existing profile costs no Hermes start")

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

    @unittest.skipUnless(INSTALLER_HAS_YAML, "needs PyYAML to read the config")
    def test_hermes_gets_main_and_casual_personalities_with_main_selected(self):
        self.fake_hermes()
        self.assertEqual(self.install().returncode, 0)
        cfg = self.hermes_config()
        rule = (self.home / "workspace/agents/.harness/personalities/main.md").read_text().strip()
        self.assertTrue(rule.startswith("# Communication style"))
        self.assertEqual(cfg["personalities"]["main"], rule)
        self.assertEqual(cfg["personalities"]["casual"], "")
        self.assertEqual(cfg["display"]["personality"], "main")

    @unittest.skipUnless(INSTALLER_HAS_YAML, "needs PyYAML to read the config")
    def test_reinstall_keeps_the_selected_personality(self):
        self.fake_hermes()
        (self.home / ".hermes").mkdir()
        (self.home / ".hermes/config.yaml").write_text("display:\n  personality: casual\n")
        self.assertEqual(self.install().returncode, 0)
        cfg = self.hermes_config()
        self.assertIn("main", cfg["personalities"])
        self.assertEqual(cfg["display"]["personality"], "casual")

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

    def test_install_reports_each_step(self):
        self.fake_hermes()
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        for line in ("+ Setting up the workspace", "+ Configuring Hermes",
                     "+ Preparing the worker and reviewer profiles", "+ Adding the umbrella command"):
            self.assertIn(line, result.stdout)
        self.assertIn("Done in ", result.stdout)
        self.assertNotIn("\r", result.stdout, "no spinner without a terminal")

    def test_a_terminal_sees_a_spinner_while_a_step_runs(self):
        self.fake_hermes(delay=0.4)  # slow enough for the spinner to draw
        main, child = pty.openpty()
        process = subprocess.Popen(["bash", str(REPO / "install"), "--dev"], stdin=subprocess.DEVNULL, stdout=child,
                                   stderr=child, env={**self.env, "LANG": "C.UTF-8"}, start_new_session=True)
        os.close(child)
        output = b""
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if select.select([main], [], [], 0.5)[0]:
                try:
                    chunk = os.read(main, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                output += chunk
            elif process.poll() is not None:
                break
        os.close(main)
        self.assertEqual(process.wait(), 0, output)
        text = output.decode()
        self.assertIn("\r  ⠋ Configuring Hermes", text)
        self.assertIn("✓ Configuring Hermes", text)
        self.assertIn("Done in ", text)
        self.assertNotIn("Terminated", text, "stopping the spinner prints nothing")
        self.assertEqual(text.count("\x1b[?25l"), text.count("\x1b[?25h"), "the cursor is shown again")


if __name__ == "__main__":
    unittest.main()
