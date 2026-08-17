"""Immutable, monotonic custody for task-declared submission paths.

The snapshot store is deliberately task-neutral.  A Worker names the absolute
paths that constitute one complete, scorable submission; the kit copies those
bytes into an immutable snapshot and advances a small ``latest`` reference only
after the complete snapshot has been verified.  Restoring a snapshot never
grants authority: callers must run restore with the same OS identity that owns
the task state.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .core import (
    MAX_MANIFEST_FILE_BYTES,
    CorridorKitError,
    atomic_write_bytes,
    atomic_write_json,
    canonical_json_bytes,
    load_json,
    sha256_bytes,
)


SUBMISSION_SNAPSHOT_SCHEMA = "charting-loop/submission-snapshot/v1"
SUBMISSION_LATEST_SCHEMA = "charting-loop/submission-latest/v1"
SUBMISSION_ROLES = frozenset({"worker", "qa"})
MAX_SUBMISSION_FILES = 4096


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _real_directory(path: Path, *, create: bool = False) -> Path:
    if not path.is_absolute():
        raise CorridorKitError(f"path must be absolute: {path}")
    if create and not path.exists():
        parent = path.parent
        if parent.is_symlink() or not parent.is_dir():
            raise CorridorKitError(f"snapshot parent must be a real directory: {parent}")
        path.mkdir(mode=0o700)
    if path.is_symlink() or not path.is_dir():
        raise CorridorKitError(f"path must be a real directory: {path}")
    return path


def _validate_role(role: str) -> str:
    if role not in SUBMISSION_ROLES:
        raise CorridorKitError(f"submission role must be one of {sorted(SUBMISSION_ROLES)}")
    return role


def _source_files(paths: Iterable[Path]) -> list[tuple[Path, bytes, int]]:
    files: dict[str, tuple[Path, bytes, int]] = {}
    roots = list(paths)
    if not roots:
        raise CorridorKitError("at least one submission path is required")
    for root in roots:
        if not root.is_absolute():
            raise CorridorKitError(f"submission path must be absolute: {root}")
        if root.is_symlink():
            raise CorridorKitError(f"submission symlink is forbidden: {root}")
        if root.is_file():
            candidates = [root]
        elif root.is_dir():
            candidates = sorted(root.rglob("*"), key=lambda item: item.as_posix())
            if not candidates:
                raise CorridorKitError(f"submission directory is empty: {root}")
        else:
            raise CorridorKitError(f"submission path must be a regular file or directory: {root}")
        for candidate in candidates:
            if candidate.is_symlink():
                raise CorridorKitError(f"submission symlink is forbidden: {candidate}")
            if candidate.is_dir():
                continue
            if not candidate.is_file():
                raise CorridorKitError(f"submission special file is forbidden: {candidate}")
            key = candidate.as_posix()
            if key in files:
                continue
            size = candidate.stat().st_size
            if size > MAX_MANIFEST_FILE_BYTES:
                raise CorridorKitError(
                    f"submission file exceeds {MAX_MANIFEST_FILE_BYTES} bytes: {candidate}"
                )
            data = candidate.read_bytes()
            files[key] = (candidate, data, stat.S_IMODE(candidate.stat().st_mode))
            if len(files) > MAX_SUBMISSION_FILES:
                raise CorridorKitError(
                    f"submission exceeds {MAX_SUBMISSION_FILES} regular files"
                )
    return [files[key] for key in sorted(files)]


def _latest_path(root: Path, role: str) -> Path:
    return root / "latest" / f"{role}.json"


def _load_latest_optional(root: Path, role: str) -> dict[str, Any] | None:
    path = _latest_path(root, role)
    if not path.exists():
        return None
    value = load_json(path)
    if not isinstance(value, dict) or value.get("schema_version") != SUBMISSION_LATEST_SCHEMA:
        raise CorridorKitError(f"invalid latest submission reference: {path}")
    if value.get("role") != role:
        raise CorridorKitError(f"latest submission role mismatch: {path}")
    sequence = value.get("sequence")
    snapshot_id = value.get("snapshot_id")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise CorridorKitError(f"invalid latest submission sequence: {path}")
    if not isinstance(snapshot_id, str) or not snapshot_id:
        raise CorridorKitError(f"invalid latest submission id: {path}")
    return value


def _acquire_lock(root: Path) -> Path:
    lock = root / ".submission.lock"
    for _ in range(100):
        try:
            lock.mkdir(mode=0o700)
            return lock
        except FileExistsError:
            time.sleep(0.01)
    raise CorridorKitError(f"submission snapshot store is busy: {root}")


def freeze_submission(root: Path, *, role: str, paths: Iterable[Path]) -> dict[str, Any]:
    """Freeze one complete version and atomically advance the role's latest ref."""

    role = _validate_role(role)
    root = _real_directory(root, create=True)
    files = _source_files(paths)
    for child in (root / "snapshots", root / "latest"):
        if not child.exists():
            child.mkdir(mode=0o700)
        _real_directory(child)
    role_root = root / "snapshots" / role
    if not role_root.exists():
        role_root.mkdir(mode=0o700)
    _real_directory(role_root)

    lock = _acquire_lock(root)
    staging: Path | None = None
    try:
        previous = _load_latest_optional(root, role)
        sequence = 1 if previous is None else int(previous["sequence"]) + 1
        staging = role_root / f".staging-{uuid.uuid4().hex}"
        staging.mkdir(mode=0o700)
        blobs = staging / "files"
        blobs.mkdir(mode=0o700)
        records: list[dict[str, Any]] = []
        for index, (source, data, mode) in enumerate(files):
            blob_relative = f"files/{index:04d}.bin"
            blob = staging / blob_relative
            atomic_write_bytes(blob, data, mode=0o400)
            records.append(
                {
                    "destination": source.as_posix(),
                    "blob": blob_relative,
                    "bytes": len(data),
                    "sha256": sha256_bytes(data),
                    "mode": mode,
                }
            )
        identity = {
            "schema_version": SUBMISSION_SNAPSHOT_SCHEMA,
            "role": role,
            "sequence": sequence,
            "parent_snapshot_id": "" if previous is None else previous["snapshot_id"],
            "files": records,
        }
        tree_digest = sha256_bytes(canonical_json_bytes(identity))
        snapshot_id = f"{role}-{sequence:06d}-{tree_digest.removeprefix('sha256:')[:16]}"
        manifest = {
            **identity,
            "snapshot_id": snapshot_id,
            "tree_digest": tree_digest,
            "created_at": _utc_now(),
            "complete": True,
        }
        atomic_write_json(staging / "manifest.json", manifest, mode=0o400)
        final = role_root / snapshot_id
        if final.exists():
            raise CorridorKitError(f"submission snapshot already exists: {snapshot_id}")
        os.replace(staging, final)
        staging = None
        latest = {
            "schema_version": SUBMISSION_LATEST_SCHEMA,
            "role": role,
            "sequence": sequence,
            "snapshot_id": snapshot_id,
            "tree_digest": tree_digest,
        }
        atomic_write_json(_latest_path(root, role), latest, mode=0o600)
        return {**latest, "file_count": len(records), "complete": True}
    finally:
        if staging is not None and staging.exists():
            for path in sorted(staging.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            staging.rmdir()
        lock.rmdir()


def verify_submission(root: Path, *, role: str, snapshot_id: str | None = None) -> dict[str, Any]:
    """Verify a snapshot's manifest, blobs, byte hashes, and monotonic identity."""

    role = _validate_role(role)
    root = _real_directory(root)
    latest = _load_latest_optional(root, role)
    if snapshot_id is None:
        if latest is None:
            raise CorridorKitError(f"no {role} submission snapshot exists")
        snapshot_id = str(latest["snapshot_id"])
    if not snapshot_id or "/" in snapshot_id or snapshot_id in {".", ".."}:
        raise CorridorKitError("invalid submission snapshot id")
    snapshot = root / "snapshots" / role / snapshot_id
    _real_directory(snapshot)
    manifest = load_json(snapshot / "manifest.json")
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SUBMISSION_SNAPSHOT_SCHEMA:
        raise CorridorKitError(f"invalid submission manifest: {snapshot_id}")
    if manifest.get("role") != role or manifest.get("snapshot_id") != snapshot_id:
        raise CorridorKitError(f"submission manifest identity mismatch: {snapshot_id}")
    if manifest.get("complete") is not True:
        raise CorridorKitError(f"submission snapshot is incomplete: {snapshot_id}")
    records = manifest.get("files")
    if not isinstance(records, list) or not records or len(records) > MAX_SUBMISSION_FILES:
        raise CorridorKitError(f"invalid submission file manifest: {snapshot_id}")
    destinations: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise CorridorKitError(f"invalid submission file record {index}")
        destination = record.get("destination")
        blob_relative = record.get("blob")
        if not isinstance(destination, str) or not Path(destination).is_absolute():
            raise CorridorKitError(f"invalid submission destination {index}")
        if destination in destinations:
            raise CorridorKitError(f"duplicate submission destination: {destination}")
        destinations.add(destination)
        if blob_relative != f"files/{index:04d}.bin":
            raise CorridorKitError(f"invalid submission blob path {index}")
        blob = snapshot / blob_relative
        if blob.is_symlink() or not blob.is_file():
            raise CorridorKitError(f"missing submission blob {index}")
        data = blob.read_bytes()
        if record.get("bytes") != len(data) or record.get("sha256") != sha256_bytes(data):
            raise CorridorKitError(f"submission blob identity mismatch {index}")
        mode = record.get("mode")
        if isinstance(mode, bool) or not isinstance(mode, int) or mode < 0 or mode > 0o7777:
            raise CorridorKitError(f"invalid submission mode {index}")
    identity = {
        "schema_version": manifest["schema_version"],
        "role": manifest["role"],
        "sequence": manifest["sequence"],
        "parent_snapshot_id": manifest["parent_snapshot_id"],
        "files": records,
    }
    tree_digest = sha256_bytes(canonical_json_bytes(identity))
    expected_id = (
        f"{role}-{int(manifest['sequence']):06d}-"
        f"{tree_digest.removeprefix('sha256:')[:16]}"
    )
    if manifest.get("tree_digest") != tree_digest or snapshot_id != expected_id:
        raise CorridorKitError(f"submission tree identity mismatch: {snapshot_id}")
    return {
        "ok": True,
        "role": role,
        "sequence": manifest["sequence"],
        "snapshot_id": snapshot_id,
        "tree_digest": tree_digest,
        "file_count": len(records),
        "latest": latest is not None and latest.get("snapshot_id") == snapshot_id,
        "manifest": manifest,
    }


def list_submissions(root: Path, *, role: str) -> dict[str, Any]:
    """List verified immutable versions for one role in sequence order."""

    role = _validate_role(role)
    root = _real_directory(root)
    role_root = root / "snapshots" / role
    if not role_root.exists():
        return {"ok": True, "role": role, "latest": None, "snapshots": []}
    _real_directory(role_root)
    snapshots = []
    for path in sorted(role_root.iterdir(), key=lambda item: item.name):
        if path.name.startswith("."):
            continue
        snapshots.append(verify_submission(root, role=role, snapshot_id=path.name))
    snapshots.sort(key=lambda item: int(item["sequence"]))
    latest = _load_latest_optional(root, role)
    if latest is not None:
        if not snapshots or snapshots[-1]["snapshot_id"] != latest["snapshot_id"]:
            raise CorridorKitError("latest submission reference is not the highest complete version")
    return {"ok": True, "role": role, "latest": latest, "snapshots": snapshots}


def restore_submission(
    root: Path, *, role: str = "worker", snapshot_id: str | None = None
) -> dict[str, Any]:
    """Restore a verified version atomically to its declared absolute paths."""

    report = verify_submission(root, role=role, snapshot_id=snapshot_id)
    restored = []
    snapshot = root / "snapshots" / role / report["snapshot_id"]
    for record in report["manifest"]["files"]:
        destination = Path(record["destination"])
        parent = destination.parent
        if destination.is_symlink():
            raise CorridorKitError(f"refusing to restore over symlink: {destination}")
        if parent.is_symlink() or not parent.is_dir():
            raise CorridorKitError(f"restore parent must be a real directory: {parent}")
        data = (snapshot / record["blob"]).read_bytes()
        atomic_write_bytes(destination, data, mode=int(record["mode"]))
        restored.append(destination.as_posix())
    return {
        "ok": True,
        "role": role,
        "snapshot_id": report["snapshot_id"],
        "sequence": report["sequence"],
        "tree_digest": report["tree_digest"],
        "restored_paths": restored,
    }
