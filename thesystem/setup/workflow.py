"""Shared setup, diagnostics, and ownership-aware distribution lifecycle."""
from __future__ import annotations

import json
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import sys
import urllib.request

from .distribution import DISTRIBUTION_PATHS
from .managed_files import clean, identity, manifest_path, read_manifest, record_manifest
from .provisioning import (HermesTarget, apply_config, enable_toolsets, link_project_skills,
                           pin_global_skills, provision_memory_review, read_config,
                           read_toolsets, trust_repository, validate_project_skill_links,
                           verify_project_skills)
from .hermes_runtime import PublishedRuntime


class LifecycleError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _source_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _validate_workspace(workspace: Path) -> Path:
    unexpanded = Path(workspace).expanduser()
    if unexpanded.is_symlink():
        raise LifecycleError("WORKSPACE_INVALID", f"workspace path cannot be a symlink: {unexpanded}")
    path = unexpanded.resolve()
    if path == Path(path.anchor):
        raise LifecycleError("WORKSPACE_UNSAFE", "filesystem root cannot be a workspace")
    if path.exists() and (path.is_symlink() or not path.is_dir()):
        raise LifecycleError("WORKSPACE_INVALID", f"workspace is not a real directory: {path}")
    return path


def _experimental(item: Path) -> bool:
    manifest = item / "SKILL.md" if item.is_dir() else item
    if not (manifest.name == "SKILL.md" or "/rules/" in manifest.as_posix()):
        return False
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return False
    if not lines or lines[0] != "---":
        return False
    try:
        end = lines.index("---", 1)
    except ValueError:
        return False
    return any(re.fullmatch(r"experimental:\s*true\s*(?:#.*)?", line) for line in lines[1:end])


def _copy_item(source: Path, target: Path, old_entries: dict, managed: dict,
               source_root: Path, target_root: Path, replace: bool, experimental: bool) -> None:
    if source.name in {".git", "__pycache__", ".gitignore"} or source.suffix == ".pyc":
        return
    if not experimental and _experimental(source):
        return
    if source.is_symlink():
        resolved = source.resolve(strict=True)
        if not resolved.is_relative_to(source_root):
            raise LifecycleError("SOURCE_UNSAFE", f"distribution symlink escapes source: {source}")
        if not target.exists() and not target.is_symlink():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(os.readlink(source))
            managed[str(target.relative_to(target_root))] = identity(target)
        else:
            relative = str(target.relative_to(target_root))
            expected = old_entries.get(relative)
            if expected is not None and identity(target) == expected:
                managed[relative] = expected
        return
    if target.is_symlink():
        raise LifecycleError("TARGET_CONFLICT", f"refusing to copy through symlink: {target}")
    if source.is_dir():
        target.mkdir(parents=True, exist_ok=True)
        for child in source.iterdir():
            _copy_item(child, target / child.name, old_entries, managed, source_root, target_root, replace, experimental)
        return
    relative = str(target.relative_to(target_root))
    expected = old_entries.get(relative)
    target_owned_unchanged = expected is not None and identity(target) == expected
    if not target.exists() or (replace and target_owned_unchanged):
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        managed[relative] = identity(target)
    elif target_owned_unchanged:
        managed[relative] = expected
    elif expected is not None and identity(target) is not None:
        # Keep the original ownership fingerprint so cleanup can report this user edit.
        managed[relative] = expected


def _copy_distribution(source: Path, target: Path, replace: bool = False, experimental: bool = False) -> None:
    _check_workspace_state(target)
    target.mkdir(parents=True, exist_ok=True)
    resolved_target = target.resolve()
    resolved_source = source.resolve()
    if resolved_target == resolved_source or resolved_target.is_relative_to(resolved_source):
        raise LifecycleError("WORKSPACE_IN_SOURCE", "workspace cannot be inside the distribution source")
    old_manifest = manifest_path(target)
    if old_manifest.exists() or old_manifest.is_symlink():
        old_entries = read_manifest(target, old_manifest)["entries"]
    else:
        old_entries = {}
    managed = {}
    for relative, expected in old_entries.items():
        parts = Path(relative).parts
        if (parts and parts[0] in DISTRIBUTION_PATHS and ".." not in parts
                and not Path(relative).is_absolute() and identity(target / relative) is not None):
            managed[relative] = expected
    for name in DISTRIBUTION_PATHS:
        original = source / name
        if original.exists() or original.is_symlink():
            _copy_item(original, target / name, old_entries, managed, resolved_source, resolved_target, replace, experimental)
    record_manifest(target, managed)


