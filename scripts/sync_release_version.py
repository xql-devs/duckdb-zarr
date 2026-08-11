#!/usr/bin/env python3
"""Synchronize the project version with a release tag.

`duckdb-zarr` keeps a single authoritative version repeated across three
files — `Cargo.toml`, `pyproject.toml`, and `description.yml` — plus the
`zarr` package entry in `Cargo.lock`. The committed value is a *development
placeholder*; it is not expected to track the latest release. At release
time the git tag (for example `v0.1.4`) is the source of truth: this script
rewrites all four sites to match the tag in the CI checkout. Nothing is
committed — the rewrite lives only in the ephemeral release build checkout,
so the published community descriptor and docs carry the tag version while
the repository keeps its development placeholder.

This mirrors the dynamic-versioning approach used by the sibling
[`arrow-lint`](https://github.com/d33bs/arrow-lint) and
[`zarr-lint`](https://github.com/d33bs/zarr-lint) projects — see
docs/versioning.md.

Usage::

    python3 scripts/sync_release_version.py v0.1.4        # rewrite
    python3 scripts/sync_release_version.py v0.1.4 --check  # verify only
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TAG_PATTERN = re.compile(r"^v(?P<version>\d+\.\d+\.\d+)$")


@dataclass(frozen=True)
class Site:
    path: str
    # Matches the single standalone version line/block for this file. Anchored
    # so it never matches a dependency's inline `version = "..."` (e.g.
    # Cargo.toml's `zarrs = { version = "0.23", ... }`, which is not a bare
    # `^version = "..."$` line).
    pattern: re.Pattern[str]
    # Rewrites `match` to embed `version`, returning the full replacement text.
    render: Callable[[re.Match[str], str], str]


def _render_toml(match: re.Match[str], version: str) -> str:
    return f'version = "{version}"'


def _render_description_yml(match: re.Match[str], version: str) -> str:
    return f"{match.group(1)}version: {version}"


def _render_cargo_lock(match: re.Match[str], version: str) -> str:
    return f'{match.group(1)}"{version}"'


SITES: list[Site] = [
    Site(
        "Cargo.toml",
        re.compile(r'^version = "\d+\.\d+\.\d+"$', re.MULTILINE),
        _render_toml,
    ),
    Site(
        "pyproject.toml",
        re.compile(r'^version = "\d+\.\d+\.\d+"$', re.MULTILINE),
        _render_toml,
    ),
    Site(
        "description.yml",
        re.compile(r"^(\s*)version:\s*\S+\s*$", re.MULTILINE),
        _render_description_yml,
    ),
    Site(
        "Cargo.lock",
        re.compile(r'(\[\[package\]\]\nname = "zarr"\nversion = )"\d+\.\d+\.\d+"'),
        _render_cargo_lock,
    ),
]


def version_from_tag(tag: str) -> str:
    match = TAG_PATTERN.fullmatch(tag)
    if not match:
        raise SystemExit(f"release tag must look like v1.2.3: {tag}")
    return match.group("version")


def read_version(site: Site, root: Path) -> str:
    text = (root / site.path).read_text(encoding="utf-8")
    match = site.pattern.search(text)
    if match is None:
        raise SystemExit(f"could not find a version line in {site.path}")
    version_match = re.search(r"\d+\.\d+\.\d+", match.group(0))
    if version_match is None:
        raise SystemExit(f"could not parse version out of {site.path}")
    return version_match.group(0)


def current_versions(root: Path) -> dict[str, str]:
    return {site.path: read_version(site, root) for site in SITES}


def rewrite(site: Site, version: str, root: Path) -> None:
    path = root / site.path
    text = path.read_text(encoding="utf-8")
    new_text, count = site.pattern.subn(
        lambda match: site.render(match, version), text, count=1
    )
    if count != 1:
        raise SystemExit(f"could not find a version line to rewrite in {site.path}")
    path.write_text(new_text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="release tag, for example v0.1.4")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the tag against the current version sites without editing",
    )
    parser.add_argument(
        "--root",
        default=str(ROOT),
        help=argparse.SUPPRESS,  # test-only escape hatch; defaults to the repo root
    )
    args = parser.parse_args()
    root = Path(args.root)

    version = version_from_tag(args.tag)

    if args.check:
        mismatches = {
            name: found for name, found in current_versions(root).items() if found != version
        }
        if mismatches:
            details = ", ".join(f"{name}={found}" for name, found in mismatches.items())
            raise SystemExit(f"tag {args.tag} does not match version sites: {details}")
        print(f"OK: tag {args.tag} matches all version sites.")
        return 0

    for site in SITES:
        rewrite(site, version, root)

    mismatches = {
        name: found for name, found in current_versions(root).items() if found != version
    }
    if mismatches:
        details = ", ".join(f"{name}={found}" for name, found in mismatches.items())
        raise SystemExit(f"rewrite verification failed: {details}")

    sites = ", ".join(site.path for site in SITES)
    print(f"tag={args.tag} version={version}: synced {sites}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
