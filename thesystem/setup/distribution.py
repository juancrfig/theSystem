"""Canonical distribution inputs and legacy managed-file roots."""

DISTRIBUTION_PATHS = (
    "AGENTS.md", "GLOSSARY.md", "GLOSSARY-MAP.md", "MANUAL.md", "README.md",
    "the_system_orchestrator.py", "thesystem", "bin", "agents", ".githooks", "docs",
)

# Cleanup must still recognize files recorded by older installations.
MANAGED_ROOTS = (*DISTRIBUTION_PATHS, "CONTEXT.md", "bootstrap", "install")