def _snapshot_manifest(archive: Path, sidecar: Path) -> dict:
    data = read_manifest(archive.parent.parent.parent, sidecar)
    entries = data["entries"]
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        seen = set()
        for member in members:
            name = member.name
            item = Path(name)
            if (not name or item.is_absolute() or ".." in item.parts or "." in item.parts
                    or name not in entries or name in seen or not (member.isfile() or member.issym())):
                raise LifecycleError("SNAPSHOT_INVALID", f"snapshot contains unowned or unsafe content: {name}")
            seen.add(name)
        if seen != set(entries):
            raise LifecycleError("SNAPSHOT_INVALID", "snapshot contents do not match its ownership manifest")
        with tempfile.TemporaryDirectory(prefix="thesystem-snapshot-check-", dir=archive.parent) as staging:
            bundle.extractall(staging, filter="data")
            for name, expected in entries.items():
                if identity(Path(staging) / name) != expected:
                    raise LifecycleError("SNAPSHOT_INVALID", f"snapshot ownership fingerprint does not match: {name}")
    return data


def _has_git_root(workspace: Path) -> bool:
    try:
        result = subprocess.run(["git", "-C", str(workspace), "rev-parse", "--show-toplevel"],
                               check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError):
        return False
    return Path(result.stdout.strip()).resolve() == workspace.resolve()


def _skill_preflight(workspace: Path) -> None:
    skills = workspace / "agents" / "skills"
    if not skills.is_dir() or skills.is_symlink():
        raise LifecycleError("SKILLS_MISSING", f"canonical skill directory is missing or unsafe: {skills}")
    if not any(skills.rglob("SKILL.md")):
        raise LifecycleError("SKILLS_EMPTY", f"canonical skill set is empty: {skills}")
    try:
        validate_project_skill_links(workspace)
    except ValueError as error:
        raise LifecycleError("SKILL_LINK_CONFLICT", str(error)) from error


def _configuration_sources(workspace: Path) -> tuple[Path, Path]:
    harness = workspace / "agents/.harness"
    if not harness.exists() and not harness.is_symlink():
        # Configure existing company workspaces without installing over their guidance.
        harness = _source_root() / "agents/.harness"
    if harness.is_symlink() or not harness.is_dir():
        raise LifecycleError("CONFIGURATION_SOURCE_INVALID", f"canonical declarations are missing or unsafe: {harness}")
    return harness / "canonical_config.tsv", harness / "required_toolsets.txt"


def _seed_missing_context_files(source: Path, workspace: Path) -> list[str]:
    """Seed missing baseline workspace context files per ADR 0002 without overwriting existing files."""
    seeded = []
    context_files = ("GLOSSARY.md", "AGENTS.md")
    for name in context_files:
        target = workspace / name
        if not target.exists() and not target.is_symlink():
            candidate = source / name
            if candidate.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(candidate, target)
                seeded.append(name)
    agents_dir = workspace / "agents"
    if not agents_dir.exists() and not agents_dir.is_symlink():
        source_agents = source / "agents"
        if source_agents.is_dir():
            shutil.copytree(source_agents, agents_dir)
            seeded.append("agents")
    return seeded


def _selected_profile(profile: str | None = None) -> str:
    if profile is None:
        inherited = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")).expanduser().resolve()
        profile = inherited.name if inherited.parent.name == "profiles" else "master"
    if not re.fullmatch(r"[a-z][a-z0-9]*", profile):
        raise LifecycleError("PROFILE_INVALID", f"invalid Hermes profile name: {profile}")
    return profile


def _hermes_target(profile: str | None = None) -> HermesTarget:
    profile = _selected_profile(profile)
    inherited = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")).expanduser().resolve()
    if inherited.parent.name == "profiles":
        root = inherited.parent.parent
    else:
        root = inherited
    return HermesTarget(root, profile)


def _install_script(url: str, interpreter: str, label: str) -> None:
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            script = response.read()
    except OSError as error:
        raise LifecycleError(f"{label.upper()}_DOWNLOAD_FAILED", f"could not download {label} installer: {error}") from error
    if not script or b"<!doctype html" in script[:1024].lower() or b"<html" in script[:1024].lower():
        raise LifecycleError(f"{label.upper()}_INSTALLER_INVALID", f"downloaded {label} installer is not a script")
    subprocess.run([interpreter], input=script, check=True)


