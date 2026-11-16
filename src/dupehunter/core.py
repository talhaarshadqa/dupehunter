"""Duplicate detection using a three-stage pipeline.

1. Group files by size (free - comes from a stat call).
2. Within same-size groups, hash only the first few KB.
3. Within groups that still collide, hash the full file.

Most non-duplicates are eliminated in stages 1-2, so very few files are
ever read in full. That is what makes this fast on large directories.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Iterator

PARTIAL_BYTES = 4096
CHUNK_SIZE = 1024 * 1024


@dataclass
class DuplicateGroup:
    """A set of files with identical content."""

    digest: str
    size: int
    paths: list[Path] = field(default_factory=list)

    @property
    def wasted_bytes(self) -> int:
        """Bytes that could be reclaimed by keeping only one copy."""
        return self.size * (len(self.paths) - 1)

    def to_dict(self) -> dict:
        return {
            "hash": self.digest,
            "size": self.size,
            "wasted_bytes": self.wasted_bytes,
            "paths": [str(p) for p in self.paths],
        }


def iter_files(
    roots: Iterable[Path],
    *,
    min_size: int = 1,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    follow_symlinks: bool = False,
    skip_hidden: bool = True,
) -> Iterator[tuple[Path, int]]:
    """Yield (path, size) for every regular file under the given roots."""
    seen_inodes: set[tuple[int, int]] = set()

    for root in roots:
        root = Path(root)
        if root.is_file():
            candidates = [(root.parent, [], [root.name])]
        else:
            candidates = os.walk(root, followlinks=follow_symlinks)

        for dirpath, dirnames, filenames in candidates:
            if skip_hidden:
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for name in filenames:
                if skip_hidden and name.startswith("."):
                    continue
                if include and not any(fnmatch.fnmatch(name, pat) for pat in include):
                    continue
                if exclude and any(fnmatch.fnmatch(name, pat) for pat in exclude):
                    continue
                path = Path(dirpath) / name
                try:
                    st = path.stat() if follow_symlinks else path.lstat()
                except OSError:
                    continue
                if not path.is_file() or (path.is_symlink() and not follow_symlinks):
                    continue
                # Hard links point at the same data: count each inode once.
                key = (st.st_dev, st.st_ino)
                if key in seen_inodes:
                    continue
                seen_inodes.add(key)
                if st.st_size >= min_size:
                    yield path, st.st_size


def hash_file(path: Path, *, limit: int | None = None, algorithm: str = "blake2b") -> str:
    """Hash a file's content (or its first `limit` bytes)."""
    h = hashlib.new(algorithm)
    remaining = limit
    with open(path, "rb") as fh:
        while True:
            size = CHUNK_SIZE if remaining is None else min(CHUNK_SIZE, remaining)
            if size == 0:
                break
            chunk = fh.read(size)
            if not chunk:
                break
            h.update(chunk)
            if remaining is not None:
                remaining -= len(chunk)
    return h.hexdigest()


def _regroup(
    groups: Iterable[list[Path]],
    keyfunc: Callable[[Path], str],
    workers: int,
) -> list[tuple[str, list[Path]]]:
    """Split each group further by keyfunc(path), hashing in parallel."""
    flat = [p for group in groups for p in group]
    if not flat:
        return []
    group_of = {p: i for i, group in enumerate(groups) for p in group}

    def safe(p: Path) -> str | None:
        try:
            return keyfunc(p)
        except OSError:
            return None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        keys = list(pool.map(safe, flat))

    buckets: dict[tuple[int, str], list[Path]] = defaultdict(list)
    for path, key in zip(flat, keys):
        if key is not None:
            buckets[(group_of[path], key)].append(path)
    return [(key, paths) for (_, key), paths in buckets.items() if len(paths) > 1]


def find_duplicates(
    roots: Iterable[Path],
    *,
    min_size: int = 1,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    follow_symlinks: bool = False,
    skip_hidden: bool = True,
    workers: int | None = None,
    algorithm: str = "blake2b",
) -> list[DuplicateGroup]:
    """Return groups of files with identical content, largest waste first."""
    workers = workers or min(32, (os.cpu_count() or 4) * 2)

    # Stage 1: size
    by_size: dict[int, list[Path]] = defaultdict(list)
    for path, size in iter_files(
        roots,
        min_size=min_size,
        include=include,
        exclude=exclude,
        follow_symlinks=follow_symlinks,
        skip_hidden=skip_hidden,
    ):
        by_size[size].append(path)
    size_groups = [paths for paths in by_size.values() if len(paths) > 1]

    # Stage 2: partial hash
    partial = _regroup(
        size_groups,
        lambda p: hash_file(p, limit=PARTIAL_BYTES, algorithm=algorithm),
        workers,
    )

    # Stage 3: full hash
    full = _regroup(
        [paths for _, paths in partial],
        lambda p: hash_file(p, algorithm=algorithm),
        workers,
    )

    result = [
        DuplicateGroup(digest=digest, size=paths[0].stat().st_size, paths=sorted(paths))
        for digest, paths in full
    ]
    result.sort(key=lambda g: (-g.wasted_bytes, str(g.paths[0])))
    return result
