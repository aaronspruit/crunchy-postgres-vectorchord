#!/usr/bin/env python3
"""Bring versions.yaml up to the policy that its header states.

The policy is every Postgres major that Crunchy supports, each at its newest
patch, and the newest VectorChord release. The set of majors is read from the
Crunchy container index rather than set here, so a new major arrives and the
oldest leaves on Crunchy's schedule.

Dependabot covers neither source. It has no ecosystem for GitHub releases, and
it reads no file that it does not recognise. This script covers both, and
.github/workflows/version-check.yml opens the pull request.

Crunchy majors and tags come from the download pages, because the registry
issues a token to an anonymous caller but refuses to list tags.

The lists are rewritten in place and every comment around them survives.
"""

import json
import re
import sys
import urllib.request

CRUNCHY_INDEX = "https://www.crunchydata.com/developers/download-postgres/containers"
CRUNCHY_PAGE = f"{CRUNCHY_INDEX}/postgresql{{major}}"
VECTORCHORD_RELEASES = "https://api.github.com/repos/supervc-stack/VectorChord/releases"

KEEP_VECTORCHORD = 1

# Cloudflare answers 403 to the default urllib user-agent.
USER_AGENT = "crunchy-postgres-vectorchord-ci"

MAJOR_LINK = re.compile(r"/developers/download-postgres/containers/postgresql(\d+)")
CDPG_TAG = re.compile(r"^ubi(?P<ubi>\d+)-(?P<major>\d+)\.(?P<minor>\d+)-(?P<build>\d+)$")
TAG_IN_PAGE = re.compile(r'"tag":"(ubi\d+-\d+\.\d+-\d+)"')
SEMVER = re.compile(r"^\d+(\.\d+)*$")


def fetch(url: str, token: str = "") -> bytes:
    headers = {"User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def tag_order(tag: str) -> tuple:
    match = CDPG_TAG.match(tag)
    if not match:
        return (0, 0, 0)
    return (int(match["ubi"]), int(match["minor"]), int(match["build"]))


def supported_majors() -> list[str]:
    """Every Postgres major that the Crunchy container index offers."""
    page = fetch(CRUNCHY_INDEX).decode("utf-8", "replace")
    majors = {int(major) for major in MAJOR_LINK.findall(page)}
    if not majors:
        raise SystemExit("The container index lists no Postgres major")
    return [str(major) for major in sorted(majors, reverse=True)]


def newest_tag(major: str) -> str:
    page = fetch(CRUNCHY_PAGE.format(major=major)).decode("utf-8", "replace")
    candidates = {
        tag for tag in TAG_IN_PAGE.findall(page) if CDPG_TAG.match(tag)["major"] == major
    }
    if not candidates:
        raise SystemExit(f"The download page for Postgres {major} lists no tag")
    return max(candidates, key=tag_order)


def version_order(version: str) -> tuple:
    return tuple(int(part) for part in version.split("."))


def newest_vectorchord(token: str = "") -> list[str]:
    releases = json.loads(fetch(VECTORCHORD_RELEASES, token))
    stable = [
        release["tag_name"].lstrip("v")
        for release in releases
        if not release["prerelease"] and not release["draft"]
    ]
    stable = [version for version in stable if SEMVER.match(version)]
    if not stable:
        raise SystemExit("VectorChord published no stable release")
    return sorted(stable, key=version_order, reverse=True)[:KEEP_VECTORCHORD]


def find_block(lines: list[str], key: str) -> tuple[int, int, list[str]]:
    """Return the start, the end, and the values of the YAML list under `key`."""
    start = None
    for number, line in enumerate(lines):
        if line.strip() == f"{key}:":
            start = number + 1
            break
    if start is None:
        raise SystemExit(f"versions.yaml has no `{key}` list")

    end = start
    values = []
    for number in range(start, len(lines)):
        stripped = lines[number].strip()
        if stripped.startswith("- "):
            values.append(stripped[2:].strip().strip('"'))
            end = number + 1
        elif not stripped or stripped.startswith("#"):
            continue
        else:
            break
    return start, end, values


def replace_block(lines: list[str], key: str, values: list[str]) -> list[str]:
    start, end, _ = find_block(lines, key)
    return lines[:start] + [f"  - {value}" for value in values] + lines[end:]


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "versions.yaml"
    token = sys.argv[2] if len(sys.argv) > 2 else ""

    with open(path) as handle:
        lines = handle.read().splitlines()

    wanted_cdpg = [newest_tag(major) for major in supported_majors()]
    wanted_vectorchord = newest_vectorchord(token)

    changes = []
    for key, wanted in (("cdpg", wanted_cdpg), ("vectorchord", wanted_vectorchord)):
        _, _, current = find_block(lines, key)
        if current == wanted:
            print(f"{key}: {', '.join(current)} matches the policy", file=sys.stderr)
            continue
        lines = replace_block(lines, key, wanted)
        changes.append(f"{key}: {', '.join(current)} -> {', '.join(wanted)}")

    if changes:
        with open(path, "w") as handle:
            handle.write("\n".join(lines) + "\n")

    print("\n".join(changes))


if __name__ == "__main__":
    main()