def _acquire_runtime() -> None:
    if shutil.which("hermes") is None:
        _install_script("https://hermes-agent.nousresearch.com/install.sh", "bash", "hermes")
        local_bin = str(Path.home() / ".local/bin")
        os.environ["PATH"] = local_bin + os.pathsep + os.environ.get("PATH", "")
    try:
        subprocess.run(["hermes", "--version"], check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise LifecycleError("HERMES_UNAVAILABLE", f"Hermes installation did not verify: {error}") from error
    if shutil.which("uv") is None:
        _install_script("https://astral.sh/uv/install.sh", "sh", "uv")
        local_bin = str(Path.home() / ".local/bin")
        os.environ["PATH"] = local_bin + os.pathsep + os.environ.get("PATH", "")
    if shutil.which("uv") is None:
        raise LifecycleError("UV_UNAVAILABLE", "uv installation did not produce an executable")


def _ensure_profile(target: HermesTarget, non_interactive: bool = True) -> None:
    profile = target.profile
    if profile is None:
        raise LifecycleError("PROFILE_REQUIRED", "a Hermes profile must be selected")
    if target.profile_home.is_dir() and (target.profile_home / "config.yaml").is_file():
        return
    environment = dict(os.environ, HERMES_HOME=str(target.home))
    if not target.profile_home.exists():
        try:
            subprocess.run([target.executable, "profile", "create", profile, "--no-skills"],
                           env=environment, check=True, capture_output=True)
        except (OSError, subprocess.CalledProcessError):
            target.profile_home.mkdir(parents=True, exist_ok=True)
    config_file = target.profile_home / "config.yaml"
    if not config_file.is_file():
        config_file.write_text("{}\n", encoding="utf-8")


def _configure_hermes(workspace: Path, profile: str | None, development: bool, non_interactive: bool) -> None:
    if not _has_git_root(workspace):
        raise LifecycleError("HERMES_PROJECT_DISCOVERY_UNSUPPORTED",
            "Hermes project skills are discovered only inside a Git root. This workspace is not its own Git root; no profile-wide skill fallback or git init was performed.")
    _skill_preflight(workspace)
    target = _hermes_target(profile)
    if shutil.which(target.executable) is None:
        raise LifecycleError("HERMES_UNAVAILABLE", "Hermes is not installed; configure does not install runtime dependencies")
    settings, toolsets = _configuration_sources(workspace)
    requirements = workspace / "agents/skills/memory-request-review/requirements.txt"
    if not requirements.is_file():
        raise LifecycleError("REVIEW_REQUIREMENTS_MISSING", f"memory-review dependency declaration is missing: {requirements}")
    read_config(settings)
    read_toolsets(toolsets)
    if shutil.which("uv") is None:
        raise LifecycleError("UV_UNAVAILABLE", "uv is required to prepare the isolated memory-review environment")
    runtime = PublishedRuntime.discover(target)
    profile_home = target.profile_home
    if not profile_home.is_dir() or not (profile_home / "config.yaml").is_file():
        _ensure_profile(target, non_interactive)
    if development and (not (workspace / ".git").exists() or not (workspace / ".githooks/pre-commit").is_file()):
        raise LifecycleError("DEVELOPMENT_CHECKOUT_REQUIRED", "--development requires a Git checkout with the managed pre-commit hook")
    try:
        link_project_skills(workspace)
        trust_repository(workspace, target)
        apply_config(settings, target)
        enable_toolsets(toolsets, target)
        provision_memory_review(workspace / ".agents" / "memory-review",
                                requirements, runtime)
        accepted = verify_project_skills(workspace, runtime)
        if accepted <= 0:
            raise LifecycleError("SKILLS_UNAVAILABLE", "Hermes accepted no project skills")
        pin_global_skills(workspace, target)
        if development:
            subprocess.run(["git", "-C", str(workspace), "config", "core.hooksPath", ".githooks"], check=True)
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "").strip()
        suffix = f": {detail}" if detail else ""
        raise LifecycleError("HERMES_CONFIGURATION_FAILED", f"Hermes configuration step failed with exit status {error.returncode}{suffix}") from error


