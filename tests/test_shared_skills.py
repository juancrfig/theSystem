"""Regression tests for theSystem's Hermes project-wide skill wiring."""

import shlex
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SharedSkillsTests(unittest.TestCase):
    def test_bootstrap_exposes_checkout_skills_to_hermes_without_installing_over_global_skills(self):
        """A fresh checkout links its shared skills; it never copies into Hermes home."""
        with tempfile.TemporaryDirectory(prefix="theSystem-skills-") as temp:
            temp = Path(temp)
            checkout = temp / "checkout"
            hermes_home = temp / "hermes-home"
            hermes_home.mkdir()
            global_skills = hermes_home / "skills"
            global_skills.mkdir()
            sentinel = global_skills / "keep-me" / "SKILL.md"
            sentinel.parent.mkdir()
            sentinel.write_text("user-installed skill; must not be changed\n")

            # Exercise the checked-out layout exactly as a clone provides it.
            result = subprocess.run(
                ["git", "clone", "--quiet", "--no-hardlinks", str(ROOT), str(checkout)],
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            # The requested skills are currently being added in this worktree;
            # preserve them in this clone fixture just as the eventual commit will.
            for source in (ROOT / "agents" / "skills").iterdir():
                if source.is_dir() and not (checkout / "agents" / "skills" / source.name).exists():
                    subprocess.run(["cp", "-a", str(source), str(checkout / "agents" / "skills" / source.name)], check=True)

            link = checkout / ".agents" / "skills"
            bootstrap_functions = temp / "bootstrap-functions"
            bootstrap_functions.write_text((checkout / "bootstrap").read_text().split("\nsteps=(", 1)[0])
            setup = (
                f"source {shlex.quote(str(bootstrap_functions))}\n"
                f"repo_root={shlex.quote(str(checkout))}\n"
                f"project_skills_link={shlex.quote(str(link))}\n"
                "link_project_skills\n"
            )
            result = subprocess.run(
                ["bash"], input=setup, text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(), checkout / "agents" / "skills")
            expected = {
                path.parent.relative_to(checkout / "agents" / "skills").as_posix()
                for path in (checkout / "agents" / "skills").rglob("SKILL.md")
            }
            self.assertTrue(expected, "checkout contains no skills")
            self.assertEqual(
                sentinel.read_text(),
                "user-installed skill; must not be changed\n",
                "bootstrap must not overwrite Hermes-installed global skills",
            )
            self.assertFalse((global_skills / "autonomous-ai-agents").exists())

    def test_all_tracked_shared_skill_directories_have_hermes_skill_manifests(self):
        skills_root = ROOT / "agents" / "skills"
        manifests = sorted(skills_root.rglob("SKILL.md"))
        self.assertTrue(manifests, "no shared skills found")
        for manifest in manifests:
            with self.subTest(manifest=manifest.relative_to(skills_root)):
                self.assertTrue(manifest.is_file())
                self.assertTrue(manifest.read_text().strip(), "empty SKILL.md")


if __name__ == "__main__":
    unittest.main()