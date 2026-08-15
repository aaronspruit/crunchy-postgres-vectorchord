#!/usr/bin/env python3
"""Describe what changed between two versions of versions.yaml.

Writes JSON on stdout with four fields:

  postgres         the Crunchy tag changes, one entry for each major
  vectorchord      the VectorChord version changes
  dockerfile       true when the build recipe changed
  labels           the pull request labels that these changes earn
  markdown         the "What's in this release" section of the release notes

The same script serves two callers. On a pull request it supplies the labels.
On a merge it supplies the notes. One source keeps the label on a pull request
and the section in the notes from ever disagreeing.

A Dockerfile change earns its own line, because it rebuilds every image while
every version stays the same. Without that line the notes of such a release
read as though nothing happened.
"""

import argparse
import json
import re
import sys

CDPG_TAG = re.compile(r"^ubi\d+-(?P<major>\d+)\.\d+-\d+$")


def list_entries(text: str, key: str) -> list[str]:
    """Return the values of the YAML list under `key`."""
    entries = []
    inside = False
    for line in text.splitlines():
        if line.strip() == f"{key}:":
            inside = True
            continue
        if not inside:
            continue
        stripped = line.strip()
        if stripped.startswith("- "):
            entries.append(stripped[2:].strip().strip('"'))
        elif stripped and not stripped.startswith("#"):
            break
    return entries


def postgres_major(tag: str) -> str:
    match = CDPG_TAG.match(tag)
    return match["major"] if match else tag


def diff_postgres(old: list[str], new: list[str]) -> list[dict]:
    """Pair the Crunchy tags by Postgres major, so a bump is one entry."""
    old_by_major = {postgres_major(tag): tag for tag in old}
    new_by_major = {postgres_major(tag): tag for tag in new}

    changes = []
    for major in sorted(set(old_by_major) | set(new_by_major), key=int, reverse=True):
        before = old_by_major.get(major)
        after = new_by_major.get(major)
        if before == after:
            continue
        changes.append({"major": major, "from": before, "to": after})
    return changes


def diff_versions(old: list[str], new: list[str]) -> list[dict]:
    changes = []
    for version in sorted(set(new) - set(old)):
        changes.append({"from": None, "to": version})
    for version in sorted(set(old) - set(new)):
        changes.append({"from": version, "to": None})

    # One version replaced by one version is a bump, not an add and a drop.
    added = [c for c in changes if c["from"] is None]
    dropped = [c for c in changes if c["to"] is None]
    if len(added) == 1 and len(dropped) == 1:
        return [{"from": dropped[0]["from"], "to": added[0]["to"]}]
    return changes


def render(postgres: list[dict], vectorchord: list[dict], dockerfile: bool) -> str:
    lines = []

    if postgres:
        lines.append("**Postgres**")
        for change in postgres:
            if change["from"] is None:
                lines.append(f"- Postgres {change['major']} is added, at `{change['to']}`.")
            elif change["to"] is None:
                lines.append(f"- Postgres {change['major']} is dropped. It was `{change['from']}`.")
            else:
                lines.append(f"- Postgres {change['major']}: `{change['from']}` → `{change['to']}`")
        lines.append("")

    if vectorchord:
        lines.append("**VectorChord**")
        for change in vectorchord:
            if change["from"] is None:
                lines.append(f"- `{change['to']}` is added.")
            elif change["to"] is None:
                lines.append(f"- `{change['from']}` is dropped.")
            else:
                lines.append(f"- `{change['from']}` → `{change['to']}`")
        lines.append("")

    if dockerfile:
        lines.append("**Build**")
        lines.append("- The Dockerfile changed. Every image is rebuilt.")
        lines.append("")

    if not lines:
        lines = ["No version changed. Every image is rebuilt from the same sources.", ""]

    return "\n".join(lines).rstrip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("old", help="the previous versions.yaml, or - for an empty one")
    parser.add_argument("new")
    parser.add_argument("--dockerfile-changed", action="store_true")
    args = parser.parse_args()

    old_text = "" if args.old == "-" else open(args.old).read()
    new_text = open(args.new).read()

    postgres = diff_postgres(list_entries(old_text, "cdpg"), list_entries(new_text, "cdpg"))
    vectorchord = diff_versions(
        list_entries(old_text, "vectorchord"), list_entries(new_text, "vectorchord")
    )

    labels = []
    if postgres:
        labels.append("postgres")
    if vectorchord:
        labels.append("vectorchord")
    if args.dockerfile_changed:
        labels.append("build")

    json.dump(
        {
            "postgres": postgres,
            "vectorchord": vectorchord,
            "dockerfile": args.dockerfile_changed,
            "labels": labels,
            "markdown": render(postgres, vectorchord, args.dockerfile_changed),
        },
        sys.stdout,
    )
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
