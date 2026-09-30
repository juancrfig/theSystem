"""Shared declaration-driven workspace provisioning, without workflow policy.

Callers own profile creation, runtime acquisition, and presentation. Hermes is
invoked only through its CLI, with an explicit home and optional profile; these
operations never edit its configuration or credentials directly.
"""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess


def read_config(source: Path) -> list[tuple[str, str]]:
    """Validate the whole TSV declaration before returning CLI-ready JSON values."""
    source = Path(source)
    text = source.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"{source} is empty")
    entries = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "\t" not in raw:
            raise ValueError(f"{source}:{line_no}: expected <key>\\t<json-value>")
        key, value = raw.split("\t", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"{source}:{line_no}: empty key")
        if any(not segment or any(ch.isspace() for ch in segment) for segment in key.split(".")):
            raise ValueError(f"{source}:{line_no}: invalid key segment in {key!r}")
        try:
            parsed = json.loads(value.strip())
        except ValueError as exc:
            raise ValueError(f"{source}:{line_no}: invalid JSON value: {exc}") from exc
        entries.append((key, json.dumps(parsed, separators=(",", ":"))))
    if not entries:
        raise ValueError(f"Canonical configuration contains no settings: {source}")
    return entries


def read_toolsets(source: Path) -> list[str]:
    """Preserve declaration order and reject invalid/duplicate toolset names."""
    source = Path(source)
    names = []
    # Bash read historically preserved CR and surrounding whitespace in names.
    for name in source.read_bytes().decode("utf-8").split("\n"):
        if not name or name.startswith("#"):
            continue
        if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
            raise ValueError(f"Invalid required toolset name: {name}")
        if name in names:
            raise ValueError(f"Duplicate toolset name: {name}")
        names.append(name)
    if not names:
        raise ValueError(f"Required toolset manifest is empty: {source}")
    return names


@dataclass(frozen=True)
class HermesTarget:
    home: Path
    profile: str | None = None
    executable: str = "hermes"

    @property
    def profile_home(self) -> Path:
        if self.profile in (None, "default"):
            return Path(self.home)
        return Path(self.home) / "profiles" / self.profile

    def run(self, *arguments: str, quiet: bool = False, capture: bool = False):
        """Inherit runtime environment but never inherit an implicit Hermes home."""
        command = [self.executable]
        if self.profile is not None:
            command.extend(["-p", self.profile])
        command.extend(arguments)
        env = dict(os.environ, HERMES_HOME=str(self.home))
        return subprocess.run(command, env=env, check=True, text=True,
                              stdout=subprocess.PIPE if capture else subprocess.DEVNULL if quiet else None)


def apply_config(source: Path, target: HermesTarget) -> int:
    entries = read_config(source)
    for key, value in entries:
        target.run("config", "set", "--force", key, value, quiet=True)
    return len(entries)


def enable_toolsets(source: Path, target: HermesTarget) -> int:
    names = read_toolsets(source)
    target.run("tools", "enable", "--platform", "cli", *names)
    return len(names)


def link_project_skills(workspace: Path, link: Path | None = None) -> bool:
    """Create the existing relative link; refuse conflicts, including broken links."""
    link = Path(link) if link is not None else Path(workspace) / ".agents" / "skills"
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink():
        existing = os.readlink(link)
        if existing != "../agents/skills":
            raise ValueError(f"Refusing to replace project skill link {link} -> {existing}")
        return False
    if link.exists():
        raise ValueError(f"Refusing to replace non-symlink project skill directory: {link}")
    link.symlink_to("../agents/skills")
    return True


def provision_memory_review(environment: Path, requirements: Path, runtime, uv: str = "uv") -> Path:
    python = Path(environment) / "bin" / "python"
    if not os.access(python, os.X_OK):
        subprocess.run([uv, "venv", "--python", str(runtime.python), str(environment)], check=True)
    subprocess.run([uv, "pip", "install", "--python", str(python), "--requirements", str(requirements)], check=True)
    metadata = runtime.review_paths()
    probe = Path(__file__).with_name("runtime_probe.py")
    # Bridge dependencies into the isolated environment, never the SDK into Hermes.
    subprocess.run([str(python), "-B", str(probe), "write-review-paths", json.dumps(metadata)],
                   check=True, env=runtime.environment())
    subprocess.run([uv, "pip", "check", "--python", str(python)], check=True)
    subprocess.run([str(python), "-B", str(probe), "verify-review-imports"], check=True,
                   env=runtime.environment())
    return python


def trust_repository(workspace: Path, target: HermesTarget) -> None:
    target.run("skills", "trust", str(workspace), quiet=True)


def verify_project_skills(workspace: Path, runtime) -> int:
    probe = Path(__file__).with_name("runtime_probe.py")
    result = runtime.run_file(probe, "verify-skills", str(workspace), capture=True,
                              environment={"TERMINAL_CWD": str(workspace)})
    count = json.loads(result.stdout)
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("Hermes returned an invalid verified skill count")
    return count


def skills_to_pin(workspace: Path, profile_home: Path, usage) -> list[str]:
    if not isinstance(usage, list):
        raise ValueError("Expected a list of curator skills")
    known = {}
    for entry in usage:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str) or not entry["name"]:
            raise ValueError("Invalid curator skill entry")
        known[entry["name"]] = entry
    root = Path(workspace) / "agents" / "skills"
    manifests = list(root.rglob("SKILL.md"))
    if not manifests:
        raise ValueError(f"No global skills found in {root}")
    sidecar = Path(profile_home) / "skills" / ".usage.json"
    recorded = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.exists() else {}
    if not isinstance(recorded, dict) or any(not isinstance(entry, dict) for entry in recorded.values()):
        raise ValueError(f"Invalid curator usage sidecar: {sidecar}")
    return [name for name in sorted({path.parent.name for path in manifests})
            if known.get(name, {}).get("provenance") not in ("bundled", "hub")
            and not recorded.get(name, {}).get("pinned", False)]


def pin_global_skills(workspace: Path, target: HermesTarget) -> int:
    usage = target.run("curator", "usage", "--json", capture=True)
    names = skills_to_pin(workspace, target.profile_home, json.loads(usage.stdout))
    for name in names:
        target.run("curator", "pin", name)
    return len(names)