def configure(workspace: Path, runtime: str = "hermes", profile: str | None = None, development: bool = False,
              non_interactive: bool = False) -> None:
    workspace = _validate_workspace(workspace)
    if not workspace.is_dir():
        raise LifecycleError("WORKSPACE_MISSING", f"workspace does not exist: {workspace}")
    if runtime not in {"hermes", "none"}:
        raise LifecycleError("RUNTIME_INVALID", f"unsupported runtime: {runtime}")
    selected_profile = _selected_profile(profile)
    _check_workspace_state(workspace)
    _seed_missing_context_files(_source_root(), workspace)
    if runtime == "hermes":
        _configure_hermes(workspace, selected_profile, development, non_interactive)
    _persist_selection(workspace, runtime, selected_profile)


def _check_workspace_state(workspace: Path) -> Path:
    marker = workspace / ".thesystem"
    if marker.is_symlink() or (marker.exists() and not marker.is_dir()):
        raise LifecycleError("WORKSPACE_STATE_UNSAFE", f"workspace state path is not a real directory: {marker}")
    for name in ("runtime", "profile"):
        state_file = marker / name
        if state_file.is_symlink() or (state_file.exists() and not state_file.is_file()):
            raise LifecycleError("WORKSPACE_STATE_UNSAFE", f"workspace state file is unsafe: {state_file}")
    return marker


def _persist_selection(workspace: Path, runtime: str, profile: str) -> None:
    marker = _check_workspace_state(workspace)
    marker.mkdir(exist_ok=True)
    (marker / "runtime").write_text(runtime + "\n", encoding="utf-8")
    (marker / "profile").write_text(profile + "\n", encoding="utf-8")


def _diagnostic(status: str, message: str) -> dict[str, str]:
    return {"status": status, "message": message}


def _diagnose_hermes_workspace(workspace: Path, runtime: PublishedRuntime) -> dict:
    settings_source, toolsets_source = _configuration_sources(workspace)
    settings = read_config(settings_source)
    toolsets = read_toolsets(toolsets_source)
    probe = Path(__file__).with_name("runtime_probe.py")
    result = runtime.run_file(probe, "diagnose-workspace", str(workspace), json.dumps(settings),
                              json.dumps(toolsets), capture=True,
                              environment={"TERMINAL_CWD": str(workspace)})
    report = None
    for line in reversed(result.stdout.splitlines()):
        try:
            candidate = json.loads(line)
        except ValueError:
            continue
        if isinstance(candidate, dict):
            report = candidate
            break
    if report is None:
        raise ValueError("Hermes returned an invalid diagnostics report")
    return report


