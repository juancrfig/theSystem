"""Installer integration tests run entirely against temporary homes."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import tarfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallerIntegrationTests(unittest.TestCase):
    def test_experimental_rules_require_opt_in_and_preserve_existing_files(self):
        with tempfile.TemporaryDirectory(prefix="thesystem-experimental-") as td:
            workspace = Path(td) / "workspace"
            rule = workspace / "agents/rules/second-order-thinking-checks.md"
            skill = workspace / "agents/skills/manual-authoring"
            def provision(*flags):
                result = subprocess.run(
                    ["bash", "-c", 'script=$1; source_root=$2; target=$3; shift 3; source "$script"; provision_distribution "$source_root" "$target"',
                     "bash", str(ROOT / "install"), str(ROOT), str(workspace), *flags],
                    text=True, capture_output=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            provision()
            self.assertFalse(rule.exists())
            self.assertFalse(skill.exists())
            self.assertTrue((workspace / "agents/rules/comments-state-why-not-what.md").exists())
            provision("--experimental")
            self.assertEqual(rule.read_text(), (ROOT / "agents/rules/second-order-thinking-checks.md").read_text())
            self.assertEqual((skill / "SKILL.md").read_text(), (ROOT / "agents/skills/manual-authoring/SKILL.md").read_text())
            rule.write_text("user customization\n")
            provision()
            provision("--experimental")
            self.assertEqual(rule.read_text(), "user customization\n")

    def test_noninteractive_install_provisions_workspace_and_master_only(self):
        with tempfile.TemporaryDirectory(prefix="thesystem-install-") as td:
            root = Path(td)
            home = root / "home"
            bin_dir = root / "bin"
            workspace = root / "workspace"
            home.mkdir(); bin_dir.mkdir()
            (home / '.hermes' / 'profiles' / 'master').mkdir(parents=True)
            (home / '.hermes' / 'profiles' / 'master' / 'config.yaml').write_text('custom: true\n')
            (home / '.hermes' / 'config.yaml').write_text('default: untouched\n')
            fake_agent = root / "agent"
            fake_agent.mkdir()
            (fake_agent / "__init__.py").write_text("")
            (fake_agent / "skill_utils.py").write_text("from pathlib import Path\nimport os\ndef iter_skill_index_files(root, name): return Path(root).rglob(name)\ndef get_project_skills_dirs(): return [Path(os.environ['TERMINAL_CWD']) / '.agents' / 'skills']\ndef iter_project_skill_files(directory): return Path(directory).rglob('SKILL.md')\n")
            (root / "yaml.py").write_text("def safe_load(_text): return {'test': True}\n")
            log = root / "calls.jsonl"
            (bin_dir / "uv").write_text("#!/bin/sh\nif [ \"$1\" = venv ]; then mkdir -p \"$4/bin\"; printf '#!/bin/sh\\nexit ${IMPORT_EXIT:-0}\\n' > \"$4/bin/python\"; chmod +x \"$4/bin/python\"; fi\nexit 0\n")
            (bin_dir / "uv").chmod(0o755)
            hermes = bin_dir / "hermes"
            hermes.write_text("""#!/usr/bin/env python3
import json, os, pathlib, sys
args=sys.argv[1:]
with open(os.environ['CALL_LOG'], 'a') as f: f.write(json.dumps(args)+'\\n')
if args[:1] == ['--print-runtime-command']:
    print(json.dumps(['/usr/bin/python3', '-I', '-c', "import sys; sys.path.insert(0, %r); import runpy; runpy.run_module('hermes_cli.main', run_name='__main__', alter_sys=True)" % os.environ['PYTHONPATH'].split(':')[0]]))
elif args[-2:] == ['profile','list']:
    print(' Profile master' if pathlib.Path(os.environ['HOME'], '.hermes', 'profiles', 'master').exists() else ' Profile default')
elif args[-2:-1] == ['profile'] and args[-1:] == ['create']:
    pathlib.Path(os.environ['HOME'], '.hermes', 'profiles', 'master').mkdir(parents=True, exist_ok=True)
elif args[:2] == ['-p','master'] and 'setup' in args:
    pathlib.Path(os.environ['HOME'], '.hermes', 'profiles', 'master').mkdir(parents=True, exist_ok=True)
elif args == ['-p', 'master', 'curator', 'usage', '--json']:
    print('[]')
elif 'config' in args:
    pass
elif 'skills' in args:
    pass
