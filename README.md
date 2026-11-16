# 🔍 dupehunter

[![CI](https://github.com/talhaarshadqa/dupehunter/actions/workflows/ci.yml/badge.svg)](https://github.com/talhaarshadqa/dupehunter/actions)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen)

**Fast, safe duplicate-file finder.** Pure Python, zero dependencies.

```text
$ dupehunter ~/Pictures --min-size 100k
[1] 3 copies x 4.2 MB  (9f2c1e07ab44)
    /home/me/Pictures/2024/beach.jpg
    /home/me/Pictures/backup/beach.jpg
    /home/me/Pictures/phone-import/IMG_0412.jpg
[2] 2 copies x 1.1 MB  (03be7d9a1f5c)
    ...

14 duplicate groups, 38.6 MB reclaimable (scanned in 0.84s)
```

## ✨ Features

- **Three-stage pipeline**: size → partial hash (first 4 KB) → full hash. Most files are never read in full.
- **Parallel hashing** with a thread pool
- **Safe by default**: `--delete` and `--hardlink` only do a dry run until you add `--yes`
- **Hard-link aware**: files that already share an inode aren't reported
- **Keep strategies**: keep the `oldest`, `newest`, `shortest` path, or `first` alphabetically
- **Output**: human-readable text, `json`, or `csv`
- **Filters**: `--min-size 10M`, `--include "*.jpg"`, `--exclude "*.tmp"`, `--hidden`
- **Script-friendly exit codes**: `0` = no duplicates, `1` = duplicates found, `2` = error

## 📦 Install

```bash
git clone https://github.com/talhaarshadqa/dupehunter.git
cd dupehunter
pip install -e .
```

## 🚀 Usage

```bash
# Report duplicates
dupehunter ~/Downloads ~/Documents

# Only large images
dupehunter ~/Pictures --include "*.jpg" --include "*.png" --min-size 500k

# Preview cleanup, keeping the oldest copy
dupehunter ~/Downloads --delete --keep oldest

# Actually delete
dupehunter ~/Downloads --delete --keep oldest --yes

# Save space without losing any path: replace copies with hard links
dupehunter ~/Music --hardlink --yes

# Machine-readable output
dupehunter . -f json > dupes.json
```

### As a library

```python
from dupehunter import find_duplicates, remove_duplicates

groups = find_duplicates(["/data"], min_size=1024)
for g in groups:
    print(g.size, g.paths)

remove_duplicates(groups, strategy="newest", dry_run=True)
```

## ⚙️ How it works

```
all files ──► group by size ──► hash first 4 KB ──► hash full file ──► duplicates
  10,000         ~800              ~120                 ~95
```

Two files can only be identical if they have the same size, which costs one `stat()` call to check.
Hashing only the first 4 KB removes most of the remaining false matches cheaply. Only the
small set of files that are still candidates gets read in full. Hashing uses BLAKE2b.

## 🧪 Development

```bash
pip install -e ".[dev]"
pytest --cov=dupehunter
ruff check .
```

CI runs the tests on Linux and macOS for Python 3.9, 3.11 and 3.13.

## 📄 License

MIT
