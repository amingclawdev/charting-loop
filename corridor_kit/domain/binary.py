"""Generic, read-only binary inspection helpers.

The module contains no benchmark identifier, opcode recipe, verifier knowledge,
candidate patch, or fixed offset.  It exposes repeatable observations that a fresh
task Builder may choose when the public task world contains binaries.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import stat
import struct
from typing import Any, Mapping, Sequence

from ..capabilities import CAPABILITY_SCHEMA
from ..core import CorridorKitError, file_sha256, sha256_json


ELF_INVENTORY_SCHEMA = "charting-loop/binary-elf-inventory/v1"
BINARY_DIFF_SCHEMA = "charting-loop/binary-diff/v1"
BINARY_REPLAY_SCHEMA = "charting-loop/binary-replay-record/v1"
ELF_MACHINE = {
    0: "none",
    3: "x86",
    8: "mips",
    20: "powerpc",
    40: "arm",
    62: "x86-64",
    183: "aarch64",
    243: "riscv",
}


def _regular(path: Path) -> Path:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise CorridorKitError(f"binary input must be a regular non-symlink file: {path}")
    return path


def elf_inventory(path: Path) -> dict[str, Any]:
    """Read a bounded ELF header and report portable identity facts."""

    path = _regular(path)
    data = path.read_bytes()
    if len(data) < 16 or data[:4] != b"\x7fELF":
        raise CorridorKitError(f"not an ELF file: {path}")
    elf_class = data[4]
    byte_order_id = data[5]
    if elf_class not in (1, 2) or byte_order_id not in (1, 2):
        raise CorridorKitError("unsupported ELF class or byte order")
    byte_order = "little" if byte_order_id == 1 else "big"
    prefix = "<" if byte_order_id == 1 else ">"
    header_size = 52 if elf_class == 1 else 64
    if len(data) < header_size:
        raise CorridorKitError("truncated ELF header")
    if elf_class == 1:
        fields = struct.unpack(prefix + "HHIIIIIHHHHHH", data[16:52])
    else:
        fields = struct.unpack(prefix + "HHIQQQIHHHHHH", data[16:64])
    elf_type, machine, version, entry, phoff, shoff, flags, ehsize, phentsize, phnum, shentsize, shnum, shstrndx = fields
    return {
        "schema_version": ELF_INVENTORY_SCHEMA,
        "sha256": file_sha256(path),
        "size_bytes": len(data),
        "mode": oct(stat.S_IMODE(path.stat().st_mode)),
        "elf_class": 32 if elf_class == 1 else 64,
        "byte_order": byte_order,
        "os_abi": data[7],
        "elf_type": elf_type,
        "machine_id": machine,
        "machine": ELF_MACHINE.get(machine, f"unknown-{machine}"),
        "header_version": version,
        "entry": entry,
        "program_header_offset": phoff,
        "section_header_offset": shoff,
        "flags": flags,
        "header_size": ehsize,
        "program_header_entry_size": phentsize,
        "program_header_count": phnum,
        "section_header_entry_size": shentsize,
        "section_header_count": shnum,
        "section_name_index": shstrndx,
        "side_effects": "none",
    }


def binary_diff(before: Path, after: Path) -> dict[str, Any]:
    """Return changed byte ranges without embedding either binary's contents."""

    before = _regular(before)
    after = _regular(after)
    left = before.read_bytes()
    right = after.read_bytes()
    common = min(len(left), len(right))
    changed_positions = [index for index in range(common) if left[index] != right[index]]
    if len(left) != len(right):
        changed_positions.extend(range(common, max(len(left), len(right))))
    ranges: list[dict[str, int]] = []
    if changed_positions:
        start = previous = changed_positions[0]
        for position in changed_positions[1:]:
            if position != previous + 1:
                ranges.append({"start": start, "end_exclusive": previous + 1, "length": previous + 1 - start})
                start = position
            previous = position
        ranges.append({"start": start, "end_exclusive": previous + 1, "length": previous + 1 - start})
    return {
        "schema_version": BINARY_DIFF_SCHEMA,
        "before_sha256": file_sha256(before),
        "after_sha256": file_sha256(after),
        "before_size_bytes": len(left),
        "after_size_bytes": len(right),
        "changed_byte_count": len(changed_positions),
        "changed_ranges": ranges,
        "identical": not changed_positions,
        "side_effects": "none",
    }


def binary_replay_record(argv: Sequence[str], inputs: Mapping[str, Path]) -> dict[str, Any]:
    """Bind a shell-free argv vector to labeled input identities for later replay."""

    if not argv or any(not isinstance(item, str) or not item for item in argv):
        raise CorridorKitError("replay argv must be a non-empty sequence of strings")
    if not inputs:
        raise CorridorKitError("replay record requires at least one labeled input")
    records: list[dict[str, Any]] = []
    for label, path in sorted(inputs.items()):
        if not isinstance(label, str) or not label or "/" in label:
            raise CorridorKitError(f"invalid replay input label: {label!r}")
        path = _regular(Path(path))
        records.append({"label": label, "sha256": file_sha256(path), "size_bytes": path.stat().st_size})
    record = {
        "schema_version": BINARY_REPLAY_SCHEMA,
        "shell": False,
        "argv": list(argv),
        "inputs": records,
        "side_effects": "not_executed",
    }
    record["replay_digest"] = sha256_json(record)
    return record


def builtin_binary_registry() -> dict[str, Any]:
    """Describe the frozen generic binary pack without selecting it for a task."""

    definitions = [
        {
            "capability_id": "binary.elf-inventory",
            "version": "1.0.0",
            "summary": "Read-only ELF identity and header inventory.",
            "entrypoint": "python -m corridor_kit binary inventory PATH",
            "input_contract": {"path": "regular non-symlink ELF file"},
            "output_contract": {"schema_version": ELF_INVENTORY_SCHEMA},
            "side_effects": "none",
            "applicability": {"domains": ["binary"], "signals": ["ELF magic"]},
        },
        {
            "capability_id": "binary.diff-ranges",
            "version": "1.0.0",
            "summary": "Read-only binary identity and changed-range comparison.",
            "entrypoint": "python -m corridor_kit binary diff BEFORE AFTER",
            "input_contract": {"before": "regular file", "after": "regular file"},
            "output_contract": {"schema_version": BINARY_DIFF_SCHEMA},
            "side_effects": "none",
            "applicability": {"domains": ["binary"], "signals": ["before/after files"]},
        },
        {
            "capability_id": "binary.replay-record",
            "version": "1.0.0",
            "summary": "Bind shell-free argv to labeled binary identities.",
            "entrypoint": "python -m corridor_kit binary replay --input LABEL=PATH -- ARGV",
            "input_contract": {"argv": "non-empty string array", "inputs": "labeled regular files"},
            "output_contract": {"schema_version": BINARY_REPLAY_SCHEMA},
            "side_effects": "none",
            "applicability": {"domains": ["binary"], "signals": ["replayable command"]},
        },
    ]
    capabilities = []
    for definition in definitions:
        capabilities.append({**definition, "digest": sha256_json(definition)})
    return {
        "schema_version": CAPABILITY_SCHEMA,
        "state": "compiled",
        "registry_version": "1.0.0",
        "capabilities": capabilities,
    }