""")
            hermes.chmod(0o755)
            archive = root / "theSystem.tar.gz"
            distribution_paths = (
                "AGENTS.md", "CONTEXT.md", "README.md", "orchestrator", "bootstrap",
                "install", "company_cli.py", "agents", ".githooks", "docs",
            )
            with tarfile.open(archive, "w:gz") as bundle:
                for name in distribution_paths:
                    source = ROOT / name
                    if source.exists() or source.is_symlink():
                        bundle.add(source, arcname=f"theSystem-master/{name}")
            env = dict(
                os.environ,
                HOME=str(home),
                PATH=f"{bin_dir}:{os.environ['PATH']}",
                CALL_LOG=str(log),
                PYTHONPATH=str(root),
                THESYSTEM_ARCHIVE_URL=f"file://{archive}",
            )
            env.pop("HERMES_HOME", None)
            result = subprocess.run(
                ["bash", "--noprofile", "--norc", "-s", "--", "--workspace", str(workspace), "--company", "Acme", "--non-interactive"],
                input=(ROOT / "install").read_text(),
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((workspace / "agents" / "roles.yaml").exists())
            self.assertTrue((workspace / ".agents" / "skills").is_symlink())
            self.assertFalse((workspace / "projects").exists())
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertFalse(any(c[:2] == ["profile", "create"] for c in calls))
            self.assertFalse(any(c[:2] == ["-p", "master"] and "setup" in c for c in calls))
            self.assertFalse(any("default" in c and "config" in c for c in calls))
            self.assertEqual((home / '.hermes' / 'config.yaml').read_text(), 'default: untouched\n')

    def test_noninteractive_new_profile_fails_before_claiming_blank_slate(self):
        with tempfile.TemporaryDirectory(prefix="thesystem-install-") as td:
            root = Path(td); home = root / "home"; bin_dir = root / "bin"; home.mkdir(); bin_dir.mkdir()
            (bin_dir / "uv").write_text("#!/bin/sh\nexit 0\n"); (bin_dir / "uv").chmod(0o755)
            hermes = bin_dir / "hermes"
            hermes.write_text("#!/bin/sh\nif [ \"$1\" = --version ]; then exit 0; fi\nif [ \"$1\" = -p ] && [ \"$3\" = profile ] && [ \"$4\" = list ]; then [ -d \"$HOME/.hermes/profiles/master\" ] && echo master; exit 0; fi\nif [ \"$1\" = -p ] && [ \"$3\" = profile ] && [ \"$4\" = create ]; then mkdir -p \"$HOME/.hermes/profiles/master\"; exit 0; fi\nexit 0\n"); hermes.chmod(0o755)
            result = subprocess.run([str(ROOT / "install"), "--workspace", str(root / "workspace"), "--company", "Acme", "--non-interactive"], env=dict(os.environ, HOME=str(home), PATH=f"{bin_dir}:{os.environ['PATH']}"), text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("requires interactive official Blank Slate setup", result.stderr)

    def test_help_is_safe_when_piped(self):
        result = subprocess.run(["bash", "-c", f"printf '' | {ROOT / 'install'} --help"], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("not a git checkout", result.stdout)

    def test_company_cli_rejects_escape_and_noninteractive_missing_argument(self):
        with tempfile.TemporaryDirectory(prefix="thesystem-company-") as td:
            root = Path(td); workspace = root / "workspace"; workspace.mkdir()
            home = root / "home"; home.mkdir(); bindir = home / '.local' / 'bin'; bindir.mkdir(parents=True)
            source = ROOT / "company_cli.py"
            company = bindir / "Acme"
            company.write_text(f"#!/usr/bin/env python3\nexec(compile(open({str(source)!r}).read(), {str(source)!r}, 'exec'))\n")
            company.chmod(0o755)
            env = dict(os.environ, HOME=str(home), PATH=f"{bindir}:{os.environ['PATH']}")
            result = subprocess.run([str(company), "add-project"], cwd=str(root), env=dict(env, THESYSTEM_WORKSPACE=str(workspace)), text=True, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)["status"], "error")
            outside = root / "outside"; outside.mkdir()
            result = subprocess.run([str(company), "add-project", str(outside)], env=dict(env, THESYSTEM_WORKSPACE=str(workspace)), text=True, capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)["code"], "PROJECT_OUTSIDE_WORKSPACE")


if __name__ == "__main__":
    unittest.main()
