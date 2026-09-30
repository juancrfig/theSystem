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
    read_config, read_toolsets,
)


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
    args = parser.parse_args(argv)
    try:
        if args.command == "config-entries":
            for key, value in read_config(args.source):
                print(f"{key}\t{value}")
        elif args.command == "toolset-names":
            print("\n".join(read_toolsets(args.source)))
        elif args.command == "link-skills":
            link_project_skills(args.workspace, args.link)
        else:
            target = HermesTarget(args.home, args.profile)
            operation = apply_config if args.command == "apply-config" else enable_toolsets
            operation(args.source, target)
    except subprocess.CalledProcessError as exc:
        # Preserve failures rather than hiding them behind a successful adapter.
        return exc.returncode if exc.returncode > 0 else 128 - exc.returncode
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
