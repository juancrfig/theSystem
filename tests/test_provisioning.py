"""Shared setup operations; Hermes mutations are confined to fixture homes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from thesystem.setup.provisioning import (
    HermesTarget, apply_config, enable_toolsets, link_project_skills,
    read_config, read_toolsets,
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
        self.harness = self.workspace / 'agents/.harness'
        self.harness.mkdir(parents=True)
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
        hermes.write_text('''#!/usr/bin/env python3
import json, os, sys
with open(os.environ['CALL_LOG'], 'a') as log:
    log.write(json.dumps([os.environ['HERMES_HOME'], sys.argv[1:]]) + '\\n')
if sys.argv[1:] == ['profile', 'list']:
    print('default implementer reviewer')
else:
    sys.exit(int(os.environ.get('FIXTURE_EXIT', '0')))
''')
        hermes.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.home), HERMES_HOME=str(self.root / 'wrong inherited home'),
                        PATH=f"{self.bin}:{os.environ['PATH']}", CALL_LOG=str(self.log))

    def run_adapter(self, adapter, action, **env):
        import shlex
        if adapter == 'bootstrap':
            script = f'source {shlex.quote(str(self.bootstrap))}\n'
            commands = {'config': 'apply_canonical_config', 'tools': 'enable_required_toolsets',
                        'link': 'link_project_skills'}
        else:
            script = (f'source {shlex.quote(str(ROOT / "install"))}\n'
                      f'HERMES_HOME_ROOT={shlex.quote(str(self.hermes_home))}\n')
            commands = {'config': 'install_system_config', 'tools': 'enable_required_toolsets',
                        'link': 'link_project_skills'}
        script += commands[action]
        if adapter == 'install':
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
