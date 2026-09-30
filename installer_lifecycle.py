#!/usr/bin/env python3
"""Compatibility entry point for distribution ownership commands."""
import sys

if __name__ == "__main__":
    sys.dont_write_bytecode = True

from thesystem.setup.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
