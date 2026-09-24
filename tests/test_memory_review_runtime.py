"""Exercise runtime discovery without dependencies or real pending writes."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path("agents/skills/memory-request-review/scripts/review_memory_requests.py")


class ReviewRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="review-runtime-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "checkout with spaces"
        self.script = self.root / SCRIPT
        self.script.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / SCRIPT, self.script)
        self.runtime = self.root / ".agents/memory-review/bin/python"
        self.runtime.parent.mkdir(parents=True)
        self.env = dict(os.environ)
        self.env.pop("HERMES_MEMORY_REVIEW_PYTHON", None)

    def run_review(self, script=None, **env):
        return subprocess.run(
            [sys.executable, str(script or self.script), "inventory", "--home-root",
             str(self.root / "empty home")],
            cwd=self.temp.name, env=dict(self.env, **env), text=True,
            capture_output=True, timeout=10,
        )

    def fake_runtime(self, path):
        path.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\nexit 17\n')
        path.chmod(0o755)

    def test_discovers_checkout_runtime_and_preserves_arguments_and_exit_status(self):
        self.fake_runtime(self.runtime)
        result = self.run_review()
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [str(self.script), "inventory",
                         "--home-root", str(self.root / "empty home")])

    def test_missing_runtime_reports_bootstrap_without_installing(self):
        result = self.run_review()
        self.assertEqual(result.returncode, 2)
        self.assertIn("Run ./bootstrap", result.stderr)
        self.assertFalse(self.runtime.exists())

    def test_explicit_override_wins(self):
        selected = self.root / "custom python"
        self.fake_runtime(selected)
        result = self.run_review(HERMES_MEMORY_REVIEW_PYTHON=str(selected))
        self.assertEqual(result.returncode, 17, result.stderr)

    def test_invalid_override_does_not_fall_back(self):
        self.fake_runtime(self.runtime)
        result = self.run_review(HERMES_MEMORY_REVIEW_PYTHON=str(self.root / "missing"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("Review interpreter is unavailable", result.stderr)

    def test_non_executable_runtime_reports_bootstrap(self):
        self.runtime.touch()
        result = self.run_review()
        self.assertEqual(result.returncode, 2)
        self.assertIn("Run ./bootstrap", result.stderr)

    def test_skill_symlink_resolves_to_checkout(self):
        self.fake_runtime(self.runtime)
        link = Path(self.temp.name) / "linked skills"
        link.symlink_to(self.root / "agents/skills", target_is_directory=True)
        result = self.run_review(link / "memory-request-review/scripts/review_memory_requests.py")
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertEqual(result.stdout.splitlines()[0], str(self.script))

    def test_real_python_symlink_runs_once_and_inventories_isolated_home(self):
        self.runtime.symlink_to(sys.executable)
        result = self.run_review()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["counts"],
                         {"memory": 0, "skills": 0, "unreadable": 0})


if __name__ == "__main__":
    unittest.main()
