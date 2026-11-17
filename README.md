[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/template/synapse-1?utm_medium=integration&utm_source=button&utm_campaign=synapse)

# Synapse on Railway

A Railway template for [Synapse](https://github.com/element-hq/synapse), the Matrix homeserver by Element. It runs Synapse **v1.165.0** from the official image `ghcr.io/element-hq/synapse:v1.165.0`, pinned by digest in the [`Dockerfile`](Dockerfile), with Railway's PostgreSQL.

## What it deploys

| Service | Source | State |
|---|---|---|
| **Synapse** | this repo (`Dockerfile` + `railway-start.py`) | volume at `/data`: signing key, generated secrets, uploaded media, your config overrides |
| **Postgres** | Railway's PostgreSQL image | volume at `/var/lib/postgresql/data` |

On every start, `railway-start.py`:

1. creates a `synapse` database with the UTF-8/C locale that Synapse requires (once);
2. generates the signing key and the macaroon, form and registration secrets on the volume (once) and keeps them;
3. writes `/data/homeserver.yaml` from the service variables, so changing a variable and redeploying applies it; it then loads `/data/conf.d/*.yaml` for your own settings;
4. listens on `PORT` (8008) behind Railway's HTTPS domain and serves `/.well-known/matrix/server` and `/.well-known/matrix/client`, so federation works over port 443 without a reverse proxy;
5. creates the first admin account from `SYNAPSE_ADMIN_USER` and the generated `SYNAPSE_ADMIN_PASSWORD` (once).

The health check is `/health`.

## Variables

| Variable | Default | Notes |
|---|---|---|
| `SYNAPSE_SERVER_NAME` | `${{RAILWAY_PUBLIC_DOMAIN}}` | Matrix server name, the `:domain` part of every user ID. **It can't change after the first start.** To use your own domain, set it before the first deploy (and add the custom domain to the service). |
| `SYNAPSE_PUBLIC_BASEURL` | `https://${{RAILWAY_PUBLIC_DOMAIN}}/` | URL clients and other servers use to reach Synapse |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | Postgres connection; the `synapse` database is created next to it |
| `SYNAPSE_ADMIN_USER` | `admin` | First admin's username |
| `SYNAPSE_ADMIN_PASSWORD` | generated | First admin's password; read it in the service's Variables tab |
| `SYNAPSE_ENABLE_REGISTRATION` | `false` | Allow sign-up from Matrix clients. Sign-up then still needs a registration token unless `SYNAPSE_REGISTRATION_REQUIRES_TOKEN=false` |
| `PORT` | `8008` | Port Synapse listens on |

Optional, not set by the template: `SYNAPSE_REGISTRATION_REQUIRES_TOKEN` (default `true`), `SYNAPSE_FEDERATION_ENABLED` (default `true`), `SYNAPSE_MAX_UPLOAD_SIZE` (default `50M`), `SYNAPSE_REPORT_STATS` (default `false`), `SYNAPSE_WEB_CLIENT_LOCATION`. Anything else (SMTP, OAuth/OIDC, TURN, URL previews) goes in a YAML file under `/data/conf.d/`; see the [Synapse configuration manual](https://element-hq.github.io/synapse/latest/usage/configuration/config_documentation.html).

## After deploy

1. Open `https://YOUR-DOMAIN/health`: it answers `OK`.
2. In a Matrix client (Element at app.element.io, Cinny, FluffyChat), choose another homeserver, enter `https://YOUR-DOMAIN`, and sign in as `admin` with the password from the Synapse service's Variables tab.
3. To add users, create them with the [admin API](https://element-hq.github.io/synapse/latest/admin_api/user_admin_api.html), or set `SYNAPSE_ENABLE_REGISTRATION=true` and hand out [registration tokens](https://element-hq.github.io/synapse/latest/usage/administration/admin_api/registration_tokens.html).
4. Check federation at [federationtester.matrix.org](https://federationtester.matrix.org/).

## Updates

The upstream image is pinned by version and digest in the `Dockerfile`. When a new Synapse release comes out, we bump the pin on `main` and add an entry to [`CHANGELOG.md`](CHANGELOG.md). Railway then shows an "update available" notice in projects deployed from the template, and you choose when to apply it. Synapse runs its database migrations on start. Read the changelog first: breaking changes are listed at the top of each entry.

## Local test

`docker compose -f compose.test.yaml up --build` runs the same two services on `localhost:42493` (the server name there is `synapse.local.test`).

## Licence

The wrapper in this repo is MIT. Synapse is AGPL-3.0 (element-hq/synapse).
