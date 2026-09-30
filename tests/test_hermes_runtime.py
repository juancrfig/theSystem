"""Runtime adapter contracts using real subprocesses, not user profiles."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from thesystem.setup.hermes_runtime import LauncherRuntime, PublishedRuntime
from thesystem.setup.provisioning import HermesTarget

ROOT = Path(__file__).resolve().parents[1]


class HermesRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hermes-runtime-adapters-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.launcher = self.root / 'hermes launcher'
        self.home = self.root / 'isolated home'
        self.target = HermesTarget(self.home, executable=str(self.launcher))
        self.script = self.root / 'script café with spaces.py'
        self.script.write_text('import json, os, sys; print(json.dumps([sys.argv[1:], os.environ["HERMES_HOME"], os.environ.get("TERMINAL_CWD"), "fixture_bootstrap" in sys.modules, __file__, __name__])); raise SystemExit(int(os.environ.get("SCRIPT_EXIT", "0")))')
        self.source = self.root / 'Hermes source with spaces'
        (self.source / 'hermes_cli').mkdir(parents=True)
        (self.source / 'fixture_bootstrap.py').write_text('VALUE = True\n')

    def publish(self, command=None, exit_code=0):
        if command is None:
            # Producer shape: Hermes be84a141, hermes_cli/_launchers.py,
            # --print-runtime-command: [python, -I, -c, bootstrap code].
            command = [sys.executable, '-I', '-c', f"import sys, runpy; sys.path.insert(0, {str(self.source)!r}); import fixture_bootstrap; runpy.run_module('hermes_cli.main', run_name='__main__', alter_sys=True)"]
        self.launcher.write_text(f'#!{sys.executable}\nimport json, sys\nprint({json.dumps(command)!r})\nraise SystemExit({exit_code})\n')
        self.launcher.chmod(0o755)

    def test_launcher_shebang_and_quoted_exec_paths(self):
        for text in (f'#!{sys.executable}\n', f'#!/usr/bin/env bash\nexec "{sys.executable}" "$@"\n'):
            with self.subTest(text=text):
                self.launcher.write_text(text)
                self.launcher.chmod(0o755)
                runtime = LauncherRuntime.discover(self.target)
                self.assertEqual(runtime.python, Path(sys.executable))
                result = runtime.run_file(self.script, 'space argument', 'semi;colon', 'naïve 🧪', capture=True,
                                          environment={'TERMINAL_CWD': str(self.root)})
                self.assertEqual(json.loads(result.stdout), [['space argument', 'semi;colon', 'naïve 🧪'], str(self.home), str(self.root), False, str(self.script), '__main__'])

    def test_published_runtime_preserves_bootstrap_and_arguments(self):
        self.publish()
        runtime = PublishedRuntime.discover(self.target)
        self.assertEqual(runtime.python, Path(sys.executable))
        result = runtime.run_file(self.script, 'space argument', 'semi;colon', 'naïve 🧪', capture=True,
                                  environment={'TERMINAL_CWD': str(self.root)})
        self.assertEqual(json.loads(result.stdout), [['space argument', 'semi;colon', 'naïve 🧪'], str(self.home), str(self.root), True, str(self.script), '__main__'])
        self.assertFalse(list(self.source.rglob('__pycache__')))

    def test_unavailable_launcher_interpreter_is_refused(self):
        for text in ('#!/usr/bin/env python3\n', '#!/missing/python\n', '#!/usr/bin/env bash\nexec "not executable"\n'):
            self.launcher.write_text(text)
            self.launcher.chmod(0o755)
            with self.assertRaises(ValueError):
                LauncherRuntime.discover(self.target)

    def test_invalid_publication_is_refused_before_execution(self):
        for command in ({'python': sys.executable}, [], [sys.executable],
                        [sys.executable, '-I', '-c', 'no entry marker'],
                        ['/missing/python', '-I', '-c', "runpy.run_module('hermes_cli.main', run_name='__main__', alter_sys=True)"],
                        [sys.executable, '-I', '-c', 3]):
            self.publish(command)
            with self.assertRaises(ValueError):
                PublishedRuntime.discover(self.target)
        self.launcher.write_text(f'#!{sys.executable}\nprint("invalid JSON")\n')
        with self.assertRaises(ValueError):
            PublishedRuntime.discover(self.target)

    def test_publication_and_script_failures_propagate(self):
        self.publish(exit_code=7)
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            PublishedRuntime.discover(self.target)
        self.assertEqual(caught.exception.returncode, 7)
        self.publish()
        with patch.dict(os.environ, SCRIPT_EXIT='9'):
            for runtime in (LauncherRuntime(Path(sys.executable), self.home), PublishedRuntime.discover(self.target)):
                with self.assertRaises(subprocess.CalledProcessError) as caught:
                    runtime.run_file(self.script, capture=True)
                self.assertEqual(caught.exception.returncode, 9)

    def test_review_paths_preserve_adapter_specific_sources(self):
        self.publish()
        launcher = LauncherRuntime(Path(sys.executable), self.home)
        published = PublishedRuntime.discover(self.target)
        version, paths = launcher.review_paths()
        self.assertEqual(version, list(sys.version_info[:2]))
        self.assertNotIn(str(self.source), paths)
        pub_version, pub_paths = published.review_paths()
        self.assertEqual(pub_version, version)
        self.assertTrue(set(paths).issubset(pub_paths))
        self.assertIn(str(self.source), pub_paths)

    def test_published_runtime_requires_one_source_root_for_review(self):
        self.publish([sys.executable, '-I', '-c', "import runpy; runpy.run_module('hermes_cli.main', run_name='__main__', alter_sys=True)"])
        with self.assertRaises(ValueError):
            PublishedRuntime.discover(self.target).review_paths()


if __name__ == '__main__':
    unittest.main()
