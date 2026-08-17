"""Task-neutral domain capability packs shipped with Corridor kit."""

from .binary import binary_diff, binary_replay_record, builtin_binary_registry, elf_inventory

__all__ = [
    "binary_diff",
    "binary_replay_record",
    "builtin_binary_registry",
    "elf_inventory",
]