def doctor(workspace: Path, runtime: str | None = None, profile: str | None = None) -> int:
    workspace = _validate_workspace(workspace)
    marker = workspace / ".thesystem"
    recorded_runtime = marker / "runtime"
    recorded_profile = marker / "profile"
    state_safe = (not marker.is_symlink() and (not marker.exists() or marker.is_dir())
                  and not recorded_runtime.is_symlink() and not recorded_profile.is_symlink())
    selection = {}
    if runtime is None:
        if state_safe and recorded_runtime.is_file():
            runtime = recorded_runtime.read_text(encoding="utf-8").strip()
            selection["runtime"] = "workspace-marker"
        else:
            runtime = "hermes"
            selection["runtime"] = "default"
    if profile is None and runtime == "hermes":
        if state_safe and recorded_profile.is_file():
            profile = recorded_profile.read_text(encoding="utf-8").strip()
            selection["profile"] = "workspace-marker"
        else:
            profile = _selected_profile()
            selection["profile"] = "active-hermes-home" if Path(os.environ.get("HERMES_HOME", "")).parent.name == "profiles" else "legacy-default"
    development_checkout = workspace == _source_root()
    distribution_present = manifest_path(workspace).is_file() and state_safe
    configured_workspace = (state_safe and recorded_runtime.is_file()
                            and (runtime == "none" or (runtime == "hermes" and recorded_profile.is_file())))
    checks = {
        "workspace": _diagnostic("pass" if workspace.is_dir() else "fail", str(workspace)),
        "workspace_state": _diagnostic("pass" if state_safe else "fail", "workspace state paths are safe" if state_safe else "unsafe .thesystem state path"),
        "distribution": _diagnostic("pass" if distribution_present or development_checkout or configured_workspace else "fail",
                                     "ownership manifest present" if distribution_present
                                     else "workspace configuration (installer ownership manifest not applicable)" if configured_workspace
                                     else "source checkout (installer ownership manifest not applicable)" if development_checkout
                                     else "distribution ownership manifest missing"),
    }
    if runtime not in {"hermes", "none"}:
        checks["runtime"] = _diagnostic("fail", f"unsupported runtime: {runtime}")
    elif runtime == "none":
        checks["runtime"] = _diagnostic("pass", "infrastructure-only runtime selected")
    else:
        skills = workspace / "agents/skills"
        checks["canonical_skills"] = _diagnostic(
            "pass" if skills.is_dir() and not skills.is_symlink() and any(skills.rglob("SKILL.md")) else "fail",
            "canonical project skills available" if skills.is_dir() and any(skills.rglob("SKILL.md")) else f"missing or empty canonical skills: {skills}")
        git_root = _has_git_root(workspace)
        checks["git_project_discovery"] = _diagnostic(
            "pass" if git_root else "fail",
            "workspace is a Hermes project-discovery root" if git_root else "Hermes project skills require this workspace to be its own Git root")
        link = workspace / ".agents/skills"
        try:
            missing_links = validate_project_skill_links(workspace)
            correct_link = link.exists() and not missing_links
            link_message = "canonical skill discovery links are present" if correct_link else "canonical skill discovery links are missing"
        except ValueError as error:
            correct_link = False
            link_message = str(error)
        checks["skill_link"] = _diagnostic("pass" if correct_link else "fail",
            link_message)
        target = _hermes_target(profile)
        available = shutil.which(target.executable) is not None
        checks["hermes_runtime"] = _diagnostic("pass" if available else "fail",
            f"Hermes executable available: {target.executable}" if available else f"Hermes executable not found: {target.executable}")
        config_path = target.profile_home / "config.yaml"
        checks["profile_config"] = _diagnostic("pass" if config_path.is_file() else "fail",
            f"selected profile configuration present: {target.profile_home}" if config_path.is_file() else f"selected profile configuration missing: {target.profile_home}")
        if available and config_path.is_file():
            try:
                runtime_adapter = PublishedRuntime.discover(target)
                report = _diagnose_hermes_workspace(workspace, runtime_adapter)
                trusted = report.get("trusted") is True
                checks["repository_trust"] = _diagnostic("pass" if trusted else "fail",
                    "workspace trust is present in the selected profile" if trusted else "workspace is not trusted in the selected Hermes profile")
                discovered = report.get("discovered") is True
                checks["skill_discovery"] = _diagnostic("pass" if discovered else "fail",
                    "workspace project skills are discovered" if discovered else "Hermes did not discover this workspace's project-skill directory")
                expected_skills = report.get("expected_skills", [])
                accepted_skills = report.get("accepted_skills", [])
                missing_skills = report.get("missing_skills", [])
                accepted = (isinstance(expected_skills, list) and bool(expected_skills)
                            and isinstance(accepted_skills, list) and bool(accepted_skills)
                            and isinstance(missing_skills, list) and not missing_skills)
                checks["accepted_project_skills"] = _diagnostic("pass" if accepted else "fail",
                    f"selected profile accepted {len(accepted_skills)} of {len(expected_skills)} project skills" if accepted
                    else "one or more canonical project skills are empty, undiscovered, quarantined, or unavailable"
                    + (": " + ", ".join(missing_skills) if isinstance(missing_skills, list) and missing_skills else ""))
                drift = report.get("settings_drift", [])
                checks["canonical_settings"] = _diagnostic("fail" if drift else "pass",
                    "canonical settings match" if not drift else "settings drift: " + ", ".join(drift))
                missing = report.get("required_toolsets_missing", [])
                if report.get("toolsets_verifiable") is True:
                    checks["required_toolsets"] = _diagnostic("fail" if missing else "pass",
                        "required toolsets enabled" if not missing else "required toolsets missing: " + ", ".join(missing))
                else:
                    checks["required_toolsets"] = _diagnostic("unverified", "Hermes did not expose CLI toolsets in the read-only config response")
                requirements = workspace / "agents/skills/memory-request-review/requirements.txt"
                review_python = workspace / ".agents/memory-review/bin/python"
                checks["memory_review_environment"] = _diagnostic(
                    "pass" if requirements.is_file() and os.access(review_python, os.X_OK) else "fail",
                    "isolated review interpreter exists" if requirements.is_file() and os.access(review_python, os.X_OK) else "isolated review interpreter or requirements declaration missing")
                try:
                    probe_result = subprocess.run([str(review_python), "-B", str(Path(__file__).with_name("runtime_probe.py")), "verify-review-imports"],
                        check=True, capture_output=True, text=True, env=runtime_adapter.environment())
                    checks["memory_review_imports"] = _diagnostic("pass", probe_result.stdout.strip())
                except (OSError, subprocess.CalledProcessError) as error:
                    checks["memory_review_imports"] = _diagnostic("fail", f"review dependencies are unavailable: {error}")
            except (OSError, ValueError, subprocess.CalledProcessError, LifecycleError) as error:
                detail = error.stderr.strip() if isinstance(error, subprocess.CalledProcessError) and error.stderr else str(error)
                checks["profile_readiness"] = _diagnostic("fail", f"could not inspect selected profile: {detail}")
        else:
            checks["profile_readiness"] = _diagnostic("unverified", "profile checks require an installed Hermes runtime and configured profile")
    ready = all(result["status"] == "pass" for result in checks.values())
    print(json.dumps({"workspace": str(workspace), "profile": _selected_profile(profile) if runtime == "hermes" else None,
                      "selection": selection,
                      "checks": checks, "ready": ready}, sort_keys=True))
    return 0 if ready else 1


