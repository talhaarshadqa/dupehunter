"""Command-line interface."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

from . import __version__
from .actions import remove_duplicates
from .core import DuplicateGroup, find_duplicates

UNITS = {"b": 1, "k": 1024, "m": 1024**2, "g": 1024**3}


def parse_size(text: str) -> int:
    """'10k' -> 10240, '1.5M' -> 1572864, '42' -> 42."""
    text = text.strip().lower().rstrip("b") or "0"
    if text[-1] in UNITS:
        return int(float(text[:-1]) * UNITS[text[-1]])
    return int(text)


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dupehunter",
        description="Find (and optionally remove) duplicate files.",
    )
    p.add_argument("paths", nargs="+", type=Path, help="directories or files to scan")
    p.add_argument("--min-size", default="1", type=parse_size, help="ignore smaller files (e.g. 10k, 2M)")
    p.add_argument("--include", action="append", metavar="GLOB", help="only consider matching names")
    p.add_argument("--exclude", action="append", metavar="GLOB", help="skip matching names")
    p.add_argument("--hidden", action="store_true", help="include dotfiles and dot-directories")
    p.add_argument("--follow-symlinks", action="store_true")
    p.add_argument("--workers", type=int, help="hashing threads (default: 2x CPUs)")
    p.add_argument("-f", "--format", choices=["text", "json", "csv"], default="text")

    act = p.add_argument_group("cleanup")
    act.add_argument("--delete", action="store_true", help="delete duplicates, keeping one per group")
    act.add_argument("--hardlink", action="store_true", help="replace duplicates with hard links")
    act.add_argument("--keep", choices=["oldest", "newest", "shortest", "first"], default="oldest")
    act.add_argument("-y", "--yes", action="store_true", help="actually do it (otherwise dry-run)")

    p.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    return p


def render_text(groups: list[DuplicateGroup], elapsed: float, out=sys.stdout) -> None:
    for i, g in enumerate(groups, 1):
        print(f"[{i}] {len(g.paths)} copies x {human(g.size)}  ({g.digest[:12]})", file=out)
        for path in g.paths:
            print(f"    {path}", file=out)
    total = sum(g.wasted_bytes for g in groups)
    print(
        f"\n{len(groups)} duplicate groups, {human(total)} reclaimable "
        f"(scanned in {elapsed:.2f}s)",
        file=out,
    )


def render_csv(groups: list[DuplicateGroup], out=sys.stdout) -> None:
    w = csv.writer(out)
    w.writerow(["group", "hash", "size", "path"])
    for i, g in enumerate(groups, 1):
        for path in g.paths:
            w.writerow([i, g.digest, g.size, str(path)])


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    missing = [p for p in args.paths if not p.exists()]
    if missing:
        print(f"error: path not found: {', '.join(map(str, missing))}", file=sys.stderr)
        return 2
    if args.delete and args.hardlink:
        print("error: choose either --delete or --hardlink", file=sys.stderr)
        return 2

    start = time.perf_counter()
    groups = find_duplicates(
        args.paths,
        min_size=args.min_size,
        include=args.include,
        exclude=args.exclude,
        follow_symlinks=args.follow_symlinks,
        skip_hidden=not args.hidden,
        workers=args.workers,
    )
    elapsed = time.perf_counter() - start

    if args.format == "json":
        json.dump([g.to_dict() for g in groups], sys.stdout, indent=2)
        print()
    elif args.format == "csv":
        render_csv(groups)
    else:
        render_text(groups, elapsed)

    if args.delete or args.hardlink:
        mode = "delete" if args.delete else "hardlink"
        dry = not args.yes
        actions = remove_duplicates(groups, strategy=args.keep, mode=mode, dry_run=dry)
        verb = {"delete": "delete", "hardlink": "hard-link"}[mode]
        prefix = "[dry-run] would " if dry else ""
        for removed, kept in actions:
            print(f"{prefix}{verb} {removed}  (keeping {kept})", file=sys.stderr)
        if dry and actions:
            print("\nRe-run with --yes to apply.", file=sys.stderr)

    return 1 if groups else 0


if __name__ == "__main__":
    raise SystemExit(main())
