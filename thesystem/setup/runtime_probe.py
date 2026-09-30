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
    from agent.skill_utils import get_project_skills_dirs, iter_project_skill_files, iter_skill_index_files

    skill_root = root / ".agents" / "skills"
    expected = {str(path.parent.relative_to(skill_root)) for path in iter_skill_index_files(skill_root, "SKILL.md")}
    accepted = {
        str(path.parent.relative_to(directory))
        for directory in get_project_skills_dirs()
        for path in iter_project_skill_files(directory)
    }
    missing = expected - accepted
    if missing:
        raise ValueError("Project skills unavailable after Hermes security filtering: " + ", ".join(sorted(missing)))
    return len(accepted)


def write_review_paths(metadata):
    version, paths = metadata
    if version != list(sys.version_info[:2]):
        raise ValueError("Review environment Python differs from Hermes; recreate .agents/memory-review and rerun provisioning.")
    target = Path(sysconfig.get_path("purelib")) / "hermes-runtime.pth"
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