def install(workspace: Path, runtime: str = "hermes", profile: str | None = None, company: str | None = None,
            experimental: bool = False, non_interactive: bool = False) -> None:
    source = _source_root()
    workspace = _validate_workspace(workspace)
    _check_workspace_state(workspace)
    selected_profile = _selected_profile(profile)
    if company and not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", company):
        raise LifecycleError("COMPANY_INVALID", "company alias must match [A-Za-z][A-Za-z0-9]*")
    _check_global_command()
    if company:
        _check_alias(company, workspace)
    if runtime == "hermes" and not _has_git_root(workspace):
        raise LifecycleError("HERMES_PROJECT_DISCOVERY_UNSUPPORTED",
            "Hermes project skills require a Git root. Installation stopped before copying distribution files; do not initialize user workspaces automatically.")
    if runtime == "hermes":
        target = _hermes_target(selected_profile)
        if non_interactive and (not target.profile_home.is_dir() or not (target.profile_home / "config.yaml").is_file()):
            raise LifecycleError("PROFILE_SETUP_REQUIRED", f"Hermes profile {profile!r} is missing; non-interactive installation will not create credentials")
        harness = source / "agents/.harness"
        read_config(harness / "canonical_config.tsv")
        read_toolsets(harness / "required_toolsets.txt")
        if not (source / "agents/skills/memory-request-review/requirements.txt").is_file():
            raise LifecycleError("REVIEW_REQUIREMENTS_MISSING", "memory-review dependency declaration is missing from the distribution")
        _acquire_runtime()
    _copy_distribution(source, workspace, experimental=experimental)
    configure(workspace, runtime, selected_profile, non_interactive=non_interactive)
    _install_global_command(source, experimental)
    if company:
        _install_alias(company, workspace)


def _check_alias(name: str, workspace: Path) -> None:
    directory = Path.home() / ".local/bin"
    target = directory / name
    found = shutil.which(name)
    if found and Path(found).resolve() != target.resolve():
        raise LifecycleError("ALIAS_CONFLICT", f"refusing to shadow existing command on PATH: {found}")
    if target.exists() or target.is_symlink():
        if target.is_file() and not target.is_symlink():
            expected = (f"#!/usr/bin/env bash\nexport THESYSTEM_WORKSPACE={str(workspace)!r}\n"
                        f"exec {str(Path.home() / '.local/share/thesystem/bin/thesystem')!r} \"$@\"\n")
            if target.read_text(encoding="utf-8", errors="replace") == expected:
                return
        raise LifecycleError("ALIAS_CONFLICT", f"refusing to overwrite existing command: {target}")


def _install_alias(name: str, workspace: Path) -> None:
    _check_alias(name, workspace)
    directory = Path.home() / ".local/bin"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / name
    command = str(Path.home() / ".local/share/thesystem/bin/thesystem")
    target.write_text(f"#!/usr/bin/env bash\nexport THESYSTEM_WORKSPACE={str(workspace)!r}\nexec {command!r} \"$@\"\n", encoding="utf-8")
    target.chmod(0o755)


