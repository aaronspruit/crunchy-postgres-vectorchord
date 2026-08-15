# crunchy-postgres-vectorchord

Container images for [Crunchy Postgres for Kubernetes](https://access.crunchydata.com/documentation/postgres-operator) with the [VectorChord](https://github.com/supervc-stack/VectorChord) extension installed.

Two images are published for each release:

| Image | Purpose |
|---|---|
| `ghcr.io/aaronspruit/crunchy-postgres-vectorchord` | The database. Use it as `spec.image`. |
| `ghcr.io/aaronspruit/crunchy-postgres-vectorchord-upgrade` | The pg_upgrade helper. Use it as the image of a `PGUpgrade`. |

Both cover `linux/amd64` and `linux/arm64`.

## Tags

```sh
docker pull ghcr.io/aaronspruit/crunchy-postgres-vectorchord:18-1.1.1
```

| Tag | Example |
|---|---|
| `<cdpg>-<vchord>` | `ubi9-18.4-2621-1.1.1` |
| `<pg_major>-<vchord>` | `18-1.1.1` |
| `<cdpg>` | `ubi9-18.4-2621` |
| `<pg_major>` | `18` |
| `latest` | the newest Postgres major |

`<cdpg>` is the Crunchy image tag and `<vchord>` is the VectorChord version. Every tag moves to the newest matching build. Pin a digest for a reference that never moves.

Postgres 15, 16, 17 and 18 are built. That is the set of majors Crunchy supports.

> [!CAUTION]
> Do not follow `latest` for a database. It moves across Postgres majors, and a
> major version change needs a pg_upgrade. Pin `<pg_major>-<vchord>`, or pin a
> digest.

[versions.yaml](versions.yaml) lists the combinations that are built. Crunchy publishes the pg_upgrade image for the newest Postgres major alone, so the upgrade image exists for that major only.

## Use

> [!IMPORTANT]
> The Postgres configuration must load the extension. Set
> `shared_preload_libraries` in the PostgresCluster spec:
>
> ```yaml
> apiVersion: postgres-operator.crunchydata.com/v1beta1
> kind: PostgresCluster
> spec:
>   (...)
>   config:
>     parameters:
>       shared_preload_libraries: "vchord.so"
> ```
>
> On an operator older than `5.8.0`, set it here instead:
>
> ```yaml
> apiVersion: postgres-operator.crunchydata.com/v1beta1
> kind: PostgresCluster
> spec:
>   (...)
>   patroni:
>     dynamicConfiguration:
>       postgresql:
>         parameters:
>           shared_preload_libraries: "vchord.so"
> ```

> [!IMPORTANT]
> The VectorChord extension is not enabled by default. Enable it when the
> database is initialized:
>
> ```yaml
> apiVersion: v1
> kind: ConfigMap
> metadata:
>   name: enable-vchord
> data:
>   init.sql: |-
>     \c mydatabasename
>     CREATE EXTENSION IF NOT EXISTS vchord CASCADE;
> ---
> apiVersion: postgres-operator.crunchydata.com/v1beta1
> kind: PostgresCluster
> spec:
>   (...)
>   databaseInitSQL:
>     name: enable-vchord
>     key: init.sql
> ```

## Building

Pass `CDPG_TAG` and `VECTORCHORD_TAG` to build the database image:

```sh
docker build . \
  --build-arg CDPG_TAG=ubi9-18.4-2621 \
  --build-arg VECTORCHORD_TAG=1.1.1
```

Add `CDPG_IMAGE` to build the pg_upgrade image:

```sh
docker build . \
  --build-arg CDPG_IMAGE=crunchy-upgrade \
  --build-arg CDPG_TAG=ubi9-18.4-2621 \
  --build-arg VECTORCHORD_TAG=1.1.1
```

The Crunchy registry needs no account. It issues a token to an anonymous caller.

## Thanks

I shamelessly took a lot of code from [cloudnative-vectorchord](https://github.com/tensorchord/cloudnative-vectorchord) and from [budimanjojo/crunchy-postgres-vectorchord](https://github.com/budimanjojo/crunchy-postgres-vectorchord).
