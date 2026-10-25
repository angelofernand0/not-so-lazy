from pathlib import Path

import pytest

from notsolazy.storage import LocalBlobStore


def test_blob_roundtrip_and_replace(tmp_path: Path) -> None:
    store = LocalBlobStore(tmp_path)
    key = "raw/320193/filing.html"
    assert not store.exists(key)
    store.write(key, b"first")
    store.write(key, b"second")
    assert store.read(key) == b"second"
    assert list((tmp_path / "raw/320193").iterdir()) == [tmp_path / key]


@pytest.mark.parametrize("key", ["", "../secret", "/tmp/secret", "raw/../../secret", ".", "a\\b"])
def test_blob_rejects_invalid_keys(tmp_path: Path, key: str) -> None:
    with pytest.raises(ValueError):
        LocalBlobStore(tmp_path).write(key, b"blocked")


def test_blob_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "blobs"
    root.mkdir()
    (root / "escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        LocalBlobStore(root).write("escape/file", b"blocked")
