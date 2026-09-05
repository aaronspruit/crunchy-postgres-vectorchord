# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when it works in this repository.

## Mandatory rules

These rules are not optional. They apply to every change.

<!-- harness:rules:begin -->
Written by harness from rules/. Do not edit between these two markers.
https://github.com/aaronspruit/harness

### Write in Simplified Technical English

Write all documentation in Simplified Technical English (ASD-STE100). This
covers the README, the agent instruction file, comments and docstrings, commit
messages, pull request titles and bodies, release notes, and each message that a
person reads. Apply the rules before you draft, and not after.

The standard is free at https://asd-ste100.org. If the session holds the
`simple-english` skill, invoke it first.

### Keep breaking-change detail in the pull request

Do not put migration steps, upgrade instructions, or "this breaks X" in the
README or in the agent instruction file. Put them in the pull request body. If
the repository uses `changelog:` labels, apply the correct one. That label
carries the detail into the release notes.

The README and the agent instruction file describe how the code works now. The
release notes are the only record of what changed. A design note can say why the
current behavior exists. It must not tell a user what to do about an older
install.

### Write comments about the present, not the past

A comment says what the current code does, and why. It does not say what the
code replaced, or what an older version did. `git log` and `git blame` hold
that, and a stale "X still serves Y" line is wrong the moment Y changes.

When you migrate something, write the new file as if it was always that way.
Strip the same kind of history out of every file that the change touches. The
migration story goes in the commit message and in the pull request.

### Write the fewest sentences that carry the fact

State each fact in one place, and link to that place from anywhere else that
needs it. Do not repeat what a linked file already says. Do not write a
preamble, a list of what comes next, or a closing restatement. If a section
changes nothing about what the reader does, delete the section instead of
shortening it.

### Give the recommendation first

When the work needs a decision, or when you compare options, write the
recommendation in the first sentence. Then give the reasons. Then give the one
fact that argues against it. Do not spread the recommendation through the
analysis. Do not end with a list of options and no choice.

This rule applies to an answer in a session, to a pull request body, and to a
design document.

### Write what you find back to the issue

When you read an issue to plan work, add a comment to that issue. Add a second
comment when you make a branch for it. The comment holds what you decided, why,
what the work covers, and what it leaves out. It holds no install step. Those go
in the pull request, under the rule for breaking changes.

When a later finding changes the answer, comment again. Do not leave the old
comment standing alone. An issue that carries no comment makes the next session
do the same research again.
<!-- harness:rules:end -->

## What this repository is

