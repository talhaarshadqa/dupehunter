import os
from pathlib import Path

import pytest

from dupehunter import find_duplicates, pick_keeper, remove_duplicates
from dupehunter.cli import main, parse_size
from dupehunter.core import PARTIAL_BYTES, hash_file


def write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


@pytest.fixture
def tree(tmp_path):
    write(tmp_path / "a.txt", b"hello world")
    write(tmp_path / "sub" / "b.txt", b"hello world")
    write(tmp_path / "sub" / "deep" / "c.txt", b"hello world")
    write(tmp_path / "unique.txt", b"something else")
    write(tmp_path / "same_size.txt", b"hello WORLD")  # same size, different content
    return tmp_path


def test_finds_group(tree):
    groups = find_duplicates([tree])
    assert len(groups) == 1
    assert len(groups[0].paths) == 3
    assert groups[0].wasted_bytes == 11 * 2


def test_same_prefix_different_tail(tmp_path):
    prefix = b"x" * PARTIAL_BYTES
    write(tmp_path / "1.bin", prefix + b"A")
    write(tmp_path / "2.bin", prefix + b"B")
    assert find_duplicates([tmp_path]) == []


def test_no_duplicates(tmp_path):
    write(tmp_path / "1", b"one")
    write(tmp_path / "2", b"two!")
    assert find_duplicates([tmp_path]) == []


def test_min_size_and_globs(tree):
    assert find_duplicates([tree], min_size=100) == []
    assert find_duplicates([tree], include=["*.bin"]) == []
    groups = find_duplicates([tree], exclude=["c.txt"])
    assert len(groups[0].paths) == 2


def test_hidden_files_skipped_by_default(tmp_path):
    write(tmp_path / "x", b"data")
    write(tmp_path / ".hidden" / "y", b"data")
    assert find_duplicates([tmp_path]) == []
    assert len(find_duplicates([tmp_path], skip_hidden=False)) == 1


def test_hardlinks_not_reported(tmp_path):
    a = write(tmp_path / "a", b"linked")
    os.link(a, tmp_path / "b")
    assert find_duplicates([tmp_path]) == []


def test_hash_file_limit(tmp_path):
    f = write(tmp_path / "f", b"abcdef")
    assert hash_file(f, limit=3) == hash_file(write(tmp_path / "g", b"abc"))


def test_pick_keeper_strategies(tree):
    group = find_duplicates([tree])[0]
    old = tree / "sub" / "deep" / "c.txt"
    os.utime(old, (1_000_000, 1_000_000))
    assert pick_keeper(group, "oldest") == old
    assert pick_keeper(group, "shortest") == tree / "a.txt"
    with pytest.raises(ValueError):
        pick_keeper(group, "bogus")


def test_dry_run_touches_nothing(tree):
    groups = find_duplicates([tree])
    actions = remove_duplicates(groups, dry_run=True)
    assert len(actions) == 2
    assert all(p.exists() for p in groups[0].paths)


def test_delete(tree):
    groups = find_duplicates([tree])
    remove_duplicates(groups, strategy="shortest", dry_run=False)
    assert (tree / "a.txt").exists()
    assert not (tree / "sub" / "b.txt").exists()
    assert find_duplicates([tree]) == []


def test_hardlink(tree):
    groups = find_duplicates([tree])
    remove_duplicates(groups, strategy="shortest", mode="hardlink", dry_run=False)
    assert (tree / "sub" / "b.txt").stat().st_ino == (tree / "a.txt").stat().st_ino
    assert (tree / "sub" / "b.txt").read_bytes() == b"hello world"


@pytest.mark.parametrize("text,expected", [("42", 42), ("1k", 1024), ("1.5M", 1572864), ("2kb", 2048)])
def test_parse_size(text, expected):
    assert parse_size(text) == expected


def test_cli_exit_codes(tree, tmp_path_factory, capsys):
    assert main([str(tree)]) == 1
    empty = tmp_path_factory.mktemp("empty")
    assert main([str(empty)]) == 0
    assert main([str(tree / "nope")]) == 2


def test_cli_json(tree, capsys):
    import json

    main([str(tree), "-f", "json"])
    data = json.loads(capsys.readouterr().out)
    assert data[0]["size"] == 11 and len(data[0]["paths"]) == 3
