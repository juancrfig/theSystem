"""CLI adapter for distribution ownership; services do not print output."""
import json
from pathlib import Path
import sys

from .distribution import DISTRIBUTION_PATHS
from .managed_files import clean, snapshot


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["paths"]:
        print("\n".join(DISTRIBUTION_PATHS))
    elif len(args) == 3 and args[0] == "snapshot":
        count = snapshot(Path(args[1]).resolve(), Path(args[2]).resolve())
        print(f"tracked {count} managed files")
    elif len(args) == 2 and args[0] == "clean":
        print(json.dumps(clean(Path(args[1]).resolve()), sort_keys=True))
    else:
        raise SystemExit("usage: installer_lifecycle.py snapshot SOURCE TARGET | clean TARGET | paths")
    return 0