def _check_global_command() -> None:
    directory = Path.home() / ".local/share/thesystem"
    launcher = Path.home() / ".local/bin/thesystem"
    expected = f"#!/usr/bin/env bash\nexec {str(directory / 'bin/thesystem')!r} \"$@\"\n"
    found = shutil.which("thesystem")
    if found and Path(found).resolve() != launcher.resolve():
        raise LifecycleError("LAUNCHER_CONFLICT", f"refusing to shadow existing command on PATH: {found}")
    if launcher.exists() or launcher.is_symlink():
        if launcher.is_symlink() or not launcher.is_file() or launcher.read_text(encoding="utf-8", errors="replace") != expected:
            raise LifecycleError("LAUNCHER_CONFLICT", f"refusing to overwrite unrelated command: {launcher}")


def _install_global_command(source: Path, experimental: bool = False) -> None:
    _check_global_command()
    directory = Path.home() / ".local/share/thesystem"
    launcher = Path.home() / ".local/bin/thesystem"
    expected = f"#!/usr/bin/env bash\nexec {str(directory / 'bin/thesystem')!r} \"$@\"\n"
    directory.mkdir(parents=True, exist_ok=True)
    _copy_distribution(source, directory, replace=launcher.exists(), experimental=experimental)
    launcher.parent.mkdir(parents=True, exist_ok=True)
    temporary = launcher.with_name(launcher.name + ".tmp")
    temporary.write_text(expected, encoding="utf-8")
    temporary.chmod(0o755)
    os.replace(temporary, launcher)


