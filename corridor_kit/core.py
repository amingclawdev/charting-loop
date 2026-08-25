"""Portable, task-neutral mechanics for constructing a Corridor.

The helpers in this module deliberately know nothing about a benchmark, a domain,
or a governance service.  They provide byte identity, safe JSON handling, public
world inventory, and optional command capture.  None of the functions is an
authorization or workflow gate.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


KIT_VERSION = "0.8.2"
MANIFEST_SCHEMA = "charting-loop/corridor-kit-tree-manifest/v1"
WORLD_INVENTORY_SCHEMA = "charting-loop/corridor-kit-world-inventory/v1"
CAPTURE_SCHEMA = "charting-loop/corridor-kit-command-capture/v1"
MAX_JSON_BYTES = 5 * 1024 * 1024
MAX_RULE_CANDIDATE_DECODE_BYTES = 16 * 1024 * 1024
MAX_MANIFEST_FILE_BYTES = 256 * 1024 * 1024
TREE_EXCLUSION_POLICY = ("**/__pycache__/**", "**/*.pyc", "**/*.pyo")


class CorridorKitError(ValueError):
    """Raised when portable Corridor-kit input violates a safety invariant."""


def _reject_large_integers(value: Any) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        if value.bit_length() > 4096:
            raise CorridorKitError("integer exceeds 4096 bits")
        return
    if isinstance(value, dict):
        for key, child in value.items():
            _reject_large_integers(key)
            _reject_large_integers(child)
    elif isinstance(value, list):
        for child in value:
            _reject_large_integers(child)


def canonical_json_bytes(value: Any) -> bytes:
    """Return the stable JSON encoding used for all kit identities."""

    _reject_large_integers(value)
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise CorridorKitError(f"value is not canonical JSON: {exc}") from exc


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise CorridorKitError(f"duplicate JSON key: {key}")
        value[key] = child
    return value


def _validate_json_strings(value: Any) -> None:
    pending = [value]
    while pending:
        child = pending.pop()
        if isinstance(child, str):
            if any(0xD800 <= ord(char) <= 0xDFFF for char in child):
                raise CorridorKitError("JSON contains an unpaired Unicode surrogate")
        elif isinstance(child, dict):
            pending.extend(child.keys())
            pending.extend(child.values())
        elif isinstance(child, list):
            pending.extend(child)


def load_json(path: Path, *, max_bytes: int = MAX_JSON_BYTES) -> Any:
    """Load strict JSON within an explicit bounded size limit."""

    if (
        isinstance(max_bytes, bool)
        or not isinstance(max_bytes, int)
        or not 0 < max_bytes <= MAX_RULE_CANDIDATE_DECODE_BYTES
    ):
        raise CorridorKitError(
            "JSON max_bytes must be a positive integer no greater than "
            f"{MAX_RULE_CANDIDATE_DECODE_BYTES}"
        )

    if path.is_symlink() or not path.is_file():
        raise CorridorKitError(f"JSON input must be a regular non-symlink file: {path}")
    if path.stat().st_size > max_bytes:
        raise CorridorKitError(f"JSON input exceeds {max_bytes} bytes: {path}")
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda item: (_ for _ in ()).throw(
                CorridorKitError(f"non-finite JSON value: {item}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise CorridorKitError(f"invalid JSON input {path}: {exc}") from exc
    _validate_json_strings(value)
    _reject_large_integers(value)
    return value


def atomic_write_bytes(path: Path, value: bytes, *, mode: int = 0o644) -> None:
    """Atomically replace one regular file in an existing real directory."""

    parent = path.parent
    if path.is_symlink():
        raise CorridorKitError(f"refusing to replace symlink: {path}")
    if parent.is_symlink() or not parent.is_dir():
        raise CorridorKitError(f"output parent must be a real directory: {parent}")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def atomic_write_json(path: Path, value: Any, *, mode: int = 0o644) -> None:
    atomic_write_bytes(path, canonical_json_bytes(value) + b"\n", mode=mode)


def file_sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise CorridorKitError(f"digest input must be a regular non-symlink file: {path}")
    if path.stat().st_size > MAX_MANIFEST_FILE_BYTES:
        raise CorridorKitError(
            f"digest input exceeds {MAX_MANIFEST_FILE_BYTES} bytes: {path}"
        )
    return sha256_bytes(path.read_bytes())


def _is_python_cache(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    return "__pycache__" in relative.parts or relative.suffix in {".pyc", ".pyo"}


def regular_tree_digest(files: Sequence[Mapping[str, Any]]) -> str:
    """Bind the exact effective-file list and the frozen cache exclusion policy."""

    return sha256_json(
        {"exclusion_policy": list(TREE_EXCLUSION_POLICY), "files": list(files)}
    )


def purge_python_caches(root: Path) -> list[str]:
    """Remove only interpreter cache artifacts before a Corridor is frozen.

    The canonical tree excludes these artifacts because they are derived runtime
    noise.  Removing them prevents excluded bytecode from influencing execution.
    """

    if root.is_symlink() or not root.is_dir():
        raise CorridorKitError(f"cache purge root must be a real directory: {root}")
    removed: list[str] = []
    paths = sorted(root.rglob("*"), key=lambda item: item.as_posix(), reverse=True)
    for path in paths:
        if path.is_symlink():
            raise CorridorKitError(f"tree symlink is forbidden: {path}")
        if not _is_python_cache(path, root):
            continue
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                continue
            removed.append(relative + "/")
        elif path.is_file():
            path.unlink()
            removed.append(relative)
        else:
            raise CorridorKitError(f"tree special file is forbidden: {path}")
    return sorted(removed)


def regular_tree_manifest(root: Path) -> dict[str, Any]:
    """Describe source bytes without following symlinks or hashing runtime caches."""

    if root.is_symlink() or not root.is_dir():
        raise CorridorKitError(f"manifest root must be a real directory: {root}")
    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise CorridorKitError(f"tree symlink is forbidden: {path}")
        if _is_python_cache(path, root):
            continue
        file_mode = path.stat(follow_symlinks=False).st_mode
        if stat.S_ISDIR(file_mode):
            continue
        if not stat.S_ISREG(file_mode):
            raise CorridorKitError(f"tree special file is forbidden: {path}")
        size = path.stat().st_size
        if size > MAX_MANIFEST_FILE_BYTES:
            raise CorridorKitError(
                f"manifest input exceeds {MAX_MANIFEST_FILE_BYTES} bytes: {path}"
            )
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": size,
                "sha256": sha256_bytes(path.read_bytes()),
                "executable": bool(stat.S_IMODE(file_mode) & 0o111),
            }
        )
    payload = {
        "schema_version": MANIFEST_SCHEMA,
        "kit_version": KIT_VERSION,
        "exclusion_policy": list(TREE_EXCLUSION_POLICY),
        "files": files,
    }
    payload["tree_digest"] = regular_tree_digest(files)
    return payload


def public_world_inventory(roots: Mapping[str, Path]) -> dict[str, Any]:
    """Hash exposed source roots using caller-provided, portable labels."""

    if not roots:
        raise CorridorKitError("at least one labeled public root is required")
    sources: list[dict[str, Any]] = []
    for label, root in sorted(roots.items()):
        if not isinstance(label, str) or not label.strip() or "/" in label:
            raise CorridorKitError(f"invalid public-root label: {label!r}")
        path = Path(root)
        if path.is_symlink():
            raise CorridorKitError(f"public root symlink is forbidden: {path}")
        if path.is_file():
            sources.append(
                {
                    "source_id": label,
                    "kind": "file",
                    "bytes": path.stat().st_size,
                    "sha256": file_sha256(path),
                }
            )
        elif path.is_dir():
            manifest = regular_tree_manifest(path)
            sources.append(
                {
                    "source_id": label,
                    "kind": "tree",
                    "file_count": len(manifest["files"]),
                    "tree_digest": manifest["tree_digest"],
                    "files": manifest["files"],
                }
            )
        else:
            raise CorridorKitError(f"public root must be a regular file or directory: {path}")
    payload = {
        "schema_version": WORLD_INVENTORY_SCHEMA,
        "kit_version": KIT_VERSION,
        "sources": sources,
    }
    payload["world_digest"] = sha256_json(sources)
    return payload


def new_run_directory(run_root: Path, prefix: str = "run") -> Path:
    """Create a unique evidence directory without inspecting task state."""

    if run_root.is_symlink():
        raise CorridorKitError(f"run root symlink is forbidden: {run_root}")
    run_root.mkdir(parents=True, exist_ok=True)
    if not run_root.is_dir():
        raise CorridorKitError(f"run root must be a directory: {run_root}")
    safe_prefix = "".join(char for char in prefix if char.isalnum() or char in "-_")
    if not safe_prefix:
        raise CorridorKitError("run prefix must contain a safe character")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = run_root / f"{safe_prefix}-{stamp}-{uuid.uuid4().hex[:8]}"
    path.mkdir(mode=0o700)
    return path


def capture_command(
    argv: Sequence[str],
    output_dir: Path,
    *,
    cwd: Path | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Execute an argv directly and retain a replayable, non-authoritative report."""

    command = list(argv)
    if not command or any(not isinstance(item, str) or "\x00" in item for item in command):
        raise CorridorKitError("argv must be a non-empty list of NUL-free strings")
    if timeout_seconds is not None and timeout_seconds <= 0:
        raise CorridorKitError("timeout_seconds must be positive")
    if output_dir.is_symlink():
        raise CorridorKitError(f"capture directory symlink is forbidden: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=False)
    working_dir = Path.cwd() if cwd is None else Path(cwd)
    if working_dir.is_symlink() or not working_dir.is_dir():
        raise CorridorKitError(f"working directory must be a real directory: {working_dir}")

    request = {
        "schema_version": CAPTURE_SCHEMA,
        "kit_version": KIT_VERSION,
        "argv": command,
        "cwd": str(working_dir.resolve()),
        "timeout_seconds": timeout_seconds,
        "shell": False,
    }
    atomic_write_json(output_dir / "request.json", request)
    stdout_path = output_dir / "stdout.txt"
    stderr_path = output_dir / "stderr.txt"
    started_wall = datetime.now(timezone.utc)
    started = time.monotonic()
    status = "completed"
    exit_code: int | None = None
    error_type = ""
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        try:
            completed = subprocess.run(
                command,
                cwd=working_dir,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                shell=False,
                timeout=timeout_seconds,
                check=False,
            )
            exit_code = completed.returncode
        except subprocess.TimeoutExpired:
            status = "timed_out"
            error_type = "TimeoutExpired"
        except FileNotFoundError:
            status = "not_found"
            error_type = "FileNotFoundError"
        except OSError as exc:
            status = "execution_error"
            error_type = type(exc).__name__
    finished_wall = datetime.now(timezone.utc)
    report = {
        **request,
        "status": status,
        "exit_code": exit_code,
        "error_type": error_type,
        "started_at": started_wall.isoformat(),
        "finished_at": finished_wall.isoformat(),
        "duration_ms": round((time.monotonic() - started) * 1000, 3),
        "stdout": {
            "path": "stdout.txt",
            "bytes": stdout_path.stat().st_size,
            "sha256": file_sha256(stdout_path),
        },
        "stderr": {
            "path": "stderr.txt",
            "bytes": stderr_path.stat().st_size,
            "sha256": file_sha256(stderr_path),
        },
    }
    report["request_digest"] = sha256_json(request)
    atomic_write_json(output_dir / "result.json", report)
    return report
