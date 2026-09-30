"""Internal shell adapter for shared provisioning; runnable from installed paths."""
import sys

# A file-path invocation must not depend on cwd, installation, or PYTHONPATH.
# Prevent unowned bytecode from surviving rollback to a pre-package release.
sys.dont_write_bytecode = True
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse
import subprocess
from thesystem.setup.provisioning import (
    HermesTarget, apply_config, enable_toolsets, link_project_skills,
    read_config, read_toolsets, pin_global_skills, provision_memory_review,
    trust_repository, verify_project_skills,
)
from thesystem.setup.hermes_runtime import LauncherRuntime, PublishedRuntime


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("config-entries", "toolset-names", "apply-config", "enable-toolsets"):
        command = commands.add_parser(name)
        command.add_argument("source", type=Path)
        if name in ("apply-config", "enable-toolsets"):
            command.add_argument("home", type=Path)
            command.add_argument("--profile")
    link = commands.add_parser("link-skills")
    link.add_argument("workspace", type=Path)
    link.add_argument("--link", type=Path)
    for name in ("memory-review", "trust-skills", "verify-skills", "pin-skills"):
        command = commands.add_parser(name)
        command.add_argument("workspace", type=Path)
        command.add_argument("home", type=Path)
        command.add_argument("--profile")
        if name in ("memory-review", "verify-skills"):
            command.add_argument("--runtime", choices=("launcher", "published"), required=True)
        if name == "memory-review":
            command.add_argument("--environment", type=Path)
            command.add_argument("--requirements", type=Path)
        if name == "pin-skills":
            command.add_argument("--count-file", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "config-entries":
            for key, value in read_config(args.source):
                print(f"{key}\t{value}")
        elif args.command == "toolset-names":
            print("\n".join(read_toolsets(args.source)))
        elif args.command == "link-skills":
            link_project_skills(args.workspace, args.link)
        elif args.command in ("apply-config", "enable-toolsets"):
            target = HermesTarget(args.home, args.profile)
            operation = apply_config if args.command == "apply-config" else enable_toolsets
            operation(args.source, target)
        else:
            target = HermesTarget(args.home, args.profile)
            if args.command == "trust-skills":
                trust_repository(args.workspace, target)
            elif args.command == "pin-skills":
                count = pin_global_skills(args.workspace, target)
                if args.count_file:
                    args.count_file.write_text(f"{count}\n", encoding="utf-8")
            else:
                runtime = {"launcher": LauncherRuntime, "published": PublishedRuntime}[args.runtime].discover(target)
                if args.command == "verify-skills":
                    print(f"{verify_project_skills(args.workspace, runtime)} skills accepted")
                else:
                    environment = args.environment or args.workspace / ".agents" / "memory-review"
                    requirements = args.requirements or args.workspace / "agents" / "skills" / "memory-request-review" / "requirements.txt"
                    provision_memory_review(environment, requirements, runtime)
    except subprocess.CalledProcessError as exc:
        # Preserve failures rather than hiding them behind a successful adapter.
        return exc.returncode if exc.returncode > 0 else 128 - exc.returncode
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
