# check=skip=InvalidDefaultArgInFrom
# The directive above must stay on the first line, where the parser reads it.
#
# CDPG_TAG has no default on purpose. A default would let a build that forgot
# the argument produce an image of some other Postgres version and still pass.
# Without one the builder warns that the FROM line cannot resolve, which is the
# intended state, so that one check is off. A build that omits the argument
# still fails, with `invalid reference format`.

# This image adds the VectorChord extension to a Crunchy Data Postgres image.
#
# CDPG_IMAGE selects the base image. `crunchy-postgres` is the database.
# `crunchy-upgrade` is the pg_upgrade helper. This argument is the only
# difference between the two builds.
ARG CDPG_IMAGE=crunchy-postgres
ARG CDPG_TAG

FROM registry.developers.crunchydata.com/crunchydata/${CDPG_IMAGE}:${CDPG_TAG}

ARG TARGETARCH
ARG VECTORCHORD_TAG
# An ARG before FROM is out of scope after it, so CDPG_TAG needs this second
# declaration.
ARG CDPG_TAG

# Root can write to the Postgres library and share directories.
USER root

# The extension goes into every Postgres major in the image, not only the major
# that the tag names. `crunchy-postgres` holds one major, so this loop runs one
# time. `crunchy-upgrade` holds four majors, 15 to 18.
#
# pg_upgrade reads the extensions of the old cluster and of the new cluster. An
# upgrade image that carries vchord for the new major alone stops with an error
# on any database that uses the extension.
#
# VectorChord compiles against one major, so each major needs its own download.
# If a major has no build in this release, the loop skips that major. The image
# stays correct for every major that has a build.
RUN set -eu; \
    case "$TARGETARCH" in \
        amd64) URLARCH="x86_64-linux" ;; \
        arm64) URLARCH="aarch64-linux" ;; \
        *) echo "Unsupported architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac; \
    installed=0; \
    for pg_config in /usr/pgsql-*/bin/pg_config; do \
        [ -x "$pg_config" ] || continue; \
        pg_major=$("$pg_config" --version | sed -E 's/^PostgreSQL ([0-9]+).*/\1/'); \
        url="https://github.com/supervc-stack/VectorChord/releases/download/${VECTORCHORD_TAG}/postgresql-${pg_major}-vchord_${VECTORCHORD_TAG}_${URLARCH}-gnu.zip"; \
        if ! curl -fsSL --retry 3 --retry-delay 2 "$url" -o /tmp/vchord.zip; then \
            echo "No VectorChord ${VECTORCHORD_TAG} build for Postgres ${pg_major}. Skipped." >&2; \
            continue; \
        fi; \
        unzip -q /tmp/vchord.zip -d /tmp/vchord; \
        cp -r /tmp/vchord/pkglibdir/. "$("$pg_config" --pkglibdir)"; \
        cp -r /tmp/vchord/sharedir/. "$("$pg_config" --sharedir)"; \
        rm -rf /tmp/vchord.zip /tmp/vchord; \
        installed=$((installed + 1)); \
        echo "Installed VectorChord ${VECTORCHORD_TAG} for Postgres ${pg_major}."; \
    done; \
    # If the loop skips every major, the release name or the asset name changed
    # upstream. That must fail the build. An image that differs from its base by
    # a label alone is worse than no image.
    if [ "$installed" -eq 0 ]; then \
        echo "No VectorChord ${VECTORCHORD_TAG} build matched a Postgres major in this image." >&2; \
        exit 1; \
    fi

USER 26
