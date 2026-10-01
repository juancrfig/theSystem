"""Standalone probes executed by Hermes or the isolated review interpreter.

Keep this file independent of theSystem imports: neither interpreter is
required to have the distribution installed in its site-packages.
"""
import json
from pathlib import Path
import site
import sys
import sysconfig

sys.dont_write_bytecode = True


def interpreter_paths():
    return [list(sys.version_info[:2]), site.getsitepackages()]


def dependency_paths():
    return [path for path in sys.path if "site-packages" in path]


def verify_skills(root):
    from agent.skill_utils import (get_project_skills_dirs, is_project_root_trusted,
                                   iter_project_skill_files, iter_skill_index_files)

    skill_root = root / ".agents" / "skills"
    expected = {str(path.parent.relative_to(skill_root)) for path in iter_skill_index_files(skill_root, "SKILL.md")}
    if not expected:
        raise ValueError(f"No canonical project skills were found in {skill_root}")
    discovered = {directory.resolve() for directory in get_project_skills_dirs()}
    trusted = is_project_root_trusted(root)
    if skill_root.resolve() not in discovered:
        raise ValueError(f"Hermes did not discover the workspace project-skill directory: {skill_root}")
    if not trusted:
        raise ValueError(f"Hermes does not trust this workspace in the selected profile: {root}")
    accepted = {str(path.parent.relative_to(skill_root)) for path in iter_project_skill_files(skill_root)}
    missing = expected - accepted
    if missing:
        raise ValueError("Project skills unavailable after Hermes security filtering: " + ", ".join(sorted(missing)))
    if not accepted:
        raise ValueError("Hermes accepted no usable project skills")
    return {"trusted": trusted, "discovered": True, "expected": len(expected), "accepted": len(accepted)}


def diagnose_workspace(root, expected_settings, required_toolsets):
    from agent.skill_utils import (get_project_skills_dirs, is_project_root_trusted,
                                   iter_project_skill_files, iter_skill_index_files)
    from hermes_cli.config import load_config_readonly
    from hermes_cli.tools_config import _get_platform_tools

    root = Path(root).resolve()
    skill_root = root / ".agents" / "skills"
    expected = {str(path.parent.relative_to(skill_root)) for path in iter_skill_index_files(skill_root, "SKILL.md")}
    discovered_dirs = {directory.resolve() for directory in get_project_skills_dirs()}
    discovered = skill_root.resolve() in discovered_dirs
    accepted = {str(path.parent.relative_to(skill_root)) for path in iter_project_skill_files(skill_root)} if discovered else set()
    config = load_config_readonly()

    def get_path(data, dotted):
        value = data
        for key in dotted.split("."):
            if not isinstance(value, dict) or key not in value:
                return None
            value = value[key]
        return value

    drift = [key for key, value in expected_settings if get_path(config, key) != json.loads(value)]
    try:
        enabled_toolsets = _get_platform_tools(config, "cli")
    except Exception:
        enabled_toolsets = None
    missing_toolsets = sorted(set(required_toolsets) - set(enabled_toolsets or [])) if isinstance(enabled_toolsets, set) else list(required_toolsets)
    return {
        "trusted": is_project_root_trusted(root),
        "discovered": discovered,
        "expected_skills": sorted(expected),
        "accepted_skills": sorted(accepted),
        "missing_skills": sorted(expected - accepted),
        "settings_drift": sorted(drift),
        "required_toolsets_missing": missing_toolsets,
        "toolsets_verifiable": isinstance(enabled_toolsets, set),
    }


def write_review_paths(metadata, purelib=None):
    version, paths = metadata
    if version != list(sys.version_info[:2]):
        raise ValueError("Review environment Python differs from Hermes; recreate .agents/memory-review and rerun provisioning.")
    target = (Path(purelib) if purelib is not None else Path(sysconfig.get_path("purelib"))) / "hermes-runtime.pth"
    # Local review packages must take precedence over Hermes dependencies.
    target.write_text("import site; " + "; ".join(f"site.addsitedir({path!r})" for path in paths) + "\n", encoding="utf-8")


def verify_review_imports():
    from typesafe_sdk import Noul, TypeSafeClient
    from tools import write_approval
    from hermes_cli.write_approval_commands import _apply_one
    from importlib.metadata import version

    return "typesafe-sdk " + version("typesafe-sdk")


def main():
    operation = sys.argv[1]
    if operation == "interpreter-paths":
        print(json.dumps(interpreter_paths()))
    elif operation == "dependency-paths":
        print(json.dumps(dependency_paths()))
    elif operation == "verify-skills":
        print(json.dumps(verify_skills(Path(sys.argv[2]))))
    elif operation == "diagnose-workspace":
        print(json.dumps(diagnose_workspace(Path(sys.argv[2]), json.loads(sys.argv[3]), json.loads(sys.argv[4]))))
    elif operation == "write-review-paths":
        write_review_paths(json.loads(sys.argv[2]))
    elif operation == "verify-review-imports":
        print(verify_review_imports())
    else:
        raise ValueError(f"Unknown runtime probe: {operation}")


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