def install_workspace(workspace: Path, company: str | None = None, runtime: str = "hermes",
                      profile: str | None = None, experimental: bool = False,
                      non_interactive: bool = True) -> int:
    source = _source_root()
    workspace = _validate_workspace(workspace)
    _check_workspace_state(workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    if not company:
        derived = re.sub(r"[^A-Za-z0-9]", "", workspace.name)
        if derived and re.match(r"[A-Za-z]", derived):
            company = derived.lower()
        else:
            company = "company"
    elif not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", company):
        raise LifecycleError("COMPANY_INVALID", f"company alias must match [A-Za-z][A-Za-z0-9]*, got: {company!r}")

    # 1. Hard prerequisite: ensure the global CLI is installed
    _install_global_command(source, experimental=experimental)

    # 2. Context seeding per ADR 0002 (never overwrite existing)
    _seed_missing_context_files(source, workspace)

    # 3. Company alias installation
    if company:
        _install_alias(company, workspace)

    # 4. Workspace wiring (Protocol 1: configure)
    selected_profile = _selected_profile(profile)
    configure(workspace, runtime=runtime, profile=selected_profile,
              non_interactive=non_interactive)

    # 5. Doctor readiness report
    return doctor(workspace, runtime=runtime, profile=selected_profile)


def _remove_owned_legacy_entrypoints(workspace: Path) -> None:
    try:
        entries = json.loads(manifest_path(workspace).read_text(encoding="utf-8"))["entries"]
    except (OSError, ValueError, KeyError, TypeError):
        return
    for name in ("install", "bootstrap"):
        path = workspace / name
        if name in entries and identity(path) is not None and entries[name] == identity(path):
            path.unlink()


def upgrade(workspace: Path, experimental: bool = False, non_interactive: bool = False,
            runtime: str | None = None, profile: str | None = None) -> None:
    workspace = _validate_workspace(workspace)
    if not workspace.is_dir():
        raise LifecycleError("WORKSPACE_MISSING", f"workspace does not exist: {workspace}")
    _check_workspace_state(workspace)
    ownership = manifest_path(workspace)
    if not ownership.is_file() or ownership.is_symlink():
        raise LifecycleError("DISTRIBUTION_NOT_MANAGED", "upgrade requires a valid ownership manifest; configure or install this workspace first")
    ownership_data = read_manifest(workspace, ownership)
    state = workspace / ".thesystem"
    runtime_file, profile_file = state / "runtime", state / "profile"
    recorded_runtime = runtime_file.read_text(encoding="utf-8").strip() if runtime_file.is_file() else None
    recorded_profile = profile_file.read_text(encoding="utf-8").strip() if profile_file.is_file() else None
    selected_runtime = runtime or recorded_runtime
    if selected_runtime not in {"hermes", "none"}:
        raise LifecycleError("RUNTIME_SELECTION_REQUIRED", "legacy workspace has no valid runtime marker; rerun upgrade with --runtime hermes|none")
    selected_profile = profile or recorded_profile
    if selected_runtime == "hermes" and selected_profile is None:
        inherited = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")).expanduser().resolve()
        if inherited.parent.name == "profiles":
            selected_profile = inherited.name
        else:
            raise LifecycleError("PROFILE_SELECTION_REQUIRED", "legacy Hermes workspace has no profile marker; rerun upgrade with --profile NAME")
    selected_profile = _selected_profile(selected_profile)
    source = _source_root()
    backup_dir = workspace / ".thesystem/backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = str(len(list(backup_dir.glob("*.tar.gz"))) + 1)
    archive = backup_dir / f"{stamp}.tar.gz"
    legacy = ("install", "bootstrap")
    snapshot_entries = {name: expected for name, expected in ownership_data["entries"].items()
                        if identity(workspace / name) == expected}
    if snapshot_entries:
        with tarfile.open(archive, "w:gz") as bundle:
            for name in snapshot_entries:
                bundle.add(workspace / name, arcname=name, recursive=False)
        (backup_dir / f"{stamp}.managed.json").write_text(
            json.dumps({"version": 1, "entries": snapshot_entries}, sort_keys=True, indent=2) + "\n",
            encoding="utf-8")
    _remove_owned_legacy_entrypoints(workspace)
    _copy_distribution(source, workspace, replace=True, experimental=experimental)
    configure(workspace, selected_runtime, selected_profile, non_interactive=non_interactive)


def rollback(workspace: Path) -> dict:
    workspace = _validate_workspace(workspace)
    candidates = sorted((workspace / ".thesystem/backups").glob("*.tar.gz"), key=lambda path: int(path.stem) if path.stem.isdigit() else -1)
    if not candidates:
        raise LifecycleError("ROLLBACK_UNAVAILABLE", f"no valid software snapshots found in {workspace}")
    archive = candidates[-1]
    manifest = archive.parent / f"{archive.name.removesuffix('.tar.gz')}.managed.json"
    if not manifest.is_file() or manifest.is_symlink():
        raise LifecycleError("SNAPSHOT_INVALID", "snapshot ownership manifest is missing or unsafe")
    snapshot_data = _snapshot_manifest(archive, manifest)
    with tarfile.open(archive, "r:gz") as bundle, tempfile.TemporaryDirectory(prefix="thesystem-rollback-", dir=archive.parent) as staging:
        bundle.extractall(staging, filter="data")
        staged = Path(staging)
        clean(workspace)
        for relative in snapshot_data["entries"]:
            path = staged / relative
            destination = workspace / relative
            if destination.exists() or destination.is_symlink():
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            if path.is_symlink():
                destination.symlink_to(os.readlink(path))
            else:
                shutil.copy2(path, destination)
        record_manifest(workspace, snapshot_data["entries"])
    output = io.StringIO()
    state = workspace / ".thesystem"
    saved_runtime = state / "runtime"
    saved_profile = state / "profile"
    with redirect_stdout(output):
        result = doctor(workspace,
                        saved_runtime.read_text(encoding="utf-8").strip() if saved_runtime.is_file() and not saved_runtime.is_symlink() else None,
                        saved_profile.read_text(encoding="utf-8").strip() if saved_profile.is_file() and not saved_profile.is_symlink() else None)
    return {"readiness": json.loads(output.getvalue()), "readiness_exit_code": result}


def uninstall(workspace: Path) -> dict:
    workspace = _validate_workspace(workspace)
    result = clean(workspace)
    alias_dir = Path.home() / ".local/bin"
    for alias in alias_dir.iterdir() if alias_dir.is_dir() else ():
        if alias.is_file() and not alias.is_symlink():
            text = alias.read_text(encoding="utf-8", errors="replace")
            expected = (f"#!/usr/bin/env bash\nexport THESYSTEM_WORKSPACE={str(workspace)!r}\n"
                        f"exec {str(Path.home() / '.local/share/thesystem/bin/thesystem')!r} \"$@\"\n")
            if text == expected:
                alias.unlink()
    state = workspace / ".thesystem"
    for name in ("runtime", "profile"):
        (state / name).unlink(missing_ok=True)
    return {"removed": result["removed"], "retained_modified": result["retained_modified"]}
