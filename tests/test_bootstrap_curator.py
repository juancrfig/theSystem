"""Offline checks for bootstrapping curator protection of global skills."""

import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CuratorBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="bootstrap-curator-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "hermes home"
        self.home.mkdir()
        self.checkout = self.root / "checkout"
        self.checkout.mkdir()
        shutil.copytree(ROOT / "thesystem", self.checkout / "thesystem",
                        ignore=shutil.ignore_patterns("__pycache__"))
        self.skills = self.checkout / "agents" / "skills"
        self.skills.mkdir(parents=True)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.mock_hermes = self.bin / "hermes"
        self.mock_hermes.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
home = pathlib.Path(os.environ["HERMES_HOME"])
entries = json.loads((home / "usage.json").read_text())
args = sys.argv[1:]
with (home / "calls").open("a") as log:
    log.write(json.dumps(args) + "\\n")
if args == ["curator", "usage", "--json"]:
    if os.environ.get("FAIL_USAGE"):
        sys.exit(9)
    print(json.dumps(entries))
elif args[:2] == ["curator", "pin"]:
    name = args[2]
    if os.environ.get("FAIL_PIN") == name:
        sys.exit(8)
    sidecar = home / "skills" / ".usage.json"
    recorded = json.loads(sidecar.read_text())
    recorded.setdefault(name, {})["pinned"] = True
    sidecar.write_text(json.dumps(recorded))
    for entry in entries:
        if entry["name"] == name:
            entry["pinned"] = True
            break
    (home / "usage.json").write_text(json.dumps(entries))
else:
    sys.exit(6)
''')
        self.mock_hermes.chmod(0o755)
        self.source_file = self.checkout / "bootstrap-functions"
        self.source_file.write_text((ROOT / "bootstrap").read_text().split("\nsteps=(", 1)[0])
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}")

    def seed(self, entries):
        (self.home / "usage.json").write_text(json.dumps(entries))
        sidecar = self.home / "skills" / ".usage.json"
        sidecar.parent.mkdir(exist_ok=True)
        sidecar.write_text(json.dumps({entry["name"]: {"pinned": entry["pinned"]}
                                       for entry in entries}))

    def add_skill(self, name):
        manifest = self.skills / "category" / name / "SKILL.md"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(f"---\nname: {name}\n---\n")

    def run_pin(self, **env):
        script = (f"source {shlex.quote(str(self.source_file))}\n"
                  f"default_hermes_home={shlex.quote(str(self.home))}\n"
                  f"repo_root={shlex.quote(str(self.checkout))}\n"
                  "pin_global_skills\nprintf 'READY %s\\n' \"$step_detail\"\n")
        return subprocess.run(["bash"], input=script, text=True,
                              capture_output=True, env=dict(self.env, **env))

    def calls(self):
        return [json.loads(line) for line in (self.home / "calls").read_text().splitlines()]

    def test_every_repository_global_skill_is_pinned_or_hermes_protected(self):
        for name in ("one", "already", "bundled", "hub", "project-only"):
            self.add_skill(name)
        entries = [
            {"name": "one", "provenance": "agent", "pinned": False},
            {"name": "already", "provenance": "agent", "pinned": True},
            {"name": "bundled", "provenance": "bundled", "pinned": False},
            {"name": "hub", "provenance": "hub", "pinned": False},
            {"name": "unrelated", "provenance": "agent", "pinned": False},
        ]
        self.seed(entries)
        self.assertIn("READY 2 newly pinned", self.run_pin().stdout)
        self.add_skill("new-skill")
        self.assertIn("READY 1 newly pinned", self.run_pin().stdout)
        self.assertIn("READY 0 newly pinned", self.run_pin().stdout)
        pins = [call for call in self.calls() if call[:2] == ["curator", "pin"]]
        self.assertEqual(pins, [["curator", "pin", "one"],
                                ["curator", "pin", "project-only"],
                                ["curator", "pin", "new-skill"]])
        final = json.loads((self.home / "skills" / ".usage.json").read_text())
        self.assertTrue(all(final[name]["pinned"] for name in ("one", "already", "project-only", "new-skill")))
        self.assertFalse(final["unrelated"]["pinned"])

    def test_failed_usage_or_pin_stops_bootstrap(self):
        self.add_skill("one")
        self.seed([{"name": "one", "provenance": "agent", "pinned": False}])
        result = self.run_pin(FAIL_USAGE="1")
        self.assertEqual(result.returncode, 9)
        self.assertNotIn("READY", result.stdout)
        result = self.run_pin(FAIL_PIN="one")
        self.assertEqual(result.returncode, 8)
        self.assertNotIn("READY", result.stdout)


if __name__ == "__main__":
    unittest.main()
