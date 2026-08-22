"""Unit tests for scripts/sync_release_version.py.

Runs the script as a subprocess against a scratch `--root` directory (never
the real repository files) covering rewrite and --check for all four version
sites, plus the guard against a dependency's inline `version = "..."` being
mistaken for the package version.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).parent.parent
SCRIPT = ROOT / "scripts" / "sync_release_version.py"

CARGO_TOML = """\
[package]
name = "zarr"
version = "0.1.3"
edition = "2021"

[dependencies]
zarrs = { version = "0.23", default-features = false, features = ["ndarray"] }
"""

PYPROJECT_TOML = """\
[project]
name = "duckdb-zarr"
version = "0.1.3"
requires-python = ">=3.11"
"""

DESCRIPTION_YML = """\
extension:
  name: zarr
  version: 0.1.3
  language: Rust
"""

CARGO_LOCK = """\
[[package]]
name = "other-crate"
version = "9.9.9"

[[package]]
name = "zarr"
version = "0.1.3"
dependencies = [
 "base64",
]
"""


@pytest.fixture()
def scratch_root(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / "Cargo.toml").write_text(CARGO_TOML, encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(PYPROJECT_TOML, encoding="utf-8")
    (tmp_path / "description.yml").write_text(DESCRIPTION_YML, encoding="utf-8")
    (tmp_path / "Cargo.lock").write_text(CARGO_LOCK, encoding="utf-8")
    return tmp_path


def run_sync(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def test_check_fails_when_placeholder_does_not_match_tag(scratch_root: pathlib.Path) -> None:
    result = run_sync("v0.1.9", "--check", "--root", str(scratch_root))
    assert result.returncode != 0
    assert "does not match version sites" in result.stderr


def test_rewrite_updates_all_four_sites(scratch_root: pathlib.Path) -> None:
    result = run_sync("v0.1.9", "--root", str(scratch_root))
    assert result.returncode == 0, result.stderr

    cargo_toml = (scratch_root / "Cargo.toml").read_text(encoding="utf-8")
    assert 'name = "zarr"\nversion = "0.1.9"' in cargo_toml
    # The dependency's inline version must be untouched.
    assert 'zarrs = { version = "0.23"' in cargo_toml

    pyproject = (scratch_root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "0.1.9"' in pyproject

    description = (scratch_root / "description.yml").read_text(encoding="utf-8")
    assert "  version: 0.1.9" in description

    cargo_lock = (scratch_root / "Cargo.lock").read_text(encoding="utf-8")
    assert 'name = "zarr"\nversion = "0.1.9"' in cargo_lock
    # The unrelated lockfile entry must be untouched.
    assert 'name = "other-crate"\nversion = "9.9.9"' in cargo_lock


def test_check_passes_after_rewrite(scratch_root: pathlib.Path) -> None:
    run_sync("v0.1.9", "--root", str(scratch_root))
    result = run_sync("v0.1.9", "--check", "--root", str(scratch_root))
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


@pytest.mark.parametrize("bad_tag", ["0.1.9", "v0.1", "v0.1.9-rc1"])
def test_rejects_tags_that_are_not_vx_y_z(scratch_root: pathlib.Path, bad_tag: str) -> None:
    result = run_sync(bad_tag, "--root", str(scratch_root))
    assert result.returncode != 0
    assert "must look like v1.2.3" in result.stderr
