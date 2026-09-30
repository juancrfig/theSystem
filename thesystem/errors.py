"""Coded domain errors shared by workspace, CLI, and orchestration services."""


class CodedError(Exception):
    def __init__(self, code: str, message: str | None):
        super().__init__(message)
        self.code = code
