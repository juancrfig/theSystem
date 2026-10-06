"""F10 · Shared improvements: releases, baseline, `update` and proposal candidates (with F1's release install).

A temporary theSystem repo with release tags stands in for GitHub: a bare clone is the origin the installer clones
from. Release notes fall back to the tag annotations because the origin is not on GitHub.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SAMPLE = "one\ntwo\nthree\nfour\nfive\n"


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


class ReleaseCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.dev = self.tmp / "dev"
        for name in git(REPO, "ls-files", "-co", "--exclude-standard").splitlines():
            source = REPO / name
            if source.is_file():
                (self.dev / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, self.dev / name)
        (self.dev / "agents/rules/sample.md").write_text(SAMPLE)
        git(self.dev, "init", "-q", "-b", "master")
        git(self.dev, "add", "-A")
        git(self.dev, "commit", "-q", "-m", "first")
        git(self.dev, "tag", "-a", "v0.1.0", "-m", "Notes for v0.1.0")
        self.origin = self.tmp / "origin.git"
        git(self.tmp, "clone", "-q", "--bare", str(self.dev), str(self.origin))
        git(self.dev, "remote", "add", "origin", str(self.origin))
        self.workspace = self.home / "workspace"
        self.clone = self.home / "theSystem"
        self.env = {"HOME": str(self.home), "PATH": f"{self.home}/.local/bin:/usr/bin:/bin",
                    "THESYSTEM_REPO": str(self.origin)}

    def commit(self, changes, tag=None, notes=None):
        """Commits *changes* (path -> text, or None to delete) to master and publishes it, tagged when *tag*."""
        for name, text in changes.items():
            path = self.dev / name
            if text is None:
                path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
        git(self.dev, "add", "-A")
        git(self.dev, "commit", "-q", "-m", notes or "work")
        if tag:
            git(self.dev, "tag", "-a", tag, "-m", notes or tag)
        git(self.dev, "push", "-q", "origin", "master", "--tags")

    def install(self, **answers):
        result = subprocess.run(["bash", str(REPO / "install")], env={**self.env, **answers}, capture_output=True,
                                text=True, stdin=subprocess.DEVNULL, start_new_session=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def update(self, command="umbrella"):
        result = subprocess.run([command, "update"], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def baseline_tag(self):
        return json.loads((self.workspace / ".thesystem/baseline/release.json").read_text())["tag"]

    def ws(self, name):
        return (self.workspace / name).read_text()

    def snapshot(self):
        return {p.relative_to(self.workspace).as_posix(): p.read_bytes() for p in self.workspace.rglob("*")
                if p.is_file() and ".git" not in p.relative_to(self.workspace).parts}


class InstallTests(ReleaseCase):
    def test_fresh_install_takes_the_latest_release_not_master_and_records_its_baseline(self):
        self.commit({"workspace/GLOSSARY.md": "unreleased\n"})
        self.install()
        self.assertTrue((self.clone / ".git").is_dir())
        self.assertNotEqual(self.ws("GLOSSARY.md"), "unreleased\n")
        self.assertEqual(self.baseline_tag(), "v0.1.0")
        copy = self.workspace / ".thesystem/baseline/files"
        self.assertEqual((copy / "AGENTS.md").read_text(), self.ws("AGENTS.md"))
        self.assertIn("umbrella run", (copy / "AGENTS.md").read_text())
        self.assertEqual((copy / "agents/rules/sample.md").read_text(), SAMPLE)
        self.assertNotIn(".thesystem", git(self.workspace, "status", "--porcelain"))

    def test_piped_installer_bootstraps_the_clone_and_installs_the_release(self):
        # What the README's one-liner does: bash reads the script from stdin, with no theSystem tree around it.
        result = subprocess.run(["bash"], input=(REPO / "install").read_text(), env=self.env, capture_output=True,
                                text=True, start_new_session=True, cwd=self.tmp)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.clone / ".git").is_dir())
        self.assertEqual(self.baseline_tag(), "v0.1.0")
        self.assertIn(f"THESYSTEM_CLONE='{self.clone}'", (self.home / ".local/bin/umbrella").read_text())

    def test_without_a_release_the_install_says_so(self):
        git(self.origin, "tag", "-d", "v0.1.0")
        result = subprocess.run(["bash", str(REPO / "install")], env=self.env, capture_output=True, text=True,
                                stdin=subprocess.DEVNULL, start_new_session=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no release yet", result.stderr)


class UpdateTests(ReleaseCase):
    def setUp(self):
        super().setUp()
        self.install()

    def test_up_to_date_changes_nothing(self):
        before = self.snapshot()
        result = self.update()
        self.assertTrue(result["up_to_date"])
        self.assertEqual((result["from"], result["to"]), ("v0.1.0", "v0.1.0"))
        self.assertEqual(self.snapshot(), before)

    def test_clean_update_reports_versions_notes_and_files(self):
        self.commit({"agents/rules/sample.md": SAMPLE.replace("two", "TWO"),
                     "agents/skills/fresh/SKILL.md": "---\nname: fresh\n---\n",
                     "agents/rules/second-order-thinking-checks.md": None}, "v0.2.0", "Notes for v0.2.0")
        self.commit({"workspace/GLOSSARY.md": "# Glossary v3\n"}, "v0.3.0", "Notes for v0.3.0")
        result = self.update()
        self.assertEqual((result["from"], result["to"]), ("v0.1.0", "v0.3.0"))
        self.assertEqual(result["release_notes"], [{"tag": "v0.2.0", "notes": "Notes for v0.2.0"},
                                                   {"tag": "v0.3.0", "notes": "Notes for v0.3.0"}])
        self.assertEqual(result["updated"], ["GLOSSARY.md", "agents/rules/sample.md"])
        self.assertEqual(result["added"], ["agents/skills/fresh/SKILL.md"])
        self.assertEqual(result["removed"], ["agents/rules/second-order-thinking-checks.md"])
        self.assertEqual(result["conflicts"], [])
        self.assertTrue(result["baseline_recorded"])
        self.assertEqual(self.baseline_tag(), "v0.3.0")
        self.assertEqual(self.ws("GLOSSARY.md"), "# Glossary v3\n")
        self.assertFalse((self.workspace / "agents/rules/second-order-thinking-checks.md").exists())
        self.assertTrue(self.update()["up_to_date"])

    def test_local_edit_is_kept_and_edits_on_both_sides_merge(self):
        (self.workspace / "agents/roles.yaml").write_text("worker: {}\n")
        (self.workspace / "agents/rules/sample.md").write_text(SAMPLE.replace("five", "FIVE (local)"))
        self.commit({"agents/rules/sample.md": SAMPLE.replace("one", "ONE (upstream)")}, "v0.2.0")
        result = self.update()
        self.assertEqual(result["merged"], ["agents/rules/sample.md"])
        self.assertEqual(result["conflicts"], [])
        self.assertEqual(self.ws("agents/roles.yaml"), "worker: {}\n")
        self.assertEqual(self.ws("agents/rules/sample.md"),
                         SAMPLE.replace("one", "ONE (upstream)").replace("five", "FIVE (local)"))
        self.assertEqual(self.baseline_tag(), "v0.2.0")

    def test_clash_is_reported_with_markers_and_baseline_waits_for_the_resolution(self):
        (self.workspace / "agents/rules/sample.md").write_text(SAMPLE.replace("three", "local three"))
        self.commit({"agents/rules/sample.md": SAMPLE.replace("three", "upstream three"),
                     "workspace/GLOSSARY.md": "# Glossary v2\n"}, "v0.2.0")
        result = self.update()
        self.assertEqual(result["conflicts"], [{"path": "agents/rules/sample.md", "reason": "both changed"}])
        self.assertEqual(result["updated"], ["GLOSSARY.md"], "other files update despite the conflict")
        self.assertFalse(result["baseline_recorded"])
        text = self.ws("agents/rules/sample.md")
        for part in ("<<<<<<< workspace", "local three", "upstream three", ">>>>>>> v0.2.0"):
            self.assertIn(part, text)
        self.assertEqual(self.baseline_tag(), "v0.1.0")

        again = self.update()
        self.assertEqual(again["conflicts"], result["conflicts"])
        self.assertFalse(again["baseline_recorded"])
        self.assertEqual(self.baseline_tag(), "v0.1.0")

        (self.workspace / "agents/rules/sample.md").write_text(SAMPLE.replace("three", "agreed three"))
        resolved = self.update()
        self.assertEqual((resolved["to"], resolved["conflicts"], resolved["baseline_recorded"]), ("v0.2.0", [], True))
        self.assertEqual(self.baseline_tag(), "v0.2.0")
        self.assertEqual(self.ws("agents/rules/sample.md"), SAMPLE.replace("three", "agreed three"))
        self.assertTrue(self.update()["up_to_date"])

    def test_removals_on_either_side(self):
        rules = self.workspace / "agents/rules"
        (rules / "sample.md").write_text(SAMPLE + "six\n")               # changed here, removed upstream
        (rules / "comments-state-why-not-what.md").unlink()             # removed here, unchanged upstream
        (rules / "overlays-escape-clipping-ancestors.md").unlink()      # removed here, changed upstream
        overlays = (self.dev / "agents/rules/overlays-escape-clipping-ancestors.md").read_text()
        self.commit({"agents/rules/sample.md": None,
                     "agents/rules/second-order-thinking-checks.md": None,  # removed upstream, unchanged here
                     "agents/rules/overlays-escape-clipping-ancestors.md": overlays + "More.\n"}, "v0.2.0")
        result = self.update()
        self.assertEqual(result["removed"], ["agents/rules/second-order-thinking-checks.md"])
        self.assertEqual(result["conflicts"], [
            {"path": "agents/rules/overlays-escape-clipping-ancestors.md", "reason": "removed locally, changed upstream"},
            {"path": "agents/rules/sample.md", "reason": "removed upstream, changed locally"}])
        self.assertFalse((rules / "comments-state-why-not-what.md").exists())
        self.assertIn("six", (rules / "sample.md").read_text())
        self.assertIn("More.", (rules / "overlays-escape-clipping-ancestors.md").read_text())

        (rules / "sample.md").write_text(SAMPLE + "six\n")                # keep it
        (rules / "overlays-escape-clipping-ancestors.md").unlink()       # stay removed
        self.assertTrue(self.update()["baseline_recorded"])
        self.assertEqual(self.baseline_tag(), "v0.2.0")
        self.assertFalse((self.workspace / ".thesystem/baseline/files/agents/rules/sample.md").exists())

    def test_missing_baseline_is_adopted_with_differences_reported(self):
        shutil.rmtree(self.workspace / ".thesystem/baseline")
        (self.workspace / "AGENTS.md").write_text("my own guide\n")
        before = self.snapshot()
        result = self.update()
        self.assertEqual((result["from"], result["to"]), (None, "v0.1.0"))
        self.assertEqual(result["conflicts"], [{"path": "AGENTS.md", "reason": "differs from the release"}])
        self.assertEqual([result[key] for key in ("updated", "added", "removed", "merged")], [[]] * 4)
        guide = self.ws("AGENTS.md")
        self.assertIn("my own guide", guide)
        self.assertIn("umbrella run", guide)
        changed = {name for name in self.snapshot() if self.snapshot()[name] != before.get(name)}
        self.assertEqual({name for name in changed if not name.startswith(".thesystem/")}, {"AGENTS.md"})
        self.assertFalse((self.workspace / ".thesystem/baseline").exists())

        (self.workspace / "AGENTS.md").write_text("my own guide, resolved\n")
        self.assertTrue(self.update()["baseline_recorded"])
        self.assertEqual(self.baseline_tag(), "v0.1.0")
        self.assertTrue(self.update()["up_to_date"])

    def test_update_reapplies_silent_steps_from_the_new_release(self):
        bin_dir = self.home / "fakebin"
        bin_dir.mkdir()
        log = self.home / "hermes.log"
        (bin_dir / "hermes").write_text("#!/usr/bin/env python3\nimport json, sys\n"
                                        f"open({str(log)!r}, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n"
                                        f"p = {str(self.home / '.hermes/config.yaml')!r}\n"
                                        "a = sys.argv[1:]\n"
                                        "if a == ['config', 'path']: print(p)\n"
                                        "if a[:2] == ['config', 'get'] and a[2] in ('terminal.cwd', 'skills.trusted_project_dirs'):\n"
                                        " import yaml\n value = yaml.safe_load(open(p))\n"
                                        " for key in a[2].split('.'): value = value[key]\n"
                                        " print(yaml.safe_dump(value).strip())\n")
        (bin_dir / "hermes").chmod(0o755)
        self.env["PATH"] = f"{bin_dir}:{self.env['PATH']}"
        self.commit({"agents/.harness/personalities/main.md": "# Communication style v2\n",
                     "thesystem/__init__.py": "RELEASE = 'v0.2.0'\n"}, "v0.2.0")
        self.update()
        # PyYAML writes the config in one pass; without it, each setting goes through `hermes config set`.
        config = self.home / ".hermes/config.yaml"
        written = config.read_text() if config.exists() else ""
        sets = [json.loads(line) for line in log.read_text().splitlines()]
        styles = [call[3] for call in sets if call[:3] == ["config", "set", "personalities.main"]]
        self.assertTrue("main: '# Communication style v2'" in written or styles[-1:] == ["# Communication style v2"],
                        written)
        installed = self.home / ".local/share/thesystem/thesystem/__init__.py"
        self.assertEqual(installed.read_text(), "RELEASE = 'v0.2.0'\n")


class CloneTests(ReleaseCase):
    def test_install_and_update_leave_the_clones_branch_and_files_alone(self):
        git(self.tmp, "clone", "-q", str(self.origin), str(self.clone))
        git(self.clone, "checkout", "-q", "-b", "my-work")
        (self.clone / "workspace/GLOSSARY.md").write_text("work in progress\n")
        (self.clone / "notes.txt").write_text("untracked\n")

        def state():
            return (git(self.clone, "branch", "--show-current"), git(self.clone, "rev-parse", "HEAD"),
                    git(self.clone, "status", "--porcelain"), (self.clone / "workspace/GLOSSARY.md").read_text())

        before = state()
        self.install()
        self.assertEqual(state(), before)
        self.assertNotEqual(self.ws("GLOSSARY.md"), "work in progress\n")
        self.commit({"agents/rules/sample.md": SAMPLE + "six\n"}, "v0.2.0")
        self.assertEqual(self.update()["to"], "v0.2.0")
        self.assertEqual(state(), before)


class ProposalCandidateTests(ReleaseCase):
    def candidates(self, *args):
        script = self.workspace / "agents/skills/propose-default/scripts/candidates.py"
        result = subprocess.run(["python3", str(script), *args], cwd=self.workspace, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_changed_added_and_deleted_files_are_found_and_mapped_back_to_the_repo(self):
        self.install(THESYSTEM_COMPANY="acme")
        guide = self.workspace / "AGENTS.md"
        guide.write_text(guide.read_text() + "\nRun `acme update` when the human asks.\n")
        (self.workspace / "agents/skills/mine/SKILL.md").parent.mkdir(parents=True)
        (self.workspace / "agents/skills/mine/SKILL.md").write_text("---\nname: mine\n---\n")
        (self.workspace / "agents/skills/mine/__pycache__").mkdir()
        (self.workspace / "agents/skills/mine/__pycache__/x.pyc").write_bytes(b"\0")
        (self.workspace / "agents/rules/sample.md").unlink()
        (self.workspace / "app/agents").mkdir(parents=True)
        (self.workspace / "app/agents/roles.yaml").write_text("worker: {}\n")
        (self.workspace / "app/notes.md").write_text("client secrets\n")
        (self.workspace / ".thesystem/scratch.txt").write_text("state\n")

        found = self.candidates("list")["candidates"]
        self.assertEqual(found, [
            {"change": "changed", "path": "AGENTS.md", "repo_path": "workspace/AGENTS.md"},
            {"change": "deleted", "path": "agents/rules/sample.md", "repo_path": "agents/rules/sample.md"},
            {"change": "added", "path": "agents/skills/mine/SKILL.md", "repo_path": "agents/skills/mine/SKILL.md"}])

        # master moved on since the baseline release; the proposal must carry only the workspace's edit.
        self.commit({"workspace/AGENTS.md": "# Workspace guide (newer)\n"
                     + (self.dev / "workspace/AGENTS.md").read_text().split("\n", 1)[1]})
        applied = self.candidates("apply", "--repo", str(self.dev), "AGENTS.md", "agents/rules/sample.md",
                                  "agents/skills/mine/SKILL.md")["applied"]
        self.assertFalse(any(entry["conflict"] for entry in applied))
        proposed = (self.dev / "workspace/AGENTS.md").read_text()
        self.assertIn("Run `{{COMMAND}} update` when the human asks.", proposed)
        self.assertIn("`{{COMMAND}} run`", proposed)
        self.assertIn("# Workspace guide (newer)", proposed)
        self.assertNotIn("acme", proposed)
        self.assertFalse((self.dev / "agents/rules/sample.md").exists())
        self.assertTrue((self.dev / "agents/skills/mine/SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
