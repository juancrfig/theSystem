"""Shared provisioning contracts verified against isolated Hermes fixtures."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from thesystem.setup.provisioning import (
    HermesTarget, apply_config, enable_toolsets, link_project_skills,
    read_config, read_toolsets, skills_to_pin,
)


class ProvisioningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="shared-provisioning-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "isolated-home"
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.log = self.root / "calls.jsonl"
        self.hermes = self.root / "hermes"
        self.hermes.write_text("#!/usr/bin/env python3\nimport json,os,sys\nopen(os.environ['CALL_LOG'],'a').write(json.dumps([os.environ['HERMES_HOME'],sys.argv[1:]])+'\\n')\nraise SystemExit(int(os.environ.get('FIXTURE_EXIT','0')))\n")
        self.hermes.chmod(0o755)
        self.config = self.root / "settings.tsv"
        self.config.write_text('compression.enabled\ttrue\nmodel.label\t"text with spaces"\n')
        self.toolsets = self.root / "toolsets.txt"
        self.toolsets.write_text("file\nweb\n")

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_config_and_toolsets_are_declaration_driven_and_profile_scoped(self):
        target = HermesTarget(self.home, "reviewer", str(self.hermes))
        with patch.dict(os.environ, CALL_LOG=str(self.log)):
            self.assertEqual(apply_config(self.config, target), 2)
            self.assertEqual(enable_toolsets(self.toolsets, target), 2)
        self.assertEqual([call[0] for call in self.calls()], [str(self.home)] * 3)
        self.assertTrue(all(call[1][:2] == ["-p", "reviewer"] for call in self.calls()))
        self.config.write_text(self.config.read_text() + 'fixture.extra\t{"value": 1}\n')
        self.toolsets.write_text(self.toolsets.read_text() + "browser\n")
        with patch.dict(os.environ, CALL_LOG=str(self.log)):
            self.assertEqual(apply_config(self.config, target), 3)
            self.assertEqual(enable_toolsets(self.toolsets, target), 3)
        self.assertIn(["-p", "reviewer", "config", "set", "--force", "fixture.extra", '{"value":1}'],
                      [call[1] for call in self.calls()])
        self.assertIn("browser", self.calls()[-1][1])

    def test_string_settings_are_passed_unquoted_for_hermes_type_aware_coercion(self):
        self.config.write_text('approvals.mode\t"off"\n')
        target = HermesTarget(self.home, "reviewer", str(self.hermes))
        with patch.dict(os.environ, CALL_LOG=str(self.log)):
            self.assertEqual(apply_config(self.config, target), 1)
        self.assertEqual(self.calls()[0][1], ["-p", "reviewer", "config", "set", "--force", "approvals.mode", "off"])

    def test_invalid_declarations_fail_before_hermes_mutation(self):
        target = HermesTarget(self.home, "master", str(self.hermes))
        for declaration in ("valid.key\ttrue\nbad..key\ttrue\n", "key\tnot-json\n", "# empty\n"):
            self.config.write_text(declaration)
            with self.assertRaises(ValueError):
                read_config(self.config)
        for declaration in ("file\nfile\n", "Bad-name\n", "# empty\n"):
            self.toolsets.write_text(declaration)
            with self.assertRaises(ValueError):
                read_toolsets(self.toolsets)
        self.assertFalse(self.log.exists())

    def test_hermes_failure_propagates_without_success_result(self):
        target = HermesTarget(self.home, "master", str(self.hermes))
        with patch.dict(os.environ, CALL_LOG=str(self.log), FIXTURE_EXIT="9"):
            with self.assertRaises(subprocess.CalledProcessError) as failure:
                apply_config(self.config, target)
        self.assertEqual(failure.exception.returncode, 9)

    def test_link_repairs_empty_directory_and_refuses_unsafe_or_nonempty_targets(self):
        canonical = self.workspace / "agents/skills/sample"
        canonical.mkdir(parents=True)
        (canonical / "SKILL.md").write_text("skill\n")
        link = self.workspace / ".agents/skills"
        link.mkdir(parents=True)
        self.assertTrue(link_project_skills(self.workspace))
        self.assertEqual(os.readlink(link), "../agents/skills")
        self.assertFalse(link_project_skills(self.workspace))
        link.unlink()
        link.mkdir()
        sentinel = link / "keep"
        sentinel.write_text("personal skill")
        with self.assertRaises(ValueError):
            link_project_skills(self.workspace)
        self.assertEqual(sentinel.read_text(), "personal skill")
        unsafe_parent = self.root / "outside"
        unsafe_parent.mkdir()
        other_workspace = self.root / "unsafe-workspace"
        (other_workspace / "agents/skills/sample").mkdir(parents=True)
        (other_workspace / "agents/skills/sample/SKILL.md").write_text("skill")
        (other_workspace / ".agents").symlink_to(unsafe_parent, target_is_directory=True)
        with self.assertRaises(ValueError):
            link_project_skills(other_workspace)

    def test_existing_workspace_skill_links_preserve_project_skills_and_add_missing_canonical_links(self):
        source = self.workspace / "agents/skills"
        for name in ("existing", "added"):
            (source / name).mkdir(parents=True)
            (source / name / "SKILL.md").write_text("skill\n")
        project = self.workspace / "project/agents/skills/project-only"
        project.mkdir(parents=True)
        (project / "SKILL.md").write_text("project skill\n")
        discovery = self.workspace / ".agents/skills"
        discovery.mkdir(parents=True)
        (discovery / "existing").symlink_to("../../agents/skills/existing")
        (discovery / "project-only").symlink_to("../../project/agents/skills/project-only")
        self.assertTrue(link_project_skills(self.workspace))
        self.assertTrue(discovery.is_dir())
        self.assertFalse(discovery.is_symlink())
        self.assertEqual((discovery / "added").resolve(), source / "added")
        self.assertEqual(os.readlink(discovery / "project-only"), "../../project/agents/skills/project-only")
        self.assertFalse(link_project_skills(self.workspace))

    def test_existing_discovery_links_outside_the_workspace_are_refused_without_writes(self):
        source = self.workspace / "agents/skills/sample"
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text("skill\n")
        outside = self.root / "outside-skill"
        outside.mkdir()
        (outside / "SKILL.md").write_text("outside skill\n")
        discovery = self.workspace / ".agents/skills"
        discovery.mkdir(parents=True)
        (discovery / "outside").symlink_to(outside)
        with self.assertRaises(ValueError):
            link_project_skills(self.workspace)
        self.assertEqual(list(discovery.iterdir()), [discovery / "outside"])

    def test_missing_or_empty_canonical_skills_never_create_a_ready_link(self):
        for source in (self.workspace / "agents/skills",):
            source.mkdir(parents=True)
            with self.assertRaises(ValueError):
                link_project_skills(self.workspace)
        self.assertFalse((self.workspace / ".agents/skills").exists())

    def test_curator_selection_uses_selected_profile_usage_and_validates_rows(self):
        for name in ("candidate", "already", "bundled"):
            directory = self.workspace / "agents/skills" / name
            directory.mkdir(parents=True)
            (directory / "SKILL.md").write_text("skill")
        sidecar = self.home / "profiles/reviewer/skills/.usage.json"
        sidecar.parent.mkdir(parents=True)
        sidecar.write_text(json.dumps({"already": {"pinned": True}}))
        usage = [{"name": "candidate", "provenance": "agent"},
                 {"name": "already", "provenance": "agent"},
                 {"name": "bundled", "provenance": "bundled"}]
        self.assertEqual(skills_to_pin(self.workspace, sidecar.parents[1], usage), ["candidate"])
        with self.assertRaises(ValueError):
            skills_to_pin(self.workspace, sidecar.parents[1], [None])
        sidecar.write_text("{invalid")
        with self.assertRaises(ValueError):
            skills_to_pin(self.workspace, sidecar.parents[1], usage)

    def test_review_path_bridge_checks_interpreter_and_keeps_local_import_precedence(self):
        from thesystem.setup.runtime_probe import write_review_paths
        with tempfile.TemporaryDirectory(prefix="review-path-bridge-") as temporary:
            root = Path(temporary)
            environment = root / "review env"
            subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
            python = environment / "bin/python"
            purelib = Path(subprocess.check_output(
                [str(python), "-c", 'import sysconfig; print(sysconfig.get_path("purelib"))'], text=True
            ).strip())
            hermes_site = root / "Hermes site-packages"
            hermes_site.mkdir()
            (purelib / "fixture_precedence.py").write_text('VALUE = "review"\n')
            (hermes_site / "fixture_precedence.py").write_text('VALUE = "hermes"\n')
            for package, content in {
                "typesafe_sdk/__init__.py": "class Noul: pass\nclass TypeSafeClient: pass\n",
                "tools.py": "write_approval = object()\n",
                "hermes_cli/__init__.py": "",
                "hermes_cli/write_approval_commands.py": "def _apply_one(): pass\n",
            }.items():
                path = purelib / package
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            metadata = purelib / "typesafe_sdk-0.7.1.dist-info"
            metadata.mkdir()
            (metadata / "METADATA").write_text("Name: typesafe-sdk\nVersion: 0.7.1\n")
            probe = Path(__file__).resolve().parents[1] / "thesystem/setup/runtime_probe.py"
            version = json.loads(subprocess.check_output(
                [str(python), "-c", "import json,sys; print(json.dumps(list(sys.version_info[:2])))"], text=True
            ))
            write_review_paths([version, [str(hermes_site)]], purelib=purelib)
            precedence = subprocess.run([str(python), "-c", "import fixture_precedence; print(fixture_precedence.VALUE)"],
                                        check=True, text=True, capture_output=True)
            self.assertEqual(precedence.stdout.strip(), "review")
            imports = subprocess.run([str(python), "-B", str(probe), "verify-review-imports"],
                                     check=True, text=True, capture_output=True)
            self.assertEqual(imports.stdout.strip(), "typesafe-sdk 0.7.1")
            with self.assertRaisesRegex(ValueError, "Python differs from Hermes"):
                write_review_paths([[0, 0], [str(hermes_site)]])


if __name__ == "__main__":
    unittest.main()
