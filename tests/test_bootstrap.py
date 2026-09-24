"""Offline regression checks for bootstrap's isolated review provisioning."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MemoryReviewBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="bootstrap-review-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "checkout with spaces"
        self.root.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "calls"
        self.requirements = self.root / "requirements.txt"
        self.requirements.write_text("typesafe-sdk==0.7.1\n")
        self.env_dir = self.root / "review env"
        self.mock_command("uv", '''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ["CALL_LOG"], "a") as log:
    log.write(json.dumps(args) + "\\n")
if os.environ.get("FAIL_AT") == " ".join(args[:2]):
    sys.exit(9)
if args[0] == "venv":
    target = pathlib.Path(args[-1]) / "bin" / "python"
    target.parent.mkdir(parents=True)
    target.write_text("#!/bin/sh\\nexit ${IMPORT_EXIT:-0}\\n")
    target.chmod(0o755)
if args[:2] == ["pip", "install"]:
    with open(os.environ["CALL_LOG"], "a") as log:
        log.write(pathlib.Path(args[-1]).read_text())
''')
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}",
                        CALL_LOG=str(self.log))
        self.source_file = self.root / "bootstrap-functions"
        self.source_file.write_text((ROOT / "bootstrap").read_text().split("\nsteps=(", 1)[0])
        self.source = f"source {shlex.quote(str(self.source_file))}\n"
        self.setup = (
            '\nresolve_hermes_python() { command -v python3; }\n'
            f"\nmemory_review_env={shlex.quote(str(self.env_dir))}\n"
            f"memory_review_requirements={shlex.quote(str(self.requirements))}\n"
        )

    def mock_command(self, name, content):
        path = self.bin / name
        path.write_text(content)
        path.chmod(0o755)

    def run_provision(self, **env):
        return subprocess.run(["bash"], input=self.source + self.setup +
                              "provision_memory_review\nprintf 'READY\\n'\n",
                              text=True, capture_output=True, env=dict(self.env, **env))

    def test_fresh_install_and_repeated_run_use_same_environment(self):
        self.assertEqual(self.run_provision().returncode, 0)
        self.assertEqual(self.run_provision().returncode, 0)
        log = self.log.read_text()
        self.assertEqual(log.count('["venv"'), 1)
        self.assertEqual(log.count('["pip", "install"'), 2)
        self.assertEqual(log.count('["pip", "check"'), 2)
        self.assertIn(str(self.env_dir / "bin/python"), log)

    def test_changed_manifest_is_consumed_without_bootstrap_edits(self):
        self.assertEqual(self.run_provision().returncode, 0)
        self.requirements.write_text("typesafe-sdk==0.7.1\nfixture-dependency==1.2.3\n")
        self.assertEqual(self.run_provision().returncode, 0)
        self.assertIn("fixture-dependency==1.2.3", self.log.read_text())

    def test_install_failure_stops_bootstrap(self):
        result = self.run_provision(FAIL_AT="pip install")
        self.assertEqual(result.returncode, 9)
        self.assertNotIn("READY", result.stdout)
        self.assertNotIn('["pip", "check"', self.log.read_text())

    def test_dependency_check_failure_stops_bootstrap(self):
        result = self.run_provision(FAIL_AT="pip check")
        self.assertEqual(result.returncode, 9)
        self.assertNotIn("READY", result.stdout)

    def test_import_failure_stops_bootstrap(self):
        result = self.run_provision(IMPORT_EXIT="8")
        self.assertEqual(result.returncode, 8)
        self.assertNotIn("READY", result.stdout)

    def test_missing_uv_is_reported_by_prerequisites(self):
        for name in ("hermes", "python3"):
            self.mock_command(name, "#!/bin/sh\nexit 0\n")
        (self.bin / "uv").unlink()
        hook = self.root / ".githooks/pre-commit"
        hook.parent.mkdir()
        hook.touch()
        script = self.source + self.setup + (
            f"repo_root={shlex.quote(str(self.root))}\n"
            f"canonical_config={shlex.quote(str(self.requirements))}\n"
            f"PATH={shlex.quote(str(self.bin))}\ncheck_prerequisites\n"
        )
        result = subprocess.run(["bash"], input=script, text=True,
                                capture_output=True, env=self.env)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Required command is not available: uv", result.stderr)


if __name__ == "__main__":
    unittest.main()
