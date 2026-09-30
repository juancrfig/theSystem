"""Shared setup operations; Hermes mutations are confined to fixture homes."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from thesystem.setup.provisioning import (
    HermesTarget, apply_config, enable_toolsets, link_project_skills,
    read_config, read_toolsets, skills_to_pin,
)

ROOT = Path(__file__).resolve().parents[1]


class ProvisioningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="shared-provisioning-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "isolated home"
        self.workspace = self.root / "workspace with spaces"
        self.workspace.mkdir()
        self.log = self.root / "calls.jsonl"
        self.hermes = self.root / "fake hermes"
        self.hermes.write_text('''#!/usr/bin/env python3
import json, os, sys
with open(os.environ['CALL_LOG'], 'a') as log:
    log.write(json.dumps([os.environ['HERMES_HOME'], sys.argv[1:]]) + '\\n')
sys.exit(int(os.environ.get('FIXTURE_EXIT', '0')))
''')
        self.hermes.chmod(0o755)
        self.config = self.root / "settings.tsv"
        self.config.write_text('# comment\ncompression.enabled\ttrue\nmodel.label\t"text with spaces"\n')
        self.toolsets = self.root / "toolsets.txt"
        self.toolsets.write_text('# comment\nfile\nweb\n')
        self.target = HermesTarget(self.home, "master", str(self.hermes))
        from unittest.mock import patch
        self.env_patch = patch.dict(os.environ, CALL_LOG=str(self.log))
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_config_and_tools_use_explicit_home_and_profile(self):
        self.assertEqual(apply_config(self.config, self.target), 2)
        self.assertEqual(enable_toolsets(self.toolsets, self.target), 2)
        self.assertEqual(self.calls(), [
            [str(self.home), ['-p', 'master', 'config', 'set', '--force', 'compression.enabled', 'true']],
            [str(self.home), ['-p', 'master', 'config', 'set', '--force', 'model.label', '"text with spaces"']],
            [str(self.home), ['-p', 'master', 'tools', 'enable', '--platform', 'cli', 'file', 'web']],
        ])

    def test_unscoped_tools_preserve_bootstrap_target(self):
        enable_toolsets(self.toolsets, HermesTarget(self.home, executable=str(self.hermes)))
        self.assertEqual(self.calls()[0], [str(self.home), ['tools', 'enable', '--platform', 'cli', 'file', 'web']])

    def test_added_declarations_and_repeat_runs_are_consumed(self):
        self.config.write_text(self.config.read_text() + 'fixture.extra\t{"value": 1}\n')
        self.toolsets.write_text(self.toolsets.read_text() + 'browser\n')
        for _ in range(2):
            self.assertEqual(apply_config(self.config, self.target), 3)
            self.assertEqual(enable_toolsets(self.toolsets, self.target), 3)
        self.assertEqual(self.calls()[2][1][-2:], ['fixture.extra', '{"value":1}'])
        self.assertEqual(self.calls()[3][1][-3:], ['file', 'web', 'browser'])

    def test_invalid_config_never_partially_applies(self):
        for invalid in ('no-tab', 'bad..key\ttrue', 'key\tnot-json', '# comments only', ''):
            with self.subTest(invalid=invalid):
                self.config.write_text('valid.key\ttrue\n' + invalid if invalid and not invalid.startswith('#') else invalid)
                with self.assertRaises(ValueError):
                    apply_config(self.config, self.target)
                self.assertFalse(self.log.exists())

    def test_invalid_toolsets_fail_before_mutation(self):
        for text in ('file\nfile\n', 'file\nBad-name\n', 'file\r\n', ' file\n', '# only comments\n', ''):
            with self.subTest(text=text):
                self.toolsets.write_text(text)
                with self.assertRaises(ValueError):
                    enable_toolsets(self.toolsets, self.target)
                self.assertFalse(self.log.exists())

    def test_subprocess_failure_is_not_success(self):
        from unittest.mock import patch
        with patch.dict(os.environ, FIXTURE_EXIT='9'):
            with self.assertRaises(subprocess.CalledProcessError) as caught:
                apply_config(self.config, self.target)
            self.assertEqual(caught.exception.returncode, 9)
            self.assertEqual(len(self.calls()), 1)
            with self.assertRaises(subprocess.CalledProcessError):
                enable_toolsets(self.toolsets, self.target)

    def test_skill_link_is_relative_idempotent_and_preserves_conflicts(self):
        link = self.workspace / '.agents/skills'
        self.assertTrue(link_project_skills(self.workspace))
        self.assertEqual(os.readlink(link), '../agents/skills')
        self.assertFalse(link_project_skills(self.workspace))
        link.unlink()
        link.mkdir()
        sentinel = link / 'keep'
        sentinel.write_text('personal skill')
        with self.assertRaises(ValueError):
            link_project_skills(self.workspace)
        self.assertEqual(sentinel.read_text(), 'personal skill')
        sentinel.unlink()
        link.rmdir()
        link.symlink_to('../elsewhere')
        with self.assertRaises(ValueError):
            link_project_skills(self.workspace)
        self.assertEqual(os.readlink(link), '../elsewhere')

    def test_parsers_return_data_not_presentation(self):
        self.assertEqual(read_config(self.config), [('compression.enabled', 'true'), ('model.label', '"text with spaces"')])
        self.assertEqual(read_toolsets(self.toolsets), ['file', 'web'])

    def test_curator_rows_and_profile_sidecar_are_validated_before_pin_selection(self):
        skills = self.workspace / 'agents/skills'
        for directory in ('candidate', 'duplicate/candidate', 'already', 'bundled'):
            skill = skills / directory
            skill.mkdir(parents=True)
            (skill / 'SKILL.md').write_text('fixture')
        sidecar = self.home / 'profiles/master/skills/.usage.json'
        sidecar.parent.mkdir(parents=True)
        sidecar.write_text(json.dumps({'already': {'pinned': True}, 'candidate': {'pinned': False}}))
        usage = [
            {'name': 'candidate', 'provenance': 'agent'},
            {'name': 'already', 'provenance': 'agent'},
            {'name': 'bundled', 'provenance': 'bundled'},
        ]
        self.assertEqual(skills_to_pin(self.workspace, sidecar.parents[1], usage), ['candidate'])

        for invalid in ([None], [{'name': '', 'provenance': 'agent'}],
                        [{'name': 'candidate', 'provenance': 'unknown'}],
                        [usage[0], usage[0]]):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                skills_to_pin(self.workspace, sidecar.parents[1], invalid)

        for invalid_sidecar in ('[]', '{"candidate": []}', '{"candidate": {"pinned": "false"}}'):
            sidecar.write_text(invalid_sidecar)
            with self.subTest(invalid_sidecar=invalid_sidecar), self.assertRaises(ValueError):
                skills_to_pin(self.workspace, sidecar.parents[1], usage)

    def test_review_path_bridge_checks_runtime_version_and_keeps_local_import_precedence(self):
        from thesystem.setup.runtime_probe import write_review_paths

        with tempfile.TemporaryDirectory(prefix='review-path-bridge-') as temp:
            root = Path(temp)
            environment = root / 'review env'
            subprocess.run([sys.executable, '-m', 'venv', str(environment)], check=True)
            python = environment / 'bin/python'
            purelib = Path(subprocess.check_output(
                [str(python), '-c', 'import sysconfig; print(sysconfig.get_path("purelib"))'], text=True
            ).strip())
            hermes_site = root / 'Hermes site-packages with spaces'
            hermes_site.mkdir()
            (purelib / 'fixture_precedence.py').write_text('VALUE = "review"\n')
            (hermes_site / 'fixture_precedence.py').write_text('VALUE = "hermes"\n')
            review_sdk = purelib / 'typesafe_sdk'
            review_sdk.mkdir()
            (review_sdk / '__init__.py').write_text('class Noul: pass\nclass TypeSafeClient: pass\n')
            (purelib / 'tools.py').write_text('write_approval = object()\n')
            review_cli = purelib / 'hermes_cli'
            review_cli.mkdir()
            (review_cli / '__init__.py').write_text('')
            (review_cli / 'write_approval_commands.py').write_text('def _apply_one(): pass\n')
            review_dist = purelib / 'typesafe_sdk-0.7.1.dist-info'
            review_dist.mkdir()
            (review_dist / 'METADATA').write_text('Name: typesafe-sdk\nVersion: 0.7.1\n')
            hermes_sdk = hermes_site / 'typesafe_sdk-0.1.dist-info'
            hermes_sdk.mkdir()
            (hermes_sdk / 'METADATA').write_text('Name: typesafe-sdk\nVersion: 0.1\n')
            probe = ROOT / 'thesystem/setup/runtime_probe.py'
            version = subprocess.check_output(
                [str(python), '-c', 'import json,sys; print(json.dumps(list(sys.version_info[:2])))'],
                text=True,
            ).strip()
            subprocess.run([str(python), '-B', str(probe), 'write-review-paths',
                            json.dumps([json.loads(version), [str(hermes_site)]])], check=True)
            result = subprocess.run([str(python), '-c',
                                     'import fixture_precedence; print(fixture_precedence.VALUE)'],
                                    check=True, text=True, capture_output=True)
            self.assertEqual(result.stdout.strip(), 'review')
            imports = subprocess.run([str(python), '-B', str(probe), 'verify-review-imports'],
                                     check=True, text=True, capture_output=True)
            self.assertEqual(imports.stdout.strip(), 'typesafe-sdk 0.7.1')
            shutil.rmtree(review_sdk)
            missing_import = subprocess.run([str(python), '-B', str(probe), 'verify-review-imports'],
                                            text=True, capture_output=True)
            self.assertNotEqual(missing_import.returncode, 0)
            with self.assertRaisesRegex(ValueError, 'Python differs from Hermes'):
                write_review_paths([[0, 0], [str(hermes_site)]])

    def test_cli_works_outside_checkout_and_does_not_create_caches(self):
        import shutil
        package = self.root / 'installed/thesystem'
        shutil.copytree(ROOT / 'thesystem', package, ignore=shutil.ignore_patterns('__pycache__'))
        result = subprocess.run(
            [sys.executable, str(package / 'setup/provisioning_cli.py'), 'config-entries', str(self.config)],
            cwd=self.root, text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'compression.enabled\ttrue\nmodel.label\t"text with spaces"\n')
        self.assertFalse(list(package.rglob('__pycache__')))


class ProvisioningAdapterTests(unittest.TestCase):
    """Exercise actual shell adapters and the shipped package from an unrelated cwd."""

    def setUp(self):
        import shutil
        self.temp = tempfile.TemporaryDirectory(prefix='provisioning-adapters-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / 'workspace with spaces'
        self.workspace.mkdir()
        shutil.copytree(ROOT / 'thesystem', self.workspace / 'thesystem',
                        ignore=shutil.ignore_patterns('__pycache__'))
        self.runtime_source = self.root / 'Hermes source with spaces'
        (self.runtime_source / 'hermes_cli').mkdir(parents=True)
        (self.runtime_source / 'fixture_bootstrap.py').write_text('VALUE = True\n')
        agent = self.runtime_source / 'agent'
        agent.mkdir()
        (agent / '__init__.py').write_text('')
        (agent / 'skill_utils.py').write_text(
            "from pathlib import Path\nimport os\n"
            "def iter_skill_index_files(root, name): return Path(root).rglob(name)\n"
            "def get_project_skills_dirs(): return [Path(os.environ['TERMINAL_CWD']) / '.agents' / 'skills']\n"
            "def iter_project_skill_files(directory):\n"
            "    hidden = os.environ.get('HIDE_SKILL')\n"
            "    return (path for path in Path(directory).rglob('SKILL.md') if path.parent.name != hidden)\n"
        )
        self.harness = self.workspace / 'agents/.harness'
        self.harness.mkdir(parents=True)
        self.skills_root = self.workspace / 'agents/skills'
        for name in ('candidate', 'already', 'bundled'):
            skill = self.skills_root / name
            skill.mkdir(parents=True)
            (skill / 'SKILL.md').write_text(f'---\nname: {name}\n---\n')
        self.config = self.harness / 'canonical_config.tsv'
        self.config.write_text('compression.enabled\ttrue\nfixture.extra\t{"x": 1}\n')
        (self.harness / 'canonical_profiles.txt').write_text('default\nimplementer\nreviewer\n')
        self.toolsets = self.harness / 'required_toolsets.txt'
        self.toolsets.write_text('file\nweb\nbrowser\n')
        self.bootstrap = self.workspace / 'bootstrap-functions'
        self.bootstrap.write_text((ROOT / 'bootstrap').read_text().split('\nsteps=(', 1)[0])
        self.home = self.root / 'home'
        self.home.mkdir()
        self.hermes_home = self.home / '.hermes'
        self.hermes_home.mkdir()
        self.sentinel = self.hermes_home / 'config.yaml'
        self.sentinel.write_text('personal: untouched\n')
        self.log = self.root / 'calls.jsonl'
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        hermes = self.bin / 'hermes'
        hermes.write_text(f'''#!{sys.executable}
import json, os, pathlib, sys
home = pathlib.Path(os.environ['HERMES_HOME'])
raw = sys.argv[1:]
with open(os.environ['CALL_LOG'], 'a') as log:
    log.write(json.dumps([os.environ['HERMES_HOME'], raw]) + '\\n')
if raw == ['--print-runtime-command']:
    source = {str(self.runtime_source)!r}
    bootstrap = f"import sys, runpy; sys.path.insert(0, {{source!r}}); import fixture_bootstrap; runpy.run_module('hermes_cli.main', run_name='__main__', alter_sys=True)"
    print(json.dumps([sys.executable, '-I', '-c', bootstrap]))
else:
    args = raw
    profile = None
    if args[:1] == ['-p']:
        profile, args = args[1], args[2:]
    if args == ['profile', 'list']:
        print('default implementer reviewer')
    elif args == ['curator', 'usage', '--json']:
        print(os.environ.get('CURATOR_USAGE_JSON', json.dumps([
            {{'name': 'candidate', 'provenance': 'agent'}},
            {{'name': 'already', 'provenance': 'agent'}},
            {{'name': 'bundled', 'provenance': 'bundled'}},
        ])))
    elif len(args) == 3 and args[:2] == ['curator', 'pin']:
        target = home if profile in (None, 'default') else home / 'profiles' / profile
        sidecar = target / 'skills' / '.usage.json'
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        recorded = json.loads(sidecar.read_text()) if sidecar.exists() else {{}}
        recorded.setdefault(args[2], {{}})['pinned'] = True
        sidecar.write_text(json.dumps(recorded))
    if os.environ.get('FIXTURE_EXIT'):
        raise SystemExit(int(os.environ['FIXTURE_EXIT']))
''')
        hermes.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.home), HERMES_HOME=str(self.root / 'wrong inherited home'),
                        PATH=f"{self.bin}:{os.environ['PATH']}", CALL_LOG=str(self.log),
                        PYTHONPATH=str(self.runtime_source))

    def run_adapter(self, adapter, action, **env):
        import shlex
        if adapter == 'bootstrap':
            script = f'source {shlex.quote(str(self.bootstrap))}\n'
            commands = {'config': 'apply_canonical_config', 'tools': 'enable_required_toolsets',
                        'link': 'link_project_skills', 'skills': 'trust_repository\nverify_skills',
                        'pin': 'pin_global_skills'}
        else:
            script = (f'source {shlex.quote(str(ROOT / "install"))}\n'
                      f'HERMES_HOME_ROOT={shlex.quote(str(self.hermes_home))}\n')
            commands = {'config': 'install_system_config', 'tools': 'enable_required_toolsets',
                        'link': 'link_project_skills',
                        'skills': f"trust_repository {shlex.quote(str(self.workspace))}\nverify_skills {shlex.quote(str(self.workspace))}",
                        'pin': 'pin_global_skills'}
        script += commands[action]
        if adapter == 'install' and action in ('config', 'tools', 'link', 'pin'):
            script += ' ' + shlex.quote(str(self.workspace))
        script += "\nprintf 'READY\\n'\n"
        return subprocess.run(['bash'], input=script, cwd=self.root, env=dict(self.env, **env),
                              text=True, capture_output=True)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_both_adapters_apply_added_settings_with_distinct_profile_scopes(self):
        for adapter, profiles in [('bootstrap', ['default', 'implementer', 'reviewer']), ('install', ['master'])]:
            with self.subTest(adapter=adapter):
                self.log.unlink(missing_ok=True)
                for _ in range(2):
                    result = self.run_adapter(adapter, 'config')
                    self.assertEqual(result.returncode, 0, result.stderr)
                sets = [args for home, args in self.calls() if 'config' in args]
                self.assertEqual(len(sets), 4 * len(profiles))
                self.assertEqual({args[1] for args in sets}, set(profiles))
                self.assertTrue(all(home == str(self.hermes_home) for home, _ in self.calls()))
                self.assertTrue(any(args[-2:] == ['fixture.extra', '{"x":1}'] for args in sets))
                self.assertEqual(self.sentinel.read_text(), 'personal: untouched\n')

    def test_both_adapters_enable_added_toolsets_and_link_idempotently(self):
        for adapter in ('bootstrap', 'install'):
            with self.subTest(adapter=adapter):
                self.log.unlink(missing_ok=True)
                result = self.run_adapter(adapter, 'tools')
                self.assertEqual(result.returncode, 0, result.stderr)
                expected = ['tools', 'enable', '--platform', 'cli', 'file', 'web', 'browser']
                if adapter == 'install':
                    expected = ['-p', 'master', *expected]
                self.assertEqual(self.calls(), [[str(self.hermes_home), expected]])
                for _ in range(2):
                    result = self.run_adapter(adapter, 'link')
                    self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(os.readlink(self.workspace / '.agents/skills'), '../agents/skills')
                self.assertFalse(list((self.workspace / 'thesystem').rglob('__pycache__')))

    def test_both_adapters_trust_before_real_filtered_discovery_from_an_unrelated_cwd(self):
        for adapter in ('bootstrap', 'install'):
            with self.subTest(adapter=adapter):
                self.log.unlink(missing_ok=True)
                linked = self.run_adapter(adapter, 'link')
                self.assertEqual(linked.returncode, 0, linked.stderr)
                result = self.run_adapter(adapter, 'skills')
                self.assertEqual(result.returncode, 0, result.stderr)
                calls = self.calls()
                trust_index = next(i for i, (_, args) in enumerate(calls) if 'skills' in args and 'trust' in args)
                if adapter == 'install':
                    self.assertIn(['--print-runtime-command'], [args for _, args in calls])
                    self.assertIn('-p', calls[trust_index][1])
                    self.assertEqual(calls[trust_index][1][calls[trust_index][1].index('-p') + 1], 'master')
                else:
                    self.assertNotIn('-p', calls[trust_index][1])
                    self.assertFalse(any(args == ['--print-runtime-command'] for _, args in calls))
                self.assertEqual(calls[trust_index][0], str(self.hermes_home))
                if adapter == 'install':
                    self.assertIn('skills accepted', result.stdout)
                self.assertFalse(list((self.workspace / 'thesystem').rglob('__pycache__')))

                self.log.unlink(missing_ok=True)
                refused = self.run_adapter(adapter, 'skills', HIDE_SKILL='candidate')
                self.assertNotEqual(refused.returncode, 0)
                self.assertNotIn('READY', refused.stdout)
                self.assertIn('candidate', refused.stderr)

    def test_both_adapters_pin_from_the_correct_profile_sidecar_and_fail_closed(self):
        for adapter in ('bootstrap', 'install'):
            with self.subTest(adapter=adapter):
                self.log.unlink(missing_ok=True)
                if adapter == 'bootstrap':
                    profile_home = self.hermes_home
                else:
                    profile_home = self.hermes_home / 'profiles/master'
                    wrong_profile = self.hermes_home / 'skills'
                    wrong_profile.mkdir(parents=True, exist_ok=True)
                    (wrong_profile / '.usage.json').write_text('{malformed wrong-profile data')
                sidecar = profile_home / 'skills/.usage.json'
                sidecar.parent.mkdir(parents=True, exist_ok=True)
                sidecar.write_text(json.dumps({'already': {'pinned': True}}))
                for _ in range(2):
                    result = self.run_adapter(adapter, 'pin')
                    self.assertEqual(result.returncode, 0, result.stderr)
                pinned = [args[-1] for _, args in self.calls()
                          if len(args) >= 3 and args[-3:-1] == ['curator', 'pin']]
                self.assertEqual(pinned, ['candidate'])
                self.assertTrue(json.loads(sidecar.read_text())['candidate']['pinned'])

                self.log.unlink(missing_ok=True)
                malformed = self.run_adapter(adapter, 'pin', CURATOR_USAGE_JSON='[null]')
                self.assertNotEqual(malformed.returncode, 0)
                self.assertFalse(any(args[-3:-1] == ['curator', 'pin'] for _, args in self.calls()))
                sidecar.write_text('{malformed sidecar')
                self.log.unlink(missing_ok=True)
                malformed = self.run_adapter(adapter, 'pin')
                self.assertNotEqual(malformed.returncode, 0)
                self.assertFalse(any(args[-3:-1] == ['curator', 'pin'] for _, args in self.calls()))

    def test_both_adapters_refuse_invalid_declarations_before_mutation(self):
        self.config.write_text('valid.key\ttrue\nbad..key\ttrue\n')
        self.toolsets.write_text('file\nfile\n')
        for adapter in ('bootstrap', 'install'):
            for action in ('config', 'tools'):
                with self.subTest(adapter=adapter, action=action):
                    result = self.run_adapter(adapter, action)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn('READY', result.stdout)
                    self.assertEqual(self.calls(), [])

    def test_both_adapters_propagate_hermes_failures(self):
        for adapter in ('bootstrap', 'install'):
            for action in ('config', 'tools'):
                with self.subTest(adapter=adapter, action=action):
                    result = self.run_adapter(adapter, action, FIXTURE_EXIT='9')
                    self.assertEqual(result.returncode, 9, result.stderr)
                    self.assertNotIn('READY', result.stdout)

    def test_both_adapters_preserve_skill_link_conflicts(self):
        link = self.workspace / '.agents/skills'
        link.mkdir(parents=True)
        sentinel = link / 'keep'
        sentinel.write_text('company content')
        for adapter in ('bootstrap', 'install'):
            result = self.run_adapter(adapter, 'link')
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('READY', result.stdout)
            self.assertEqual(sentinel.read_text(), 'company content')


if __name__ == '__main__':
    unittest.main()
