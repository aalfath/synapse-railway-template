# Changelog

## v1.165.0-railway.1 (2026-11-17)

First release of the template.

- Synapse v1.165.0 (`ghcr.io/element-hq/synapse:v1.165.0@sha256:673b4223c81a7634fd07d832b939a58f97081cfdaae7cdd2d1664cdcf7611b62`) with Railway PostgreSQL.
- `homeserver.yaml` is written from the variables on every start. Extra settings go in `/data/conf.d/*.yaml`.
- The signing key, the generated secrets and the media live on the `/data` volume. The first admin account is created from the generated password.