It builds container images. It holds no application code. [Dockerfile](Dockerfile) copies the [VectorChord](https://github.com/supervc-stack/VectorChord) extension into a [Crunchy Data](https://www.crunchydata.com/developers) Postgres image, and [versions.yaml](versions.yaml) states which combinations exist. Every other file serves those two.

There is no test suite. The build is the test, and the smoke test in [.github/workflows/ci.yml](.github/workflows/ci.yml) is the assertion.

## Commands

```bash
# Build the database image for one combination
docker build . \
  --build-arg CDPG_TAG=ubi9-18.4-2621 \
  --build-arg VECTORCHORD_TAG=1.1.1

# Build the pg_upgrade image for the same combination
docker build . \
  --build-arg CDPG_IMAGE=crunchy-upgrade \
  --build-arg CDPG_TAG=ubi9-18.4-2621 \
  --build-arg VECTORCHORD_TAG=1.1.1

# Print the build matrix that CI derives from versions.yaml
yq -o=json -I=0 versions.yaml | python3 .github/scripts/build_matrix.py | python3 -m json.tool

# Bring versions.yaml up to the policy
python3 .github/scripts/check_versions.py versions.yaml

# Print the labels and the release notes for a change to versions.yaml
python3 .github/scripts/version_diff.py old-versions.yaml versions.yaml --dockerfile-changed
```

The Crunchy registry needs no account for any of this. Its auth service issues a token to an anonymous caller.

## The Dockerfile

One file builds both images. `CDPG_IMAGE` selects the base: `crunchy-postgres` is the database and `crunchy-upgrade` is the pg_upgrade helper.

**The extension is installed into every Postgres major in the image, not into the major that the tag names.** `crunchy-postgres` holds one major. `crunchy-upgrade` holds four, 15 through 18. pg_upgrade reads the extensions of the old cluster as well as the new one, so an upgrade image that carries the extension for the target major alone fails on any database that uses VectorChord. That is every database this repository serves. The loop over `/usr/pgsql-*/bin/pg_config` is the whole point of the build, not a convenience.

A major with no VectorChord release for the requested version is skipped, and the build still succeeds. A build where **no** major matched fails, because that means the upstream release name or asset name changed and the image would differ from its base by a label alone.

## Versions

[versions.yaml](versions.yaml) is the only place that decides which images exist. Every `cdpg` tag is paired with every `vectorchord` version.

The policy is every Postgres major that Crunchy supports, each at its newest patch, and the newest VectorChord release. Crunchy supports four majors at a time.

**Crunchy publishes no image for Postgres 14.** Its download page for that major returns 404 and its registry holds no tag. Postgres 14 cannot be served from this base image, whatever `versions.yaml` says.

- [.github/scripts/check_versions.py](.github/scripts/check_versions.py) rewrites both lists to match the policy. It reads the set of majors from the Crunchy container index, so a new major arrives and the oldest leaves on Crunchy's schedule and not on one set here.
- Crunchy tags come from the download page of each major, because the registry issues an anonymous token but refuses to list tags.
- [.github/scripts/build_matrix.py](.github/scripts/build_matrix.py) expands the file into the CI matrix and drops a pair that cannot be built. It asks the registry whether `crunchy-upgrade:<tag>` exists, because **Crunchy publishes the upgrade image for the newest major alone**. It asks GitHub whether VectorChord published a build for that Postgres major, because a release does not always cover every major. Either guess fails the build on the day the answer changes.
- One entry is marked `is_latest`, and one for each major is marked `is_newest_vectorchord`. Those two flags decide which cell may claim a tag that names no extension version. Two cells claiming `18` would race, and the winner would be whichever job finished last.

## Dependencies

Dependabot handles GitHub Actions and nothing else. It has no ecosystem for GitHub releases, so it cannot follow VectorChord. It reads no file that it does not recognize, so it cannot follow `versions.yaml`. The base image comes from a build argument, so there is no `FROM` line for it to parse either. [.github/workflows/version-check.yml](.github/workflows/version-check.yml) covers the two dependencies that Dependabot cannot.

A pull request that `GITHUB_TOKEN` opens starts no other workflow. Version-check therefore uses a `VERSIONS_PR_TOKEN` secret when one exists, so that CI/CD builds its proposal. Without that secret, close and reopen the pull request to start CI/CD.

## CI/CD

[.github/workflows/ci.yml](.github/workflows/ci.yml) runs on pull requests and on pushes to `main`. It holds four jobs.

- `configure` builds the matrix. On a merge it also plans the release: whether to cut one, the version, and the notes.
- `label` runs on a pull request only. It labels the pull request `postgres`, `vectorchord` or `build`, from the same diff that writes the release notes, so a label and a section can never disagree.
- `build` runs one job for each image. A pull request builds every image, scans it and pushes nothing. A merge that earns a release pushes.
- `release` creates the tag and publishes the release.

**A pull request verifies the build.** It builds both architectures, then loads the amd64 image from the same cache to smoke test and scan it. Nothing is pushed.

Trivy reports and never fails a build. Every finding belongs to the Crunchy base image, which this repository cannot patch. The answer to one is a newer Crunchy tag, which version-check already proposes. The findings go to code scanning so that they stay visible.

## Releases

**A merge to `main` that changed `versions.yaml` or the `Dockerfile` builds, pushes and releases on its own.** A merge that changed neither builds nothing, because the images would be identical. The comparison runs against the last release rather than the last commit, so two merges between releases both reach the notes.

The version is CalVer, `vYYYY.MM.DD`, with a `.N` suffix for a second release on the same day. It is a serial number for the changelog. Nothing pins to it, because consumers pin an image tag or a digest.

The version is known before the build, so each image carries its final tags at once and nothing is retagged afterwards:

| Tag | Example | Claimed by |
|---|---|---|
| `<cdpg>-<vchord>` | `ubi9-18.4-2621-1.1.1` | every cell |
| `<pg_major>-<vchord>` | `18-1.1.1` | every cell |
| `<cdpg>` | `ubi9-18.4-2621` | the newest VectorChord version |
| `<pg_major>` | `18` | the newest VectorChord version |
| `latest` | | the newest major at the newest VectorChord version |

The notes open with a section that [.github/scripts/version_diff.py](.github/scripts/version_diff.py) writes. It names only what changed, so a Postgres-only release lists Postgres alone. **A Dockerfile change earns its own line**, because it rebuilds every image while every version stays the same, and the notes would otherwise read as though nothing happened. [.github/release.yml](.github/release.yml) groups the merged pull requests under that section.
