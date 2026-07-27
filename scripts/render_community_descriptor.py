#!/usr/bin/env python3
"""Render description.yml for duckdb/community-extensions submission."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def first_match(pattern: str, text: str, label: str) -> str:
    match = re.search(pattern, text, re.MULTILINE)
    if match is None:
        raise ValueError(f"could not find {label}")
    return match.group(1)


def project_versions() -> dict[str, str]:
    return {
        "Cargo.toml": first_match(
            r'^version\s*=\s*"([^"]+)"',
            read("Cargo.toml"),
            "Cargo.toml package version",
        ),
        "pyproject.toml": first_match(
            r'^version\s*=\s*"([^"]+)"',
            read("pyproject.toml"),
            "pyproject.toml project version",
        ),
        "description.yml": first_match(
            r"^\s*version:\s*([^\s]+)\s*$",
            read("description.yml"),
            "description.yml extension version",
        ),
    }


def validate_ref(ref: str, version: str) -> None:
    if re.fullmatch(r"[0-9a-f]{40}", ref):
        return
    if re.fullmatch(r"v\d+\.\d+\.\d+", ref) and ref == f"v{version}":
        return
    raise ValueError(
        f"release ref must be a 40-character commit hash or v{version}; got {ref!r}"
    )


def validate_ref_next(ref_next: str) -> None:
    # ref_next points at the commit built for the *upcoming* DuckDB version, so
    # it is not tied to this release's version. Any immutable ref is acceptable:
    # a 40-character commit hash (the usual "latest commit of the vx.y-codename
    # branch") or a version tag.
    if re.fullmatch(r"[0-9a-f]{40}", ref_next) or re.fullmatch(
        r"v\d+\.\d+\.\d+", ref_next
    ):
        return
    raise ValueError(
        f"ref_next must be a 40-character commit hash or a vX.Y.Z tag; got {ref_next!r}"
    )


def render(ref: str, version: str, ref_next: str | None = None) -> str:
    text = read("description.yml")

    text = re.sub(
        r"^(\s*version:\s*)[^\s]+(\s*)$",
        rf"\g<1>{version}\2",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r"^(\s*)# Update ref to the tagged release commit before submitting the PR to duckdb/community-extensions\.\n",
        "",
        text,
        count=1,
        flags=re.MULTILINE,
    )

    def replace_ref(match: re.Match[str]) -> str:
        indent = match.group(1)
        rendered = f"{indent}ref: {ref}"
        if ref_next is not None:
            # ref_next sits alongside ref in the repo block, at the same indent.
            rendered += f"\n{indent}ref_next: {ref_next}"
        return rendered

    text = re.sub(
        r"^(\s*)ref:\s*[^\s#]+.*$",
        replace_ref,
        text,
        count=1,
        flags=re.MULTILINE,
    )
    return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", required=True, help="release tag or commit hash")
    parser.add_argument(
        "--ref-next",
        default=None,
        help=(
            "optional commit/tag built for the upcoming DuckDB version; emitted as "
            "repo.ref_next so the community rebuild can serve it the moment that "
            "DuckDB version is released"
        ),
    )
    parser.add_argument(
        "--out",
        required=True,
        help="output descriptor path, relative to the repository root",
    )
    args = parser.parse_args()

    versions = project_versions()
    unique_versions = set(versions.values())
    if len(unique_versions) != 1:
        details = ", ".join(f"{path}={version}" for path, version in versions.items())
        raise SystemExit(f"project versions differ: {details}")

    version = unique_versions.pop()
    try:
        validate_ref(args.ref, version)
        if args.ref_next is not None:
            validate_ref_next(args.ref_next)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(args.ref, version, args.ref_next), encoding="utf-8")
    suffix = f" (ref_next {args.ref_next})" if args.ref_next else ""
    print(f"wrote {out.relative_to(ROOT)} for zarr {version} at {args.ref}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
