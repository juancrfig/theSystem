"""Registered project and source-clone operations for one bound workspace."""
from __future__ import annotations

from contextlib import contextmanager
import errno
import fcntl
import json
import os
from pathlib import Path
import stat
import tempfile

from thesystem.errors import CodedError
from thesystem.setup.distribution import MANAGED_ROOTS


PROJECT_INFRASTRUCTURE = ("wiki", "agents", "tickets")
RESERVED_WORKSPACE_NAMES = {*MANAGED_ROOTS, ".git", ".thesystem", ".agents", "tests", "tickets", "wiki"}


class WorkspaceError(CodedError):
    pass


class Workspace:
    def __init__(self, root: str | Path):
        try:
            self.root = Path(root).expanduser().resolve(strict=True)
        except OSError as error:
            raise WorkspaceError("WORKSPACE_NOT_BOUND", f"workspace is not an existing directory: {root}") from error
        if not self.root.is_dir():
            raise WorkspaceError("WORKSPACE_NOT_BOUND", f"workspace is not an existing directory: {root}")

    def register_project(self, value: str | Path) -> dict:
        project = self._existing_directory(value, "PROJECT_NOT_DIRECTORY")
        if project == self.root:
            raise WorkspaceError("PROJECT_IS_WORKSPACE", "workspace itself is not a project")
        if not self._inside(project, self.root):
            raise WorkspaceError("PROJECT_OUTSIDE_WORKSPACE", "project must be strictly inside the company workspace")
        relative = project.relative_to(self.root)
        if relative.parts[0] in RESERVED_WORKSPACE_NAMES:
            raise WorkspaceError("PROJECT_RESERVED_PATH", "project path is reserved workspace infrastructure")
        if self._lstat(project / ".git") is not None:
            raise WorkspaceError("PROJECT_IS_SOURCE_CLONE", "project is a source clone (.git exists)")
        for name in PROJECT_INFRASTRUCTURE:
            path = project / name
            info = self._lstat(path)
            if info is not None and (path.is_symlink() or not path.is_dir()):
                raise WorkspaceError("PROJECT_INFRASTRUCTURE_INVALID", f"project infrastructure path is not a real directory: {name}")

        created: list[Path] = []
        try:
            with self._locked_registry(create=True) as registry_dir:
                registry = registry_dir / "projects.json"
                entries = self._read_registry(registry, "projects")
                project_value = str(project)
                matches = [entry for entry in entries if entry["path"] == project_value]
                if not matches:
                    for entry in entries:
                        registered = Path(entry["path"])
                        if registered != project and (self._inside(project, registered) or self._inside(registered, project)):
                            raise WorkspaceError("PROJECT_OVERLAPS_REGISTERED", "project overlaps a registered project")
                try:
                    for name in PROJECT_INFRASTRUCTURE:
                        path = project / name
                        if self._lstat(path) is None:
                            path.mkdir()
                            created.append(path)
                        if path.is_symlink() or not path.is_dir():
                            raise OSError(errno.ELOOP, f"invalid project infrastructure path: {path}")
                    if not matches:
                        entries.append({"name": project.name, "path": project_value})
                        self._write_registry(registry, entries)
                except Exception:
                    self._remove_created_directories(created)
                    raise
        except WorkspaceError:
            self._remove_created_directories(created)
            raise
        except (OSError, ValueError) as error:
            self._remove_created_directories(created)
            raise WorkspaceError("PROJECT_SETUP_FAILED", f"cannot register project: {error}") from error
        return {"project": str(project), "idempotent": bool(matches)}

    def register_source_clone(self, project_value: str | Path, clone_value: str | Path) -> dict:
        project = self.require_registered_project(project_value)
        clone = self._existing_directory(clone_value, "SOURCE_CLONE_INVALID")
        if self._lstat(clone / ".git") is None:
            raise WorkspaceError("SOURCE_CLONE_INVALID", "source clone must be an existing Git working tree")
        if clone == project or not self._inside(clone, project):
            raise WorkspaceError("SOURCE_CLONE_OUTSIDE_PROJECT", "source clone must be strictly inside its registered project")
        try:
            with self._locked_registry(create=False) as registry_dir:
                project_entries = self._read_registry(registry_dir / "projects.json", "projects")
                project_paths = {entry["path"] for entry in project_entries}
                registry = registry_dir / "source-clones.json"
                entries = self._read_clone_registry(registry, project_paths)
                record = {"project": str(project), "path": str(clone)}
                already = record in entries
                if not already:
                    entries.append(record)
                    self._write_registry(registry, entries)
        except WorkspaceError:
            raise
        except (OSError, ValueError) as error:
            raise WorkspaceError("SOURCE_CLONE_REGISTRY_INVALID", str(error)) from error
        return {"project": str(project), "source_clone": str(clone), "idempotent": already}

    def require_registered_project(self, value: str | Path) -> Path:
        project = self._existing_directory(value, "PROJECT_NOT_REGISTERED")
        if not self._inside(project, self.root) or project == self.root:
            raise WorkspaceError("PROJECT_OUTSIDE_WORKSPACE", "project must be strictly inside the company workspace")
        try:
            with self._locked_registry(create=False) as registry_dir:
                entries = self._read_registry(registry_dir / "projects.json", "projects")
        except WorkspaceError:
            raise
        except (OSError, ValueError) as error:
            raise WorkspaceError("REGISTRY_INVALID", str(error)) from error
        if str(project) not in {entry["path"] for entry in entries}:
            raise WorkspaceError("PROJECT_NOT_REGISTERED", "project must be registered before this operation")
        return project

    @contextmanager
    def locked_project(self, value: str | Path):
        project = self.require_registered_project(value)
        with self._locked_registry(create=False) as registry_dir:
            entries = self._read_registry(registry_dir / "projects.json", "projects")
            if str(project) not in {entry["path"] for entry in entries}:
                raise WorkspaceError("PROJECT_NOT_REGISTERED", "project must be registered before this operation")
            yield project

    @staticmethod
    def atomic_write(path: Path, payload: bytes) -> None:
        descriptor, temporary = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    def require_registered_clone(self, project_value: str | Path, clone_value: str | Path) -> Path:
        project = self.require_registered_project(project_value)
        clone = self._existing_directory(clone_value, "SOURCE_CLONE_NOT_REGISTERED")
        try:
            with self._locked_registry(create=False) as registry_dir:
                projects = self._read_registry(registry_dir / "projects.json", "projects")
                entries = self._read_clone_registry(registry_dir / "source-clones.json",
                                                    {entry["path"] for entry in projects})
        except WorkspaceError:
            raise
        except (OSError, ValueError) as error:
            raise WorkspaceError("SOURCE_CLONE_REGISTRY_INVALID", str(error)) from error
        if {"project": str(project), "path": str(clone)} not in entries:
            raise WorkspaceError("SOURCE_CLONE_NOT_REGISTERED", "register the source clone for this project before creating a task")
        return clone

    @contextmanager
    def _locked_registry(self, create: bool):
        directory = self.root / ".thesystem"
        info = self._lstat(directory)
        if info is None:
            if not create:
                raise WorkspaceError("PROJECT_NOT_REGISTERED", "project registry does not exist")
            try:
                directory.mkdir()
            except FileExistsError:
                pass
            if directory.is_symlink() or not directory.is_dir():
                raise WorkspaceError("REGISTRY_INVALID", "registry directory is not a real directory")
        elif directory.is_symlink() or not directory.is_dir():
            raise WorkspaceError("REGISTRY_INVALID", "registry directory is not a real directory")
        lock = directory / "projects.lock"
        lock_info = self._lstat(lock)
        if lock_info is not None and (lock.is_symlink() or not lock.is_file()):
            raise WorkspaceError("REGISTRY_INVALID", "registry lock is not a regular file")
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(lock, flags, 0o600)
        except OSError as error:
            if error.errno in (errno.ELOOP, errno.EMLINK):
                raise WorkspaceError("REGISTRY_INVALID", "registry lock is not a regular file") from error
            raise
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise WorkspaceError("REGISTRY_INVALID", "registry lock is not a regular file")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield directory
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def _read_registry(self, path: Path, label: str) -> list[dict]:
        if self._lstat(path) is None:
            return []
        if path.is_symlink() or not path.is_file():
            raise WorkspaceError("REGISTRY_INVALID", f"{label} registry is not a regular file")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise WorkspaceError("REGISTRY_INVALID", f"cannot read {label} registry: {error}") from error
        if not isinstance(value, list):
            raise WorkspaceError("REGISTRY_INVALID", f"{label} registry is not a list")
        entries = []
        for item in value:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                raise WorkspaceError("REGISTRY_INVALID", f"{label} registry contains an invalid entry")
            raw_path = Path(item["path"])
            if not raw_path.is_absolute():
                raise WorkspaceError("REGISTRY_INVALID", f"{label} registry contains a relative path")
            try:
                registered = raw_path.resolve(strict=True)
            except OSError as error:
                raise WorkspaceError("REGISTRY_INVALID", f"registry contains an unreadable path: {raw_path}") from error
            if not self._inside(registered, self.root) or registered == self.root or not registered.is_dir():
                raise WorkspaceError("REGISTRY_INVALID", "registry contains a path outside the workspace")
            entries.append({**item, "path": str(registered)})
        return entries

    def _read_clone_registry(self, path: Path, registered_projects: set[str]) -> list[dict]:
        try:
            entries = self._read_registry(path, "source clones")
        except WorkspaceError as error:
            raise WorkspaceError("SOURCE_CLONE_REGISTRY_INVALID", str(error)) from error
        validated = []
        seen = set()
        for entry in entries:
            project_value = entry.get("project")
            if not isinstance(project_value, str):
                raise WorkspaceError("SOURCE_CLONE_REGISTRY_INVALID", "source clone registry contains an invalid project")
            try:
                project = Path(project_value).resolve(strict=True)
                clone = Path(entry["path"]).resolve(strict=True)
            except OSError as error:
                raise WorkspaceError("SOURCE_CLONE_REGISTRY_INVALID", "source clone registry contains an unreadable path") from error
            record = {"project": str(project), "path": str(clone)}
            identity = (record["project"], record["path"])
            if (str(project) not in registered_projects or project == clone
                    or not self._inside(clone, project) or not clone.is_dir()
                    or self._lstat(clone / ".git") is None or identity in seen):
                raise WorkspaceError("SOURCE_CLONE_REGISTRY_INVALID", "source clone registry contains an invalid entry")
            seen.add(identity)
            validated.append(record)
        return validated

    @staticmethod
    def _write_registry(path: Path, value: list[dict]) -> None:
        payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
        Workspace.atomic_write(path, payload)

    def _existing_directory(self, value: str | Path, code: str) -> Path:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as error:
            raise WorkspaceError(code, f"directory does not exist: {value}") from error
        if not resolved.is_dir():
            raise WorkspaceError(code, f"path is not a directory: {value}")
        return resolved

    @staticmethod
    def _lstat(path: Path):
        try:
            return path.lstat()
        except FileNotFoundError:
            return None

    @staticmethod
    def _inside(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    @staticmethod
    def _remove_created_directories(paths: list[Path]) -> None:
        for path in reversed(paths):
            try:
                path.rmdir()
            except OSError:
                pass
