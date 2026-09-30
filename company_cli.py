#!/usr/bin/env python3
"""Stable executable adapter for the packaged company command."""
import sys

if __name__ == "__main__":
    sys.dont_write_bytecode = True

from thesystem.cli import main
from thesystem.workspace import WorkspaceError as ProjectError


if __name__ == "__main__":
    raise SystemExit(main())
