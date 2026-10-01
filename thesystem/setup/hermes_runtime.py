"""Hermes runtime adapters for checkout launchers and published installer commands.

These adapters preserve two existing discovery contracts. Provisioning callers
need only an interpreter for uv, script invocation, and review dependency paths.
"""
import ast
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess

from thesystem.setup.provisioning import HermesTarget

PROBE = Path(__file__).with_name("runtime_probe.py")
ENTRY_MARKER = "runpy.run_module('hermes_cli.main', run_name='__main__', alter_sys=True)"


def _executable_python(path: str) -> Path:
    if not path or not os.access(path, os.X_OK) or not Path(path).is_file():
        raise ValueError(f"Hermes runtime is not executable: {path}")
    return Path(path)


@dataclass(frozen=True)
class LauncherRuntime:
    python: Path
    home: Path

    @classmethod
    def discover(cls, target: HermesTarget):
        launcher = shutil.which(target.executable)
        if launcher is None:
            raise ValueError(f"Hermes launcher is unavailable: {target.executable}")
        lines = Path(launcher).read_text(encoding="utf-8").splitlines()
        candidate = ""
        if lines and lines[0].startswith("#!/") and not lines[0].startswith("#!/usr/bin/env "):
            candidate = lines[0][2:]
        else:
            for line in lines:
                if line.startswith('exec "'):
                    candidate = line[len('exec "'):].split('"', 1)[0]
                    break
        try:
            python = _executable_python(candidate)
        except ValueError as exc:
            raise ValueError(f"Unable to resolve Hermes Python runtime from: {launcher}") from exc
        return cls(python, target.profile_home)

    def environment(self, overrides=None):
        env = dict(os.environ, HERMES_HOME=str(self.home), PYTHONDONTWRITEBYTECODE="1")
        if overrides:
            env.update(overrides)
        return env

    def run_file(self, script: Path, *arguments: str, capture=False, environment=None):
        return subprocess.run([str(self.python), "-B", str(script), *arguments], check=True,
                              capture_output=capture, text=True, env=self.environment(environment))

    def review_paths(self) -> tuple[list[int], list[str]]:
        result = subprocess.run([str(self.python), "-I", "-B", str(PROBE), "interpreter-paths"],
                                check=True, capture_output=True, text=True, env=self.environment())
        version, paths = json.loads(result.stdout)
        return version, paths


@dataclass(frozen=True)
class PublishedRuntime(LauncherRuntime):
    bootstrap: str

    @classmethod
    def discover(cls, target: HermesTarget):
        # Runtime publication is launcher-global, not a profile command.
        result = subprocess.run([target.executable, "--print-runtime-command"], check=True,
                                capture_output=True, text=True,
                                env=dict(os.environ, HERMES_HOME=str(target.home)))
        try:
            command = json.loads(result.stdout)
        except ValueError as exc:
            raise ValueError("Hermes returned an invalid runtime command") from exc
        if (not isinstance(command, list) or len(command) != 4
                or not all(isinstance(part, str) for part in command)
                or command[1:3] != ["-I", "-c"]):
            raise ValueError("Hermes returned an invalid runtime command")
        if ENTRY_MARKER not in command[3]:
            raise ValueError("Hermes runtime command does not bootstrap hermes_cli.main")
        return cls(_executable_python(command[0]), target.profile_home, command[3])

    def run_file(self, script: Path, *arguments: str, capture=False, environment=None):
        invocation = "sys.argv = sys.argv[1:]; runpy.run_path(sys.argv[0], run_name='__main__')"
        code = "import sys; sys.dont_write_bytecode = True; " + self.bootstrap.replace(ENTRY_MARKER, invocation, 1)
        return subprocess.run([str(self.python), "-I", "-c", code, str(script), *arguments],
                              check=True, capture_output=capture, text=True,
                              env=self.environment(environment))

    def review_paths(self) -> tuple[list[int], list[str]]:
        version, paths = super().review_paths()
        dependencies = self.run_file(PROBE, "dependency-paths", capture=True)
        paths.extend(json.loads(dependencies.stdout))
        roots = []
        for node in ast.walk(ast.parse(self.bootstrap)):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "insert" and isinstance(node.func.value, ast.Attribute)
                    and node.func.value.attr == "path" and len(node.args) >= 2
                    and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str)):
                candidate = Path(node.args[1].value)
                if candidate.is_absolute() and (candidate / "hermes_cli").is_dir():
                    roots.append(str(candidate))
        if len(roots) != 1:
            raise ValueError("Hermes runtime did not publish one source root")
        return version, [*paths, *roots]
