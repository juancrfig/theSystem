#!/usr/bin/env python3
"""Prepare the isolated review interpreter at <workspace>/.agents/memory-review.

Idempotent; safe to rerun after a Hermes upgrade. Steps:

1. Ask the `hermes` launcher on PATH for the Python it runs on.
2. Create a virtualenv on that same Python (uv when available, else venv+pip).
3. Install requirements.txt (the pinned TypeSafe SDK) into the virtualenv.
4. Write a .pth file so the virtualenv can also import Hermes's own modules
   (tools.write_approval, hermes_cli.write_approval_commands, ...). The SDK is
   never installed into Hermes itself.

Uses only the standard library, so any python3 can run it.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
WORKSPACE = Path(__file__).resolve().parents[4]
ENVIRONMENT = WORKSPACE / ".agents" / "memory-review"
REQUIREMENTS = SKILL / "requirements.txt"
PTH_NAME = "hermes-runtime.pth"
ENTRY_MARKER = "runpy.run_module('hermes_cli.main', run_name='__main__', alter_sys=True)"
# Printed from inside Hermes's own interpreter after its normal bootstrap ran.
PROBE = (
    "import importlib.util, json, os, site, sys; "
    "spec = importlib.util.find_spec('hermes_cli'); "
    "print(json.dumps({'version': list(sys.version_info[:2]), "
    "'paths': [*site.getsitepackages(), *[p for p in sys.path if 'site-packages' in p], "
    "os.path.dirname(os.path.dirname(spec.origin))]}))"
)


class PrepareError(RuntimeError):
    pass


def hermes_runtime(launcher: str = "hermes") -> tuple[str, list[str]]:
    """Return (python, probe command) for the Hermes install behind `launcher`."""
    executable = shutil.which(launcher)
    if executable is None:
        raise PrepareError(f"`{launcher}` is not on PATH; install Hermes first.")
    # Current launchers publish their exact runtime command.
    result = subprocess.run([executable, "--print-runtime-command"], capture_output=True, text=True)
    if result.returncode == 0:
        try:
            command = json.loads(result.stdout)
        except ValueError:
            command = None
        if (isinstance(command, list) and len(command) == 4 and command[1:3] == ["-I", "-c"]
                and ENTRY_MARKER in command[3]):
            return command[0], [command[0], "-I", "-c", command[3].replace(ENTRY_MARKER, PROBE, 1)]
    # Older pip-style launchers: a `#!/abs/path/python` shebang.
    first = Path(executable).read_text(encoding="utf-8", errors="replace").splitlines()[:1]
    if first and first[0].startswith("#!/") and "python" in first[0] and not first[0].startswith("#!/usr/bin/env"):
        python = first[0][2:].split()[0]
        return python, [python, "-I", "-c", PROBE]
    raise PrepareError(f"Cannot determine Hermes's Python from launcher {executable}.")


def find_uv() -> str | None:
    """uv on PATH, else the copy Hermes bundles under ~/.hermes/tools."""
    found = shutil.which("uv")
    if found:
        return found
    bundled = sorted(glob.glob(str(Path.home() / ".hermes" / "tools" / "uv-*" / "uv")))
    return bundled[-1] if bundled and os.access(bundled[-1], os.X_OK) else None


def run(*command: str, capture: bool = False) -> str:
    result = subprocess.run(command, text=True, capture_output=capture)
    if result.returncode:
        detail = (result.stderr or result.stdout or "").strip() if capture else ""
        raise PrepareError(f"Command failed ({result.returncode}): {' '.join(command)}\n{detail}".rstrip())
    return result.stdout if capture else ""


def interpreter_facts(python: str) -> tuple[list[int], str]:
    out = run(python, "-I", "-c", "import json, sys, sysconfig; "
              "print(json.dumps([list(sys.version_info[:2]), sysconfig.get_path('purelib')]))", capture=True)
    version, purelib = json.loads(out)
    return version, purelib


def write_bridge(purelib: str, paths: list[str]) -> Path:
    unique = list(dict.fromkeys(path for path in paths if path and Path(path).is_dir()))
    target = Path(purelib) / PTH_NAME
    # addsitedir appends, so the venv's own packages keep precedence.
    target.write_text("import site; " + "; ".join(f"site.addsitedir({path!r})" for path in unique) + "\n",
                      encoding="utf-8")
    return target


def prepare(environment: Path = ENVIRONMENT, requirements: Path = REQUIREMENTS, launcher: str = "hermes") -> Path:
    hermes_python, probe = hermes_runtime(launcher)
    hermes = json.loads(run(*probe, capture=True).strip().splitlines()[-1])
    uv = find_uv()
    python = environment / "bin" / "python"

    stale = os.access(python, os.X_OK) and interpreter_facts(str(python))[0] != hermes["version"]
    if stale or not os.access(python, os.X_OK):
        environment.parent.mkdir(parents=True, exist_ok=True)
        print(f"Creating {environment} on {hermes_python}", file=sys.stderr)
        if uv:
            run(uv, "venv", "--quiet", "--clear", "--python", hermes_python, str(environment))
        else:
            run(hermes_python, "-m", "venv", "--clear", str(environment))

    if uv:
        run(uv, "pip", "install", "--quiet", "--python", str(python), "--requirements", str(requirements))
    else:
        run(str(python), "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "-r", str(requirements))

    version, purelib = interpreter_facts(str(python))
    if version != hermes["version"]:
        raise PrepareError(f"Review Python {version} differs from Hermes {hermes['version']}.")
    write_bridge(purelib, hermes["paths"])
    run(str(python), "-c", "import typesafe_sdk, tools.write_approval, hermes_cli.write_approval_commands")
    return python


def main() -> int:
    try:
        python = prepare()
    except PrepareError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Review interpreter ready: {python}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
