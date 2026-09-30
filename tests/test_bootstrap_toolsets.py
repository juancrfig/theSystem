"""Offline checks for additively enabling required Hermes toolsets."""

import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RequiredToolsetsBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="install-toolsets-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "calls.json"
        self.hermes_home = self.root / "hermes-home"
        self.manifest = self.root / "required_toolsets.txt"
        self.manifest.write_text("file\nweb\n")

        hermes = self.bin / "hermes"
        hermes.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys\n"
            "pathlib.Path(os.environ['CALL_LOG']).write_text(json.dumps(sys.argv[1:]))\n"
        )
        hermes.chmod(0o755)

        source_file = self.root / "bootstrap-functions"
        source_file.write_text((ROOT / "bootstrap").read_text().split("\nsteps=(", 1)[0])
        self.script = (
            f"source {shlex.quote(str(source_file))}\n"
            f"provisioning_cli={shlex.quote(str(ROOT / 'thesystem/setup/provisioning_cli.py'))}\n"
            f"required_toolsets={shlex.quote(str(self.manifest))}\n"
            f"default_hermes_home={shlex.quote(str(self.hermes_home))}\n"
            "enable_required_toolsets\nprintf 'READY\\n'\n"
        )
        self.env = {
            "HOME": str(self.root),
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "CALL_LOG": str(self.log),
        }

    def run_install_function(self):
        return subprocess.run(
            ["bash"], input=self.script, text=True, capture_output=True, env=self.env
        )

    def test_enables_manifest_toolsets_on_cli_without_disable_command(self):
        result = self.run_install_function()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("READY", result.stdout)
        self.assertEqual(
            json.loads(self.log.read_text()),
            ["tools", "enable", "--platform", "cli", "file", "web"],
        )

    def test_manifest_changes_are_consumed_without_install_edits(self):
        self.manifest.write_text("browser\ncode_execution\n")
        result = self.run_install_function()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(self.log.read_text()),
            ["tools", "enable", "--platform", "cli", "browser", "code_execution"],
        )

    def test_duplicate_entries_fail_before_changing_hermes(self):
        self.manifest.write_text("file\nfile\n")
        result = self.run_install_function()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Duplicate toolset name", result.stderr)
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
