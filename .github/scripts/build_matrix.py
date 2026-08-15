#!/usr/bin/env python3
"""Expand versions.yaml into the CI build matrix.

Reads the JSON form of versions.yaml on stdin and writes a GitHub Actions
matrix on stdout. Every Crunchy tag is paired with every VectorChord version.

Three checks shape the result.

A pair is included only when VectorChord published a build for that Postgres
major. Not every release covers every major, so a pair that nobody built must
not reach the build and fail there.

A pair produces a pg_upgrade entry only when Crunchy published
`crunchy-upgrade` for that tag. Crunchy publishes it for the newest major
alone, so pairing it with every tag would fail the build for every older major
on every run.

One entry is marked `is_latest`. It carries the `latest` tag, and it is the
newest Postgres major at the newest VectorChord version.

The Crunchy registry needs no account. Its auth service issues a token to an
anonymous caller, which is enough to read a manifest, though not to list tags.
That is why the Crunchy tags come from versions.yaml.
"""

import json
import sys
import urllib.error
import urllib.request

REGISTRY = "https://registry.developers.crunchydata.com"
AUTH = "https://registry-auth.developers.crunchydata.com/auth"
UPGRADE_REPO = "crunchydata/crunchy-upgrade"
VECTORCHORD_ASSET = (
    "https://github.com/supervc-stack/VectorChord/releases/download/"
    "{version}/postgresql-{major}-vchord_{version}_x86_64-linux-gnu.zip"
)

# Cloudflare sits in front of the Crunchy hosts and answers 403 to the default
# urllib user-agent. Any ordinary-looking value gets through.
USER_AGENT = "crunchy-postgres-vectorchord-ci"

# A tag may resolve to a multi-architecture index or to a single manifest.
# Asking for only one of the two makes an existing tag look missing.
ACCEPT = ", ".join(
    [
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    ]
)


def anonymous_token(repository: str) -> str:
    url = f"{AUTH}?service=docker-registry&scope=repository:{repository}:pull"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["access_token"]


def manifest_exists(repository: str, tag: str, token: str) -> bool:
    request = urllib.request.Request(
        f"{REGISTRY}/v2/{repository}/manifests/{tag}",
        method="HEAD",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": ACCEPT,
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status == 200
    except urllib.error.HTTPError as error:
        if error.code in (401, 403, 404):
            return False
        raise


def vectorchord_build_exists(version: str, major: str) -> bool:
    """A release asset for this Postgres major. The download redirects."""
    url = VECTORCHORD_ASSET.format(version=version, major=major)
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status == 200
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise


def postgres_major(cdpg_tag: str) -> str:
    """`ubi9-18.4-2621` -> `18`. Matches the parse the Dockerfile documents."""
    try:
        return cdpg_tag.split("-")[1].split(".")[0]
    except IndexError:
        raise SystemExit(f"Cannot read a Postgres major from the tag {cdpg_tag!r}")


def version_order(version: str) -> tuple:
    return tuple(int(part) for part in version.split("."))


def main() -> None:
    versions = json.load(sys.stdin)
    cdpg_tags = versions.get("cdpg") or []
    vectorchord_versions = [str(version) for version in versions.get("vectorchord") or []]
    if not cdpg_tags or not vectorchord_versions:
        raise SystemExit("versions.yaml must list a cdpg tag and a vectorchord version")

    newest_major = max((postgres_major(tag) for tag in cdpg_tags), key=int)
    newest_vectorchord = max(vectorchord_versions, key=version_order)

    token = anonymous_token(UPGRADE_REPO)
    include = []
    for cdpg_tag in cdpg_tags:
        major = postgres_major(cdpg_tag)
        has_upgrade = manifest_exists(UPGRADE_REPO, cdpg_tag, token)
        print(
            f"{cdpg_tag}: pg{major}, upgrade image "
            f"{'found' if has_upgrade else 'not published'}",
            file=sys.stderr,
        )
        for vectorchord in vectorchord_versions:
            if not vectorchord_build_exists(vectorchord, major):
                print(
                    f"  VectorChord {vectorchord} has no build for pg{major}. Skipped.",
                    file=sys.stderr,
                )
                continue

            # `latest` follows the newest major at the newest extension version.
            is_latest = major == newest_major and vectorchord == newest_vectorchord
            common = {
                "cdpg": cdpg_tag,
                "vectorchord": vectorchord,
                "pg_major": major,
                "is_latest": is_latest,
                # The bare `<cdpg>` and `<pg_major>` tags name no extension
                # version, so only the newest one may claim them.
                "is_newest_vectorchord": vectorchord == newest_vectorchord,
            }
            include.append(
                {**common, "variant": "postgres", "base_image": "crunchy-postgres", "image_suffix": ""}
            )
            if has_upgrade:
                include.append(
                    {
                        **common,
                        "variant": "upgrade",
                        "base_image": "crunchy-upgrade",
                        "image_suffix": "-upgrade",
                    }
                )

    if not include:
        raise SystemExit("No buildable pair of Crunchy tag and VectorChord version")

    json.dump({"include": include}, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
