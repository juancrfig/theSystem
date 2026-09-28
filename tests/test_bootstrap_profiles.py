"""Offline checks for canonical profile reconciliation during bootstrap."""

import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BootstrapProfileReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="bootstrap-profiles-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "calls.jsonl"

        self.canonical_config = self.root / "canonical_config.tsv"
        self.canonical_config.write_text(
            "compression.enabled\ttrue\n"
            "approvals.mode\t\"off\"\n"
        )
        self.canonical_profiles = self.root / "canonical_profiles.txt"
        self.canonical_profiles.write_text("default\nimplementer\nreviewer\n")

        hermes = self.bin / "hermes"
        hermes.write_text("""#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
log = pathlib.Path(os.environ["CALL_LOG"])
with log.open("a") as f:
    f.write(json.dumps(args) + "\\n")
if args == ["profile", "list"]:
    print(os.environ.get("PROFILE_LIST", "default"))
elif args[:2] == ["profile", "create"]:
    pass
elif len(args) >= 7 and args[0] == "-p" and args[2:5] == ["config", "set", "--force"]:
    pass
else:
    raise SystemExit(7)
""")
        hermes.chmod(0o755)

        source_file = self.root / "bootstrap-functions"
        source_file.write_text((ROOT / "bootstrap").read_text().split("\nsteps=(", 1)[0])
        self.script = (
            f"source {shlex.quote(str(source_file))}\n"
            f"canonical_config={shlex.quote(str(self.canonical_config))}\n"
            f"canonical_profiles={shlex.quote(str(self.canonical_profiles))}\n"
            "apply_canonical_config\nprintf 'READY %s\\n' \"$step_detail\"\n"
        )
        self.env = {
            "HOME": str(self.root),
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "CALL_LOG": str(self.log),
            "PROFILE_LIST": "default",
        }

    def run_apply(self, **env):
        return subprocess.run(
            ["bash"], input=self.script, text=True, capture_output=True, env=dict(self.env, **env)
        )

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_applies_every_canonical_setting_to_every_declared_profile(self):
        result = self.run_apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("READY 2 settings x 3 profiles", result.stdout)
        calls = self.calls()
        creates = [call for call in calls if call[:2] == ["profile", "create"]]
        self.assertEqual(creates, [["profile", "create", "implementer", "--no-skills"],
                                   ["profile", "create", "reviewer", "--no-skills"]])
        sets = [call for call in calls if call[:2] == ["-p", "default"] or call[:2] == ["-p", "implementer"] or call[:2] == ["-p", "reviewer"]]
        self.assertEqual(len(sets), 6)
        expected_pairs = {
            ("default", "compression.enabled", "true"),
            ("default", "approvals.mode", '"off"'),
            ("implementer", "compression.enabled", "true"),
            ("implementer", "approvals.mode", '"off"'),
            ("reviewer", "compression.enabled", "true"),
            ("reviewer", "approvals.mode", '"off"'),
        }
        actual_pairs = {(call[1], call[5], call[6]) for call in sets}
        self.assertEqual(actual_pairs, expected_pairs)

    def test_new_declared_profile_is_reconciled_without_code_changes(self):
        self.canonical_profiles.write_text("default\nimplementer\nreviewer\nauditor\n")
        result = self.run_apply(PROFILE_LIST="default\nimplementer\nreviewer")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("READY 2 settings x 4 profiles", result.stdout)
        creates = [call for call in self.calls() if call[:2] == ["profile", "create"]]
        self.assertEqual(creates, [["profile", "create", "auditor", "--no-skills"]])
        auditor_sets = [call for call in self.calls() if call[:2] == ["-p", "auditor"]]
        self.assertEqual(len(auditor_sets), 2)

    def test_invalid_profile_declaration_fails_fast(self):
        self.canonical_profiles.write_text("default\nreviewer-role\n")
        result = self.run_apply()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid profile name", result.stderr)


if __name__ == "__main__":
    unittest.main()
