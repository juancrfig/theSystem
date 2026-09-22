import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ToolchainChecks(unittest.TestCase):
    def test_harness_links_are_repaired_from_canonical_skills(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            shared = workspace / "agents/utils/scripts/preflight"
            shared.mkdir(parents=True)
            shutil.copy(ROOT / "common.sh", shared / "common.sh")
            skill = workspace / "agents/skills/example-skill"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\\nname: example-skill\\ndescription: Example skill.\\n---\\n"
            )
            stale = workspace / ".agents/skills/example-skill"
            stale.parent.mkdir(parents=True)
            stale.symlink_to("missing-skill")

            result = subprocess.run(
                [
                    "bash", "-c",
                    'source "$1"; check_agent_skill_harnesses; exit "$PREFLIGHT_FAILED"',
                    "test", str(shared / "common.sh"),
                ],
                cwd=workspace,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(stale.resolve(), skill.resolve())
            self.assertFalse((workspace / ".github").exists())

    def test_patch_version_mismatch_fails(self):
        result = subprocess.run(
            [
                "bash", "-c",
                'source "$1"; check_exact Node 1.2.3 .nvmrc printf v1.2.4; exit "$PREFLIGHT_FAILED"',
                "test", str(ROOT / "common.sh"),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("expected 1.2.3", result.stdout)
        self.assertIn("observed v1.2.4", result.stdout)

    def test_templates_read_current_source_pins_each_run(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            shared = workspace / "agents/utils/scripts/preflight"
            shared.mkdir(parents=True)
            shutil.copy(ROOT / "common.sh", shared / "common.sh")
            clone = workspace / "project/clone"
            clone.mkdir(parents=True)
            binaries = workspace / "bin"
            binaries.mkdir()
            for name, output in [("node", "v1.2.3"), ("npm", "4.5.6"),
                                 ("flutter", '{"frameworkVersion":"7.8.9"}')]:
                binary = binaries / name
                binary.write_text(f"#!/bin/sh\nprintf '%s\\n' '{output}'\n")
                binary.chmod(0o755)
            (clone / ".nvmrc").write_text("1.2.3\n")
            (clone / "package.json").write_text('{"packageManager":"npm@4.5.6"}')
            (clone / "tool").mkdir()
            (clone / "tool/toolchain.json").write_text('{"flutter":"7.8.9"}')

            for stack, source_file, old_pin, new_pin in [
                ("react", ".nvmrc", "1.2.3", "1.2.4"),
                ("flutter", "tool/toolchain.json", "7.8.9", "7.8.10"),
            ]:
                with self.subTest(stack=stack):
                    template = ROOT.parents[1] / "templates/preflight" / stack / "preflight"
                    shutil.copy(template, clone / "preflight")
                    first = self.run_preflight(clone, binaries)
                    self.assertIn("PASS", first.stdout)
                    self.replace_pin(clone / source_file, old_pin, new_pin)
                    second = self.run_preflight(clone, binaries)
                    self.assertIn(f"expected {new_pin}", second.stdout)

    @staticmethod
    def run_preflight(clone, binaries):
        return subprocess.run(
            ["bash", str(clone / "preflight")],
            cwd=clone,
            env={**os.environ, "PATH": str(binaries) + os.pathsep + os.environ["PATH"]},
            capture_output=True,
            text=True,
        )

    @staticmethod
    def replace_pin(path, old_pin, new_pin):
        path.write_text(path.read_text().replace(old_pin, new_pin))


if __name__ == "__main__":
    unittest.main()
