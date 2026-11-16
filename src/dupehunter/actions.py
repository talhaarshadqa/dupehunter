"""What to do with duplicates once they are found."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from .core import DuplicateGroup

KeepStrategy = Literal["oldest", "newest", "shortest", "first"]


def pick_keeper(group: DuplicateGroup, strategy: KeepStrategy = "oldest") -> Path:
    """Choose which file in a group survives."""
    paths = group.paths
    if strategy == "oldest":
        return min(paths, key=lambda p: (p.stat().st_mtime, str(p)))
    if strategy == "newest":
        return max(paths, key=lambda p: (p.stat().st_mtime, str(p)))
    if strategy == "shortest":
        return min(paths, key=lambda p: (len(str(p)), str(p)))
    if strategy == "first":
        return sorted(paths)[0]
    raise ValueError(f"unknown keep strategy: {strategy!r}")


def remove_duplicates(
    groups: list[DuplicateGroup],
    *,
    strategy: KeepStrategy = "oldest",
    mode: Literal["delete", "hardlink"] = "delete",
    dry_run: bool = True,
) -> list[tuple[Path, Path]]:
    """Delete (or hard-link) every non-keeper. Returns (removed, kept) pairs.

    Defaults to dry_run=True so nothing is touched unless asked explicitly.
    """
    actions: list[tuple[Path, Path]] = []
    for group in groups:
        keeper = pick_keeper(group, strategy)
        for path in group.paths:
            if path == keeper:
                continue
            actions.append((path, keeper))
            if dry_run:
                continue
            if mode == "delete":
                path.unlink()
            elif mode == "hardlink":
                tmp = path.with_name(path.name + ".dupehunter-tmp")
                os.link(keeper, tmp)
                os.replace(tmp, path)  # atomic swap
            else:
                raise ValueError(f"unknown mode: {mode!r}")
    return actions
