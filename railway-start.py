#!/usr/bin/env python
"""Railway entrypoint for Synapse.

On every start it:
  1. keeps all state on the /data volume (signing key, secrets, media, config overrides);
  2. creates a C-locale `synapse` database in the bundled Postgres if it is missing;
  3. rewrites /data/homeserver.yaml from the service variables (so variable changes apply
     on the next deploy), then loads /data/conf.d/*.yaml on top for your own settings;
  4. starts Synapse as uid 991 and, once it is healthy, creates the first admin account.
"""
import json, os, pwd, secrets, subprocess, sys, time, urllib.parse, urllib.request

DATA = os.environ.get("SYNAPSE_DATA_DIR", "/data")
UID = GID = 991
PORT = int(os.environ.get("PORT") or 8008)
CONFIG = os.path.join(DATA, "homeserver.yaml")
CONFD = os.path.join(DATA, "conf.d")
SECRETS = os.path.join(DATA, "secrets")


def log(msg):
    print(f"railway-start: {msg}", flush=True)


def env(name, default=""):
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def truthy(name, default=False):
    v = env(name, "")
    return default if v == "" else v.strip().lower() in ("1", "true", "yes", "on")


def secret_file(name):
    path = os.path.join(SECRETS, name)
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(secrets.token_urlsafe(48))
        log(f"generated {path}")
    os.chmod(path, 0o600)
    os.chown(path, UID, GID)
    return path


def ensure_database(url):
    import psycopg2
    from psycopg2 import sql

    u = urllib.parse.urlparse(url)
    dbname = env("SYNAPSE_DB_NAME", "synapse")
    args = dict(host=u.hostname, port=u.port or 5432, user=urllib.parse.unquote(u.username or ""),
                password=urllib.parse.unquote(u.password or ""), connect_timeout=10)
    admin_db = (u.path or "/").lstrip("/") or "postgres"
    for attempt in range(60):
        try:
            conn = psycopg2.connect(dbname=admin_db, **args)
            break
        except psycopg2.OperationalError as e:
            log(f"waiting for Postgres ({attempt + 1}/60): {str(e).strip().splitlines()[0]}")
            time.sleep(3)
    else:
        sys.exit("railway-start: Postgres did not answer; check the Postgres service")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
        if not cur.fetchone():
            cur.execute(sql.SQL("CREATE DATABASE {} ENCODING 'UTF8' LC_COLLATE 'C' LC_CTYPE 'C' TEMPLATE template0")
                        .format(sql.Identifier(dbname)))
            log(f"created database {dbname} (UTF8, C locale)")
    conn.close()
    a = dict(args)
    a.pop("connect_timeout")
    a.update(dbname=dbname, cp_min=5, cp_max=10, keepalives_idle=10, keepalives_interval=10, keepalives_count=3)
    return {"name": "psycopg2", "args": a}


def build_config(server_name, public_baseurl, database):
    cfg = {
        "server_name": server_name,
        "public_baseurl": public_baseurl,
        "serve_server_wellknown": True,
        "report_stats": truthy("SYNAPSE_REPORT_STATS", False),
        "web_client_location": env("SYNAPSE_WEB_CLIENT_LOCATION") or None,
        "listeners": [{
            "port": PORT, "bind_addresses": ["::"], "type": "http", "tls": False, "x_forwarded": True,
            "resources": [{"names": ["client", "federation"], "compress": False}],
        }],
        "database": database,
        "log_config": "/conf/railway-log.config",
        "media_store_path": os.path.join(DATA, "media_store"),
        "max_upload_size": env("SYNAPSE_MAX_UPLOAD_SIZE", "50M"),
        "signing_key_path": os.path.join(DATA, "signing.key"),
        "macaroon_secret_key_path": secret_file("macaroon_secret_key"),
        "form_secret_path": secret_file("form_secret"),
        "registration_shared_secret_path": secret_file("registration_shared_secret"),
        "enable_registration": truthy("SYNAPSE_ENABLE_REGISTRATION", False),
        # Open sign-up stays gated by registration tokens unless you turn that off explicitly.
        "registration_requires_token": truthy("SYNAPSE_REGISTRATION_REQUIRES_TOKEN", True),
        "url_preview_enabled": False,
        "trusted_key_servers": [{"server_name": "matrix.org"}],
        "suppress_key_server_warning": True,
    }
    if not truthy("SYNAPSE_FEDERATION_ENABLED", True):
        cfg["federation_domain_whitelist"] = []
    return {k: v for k, v in cfg.items() if v is not None}


def create_admin():
    user = env("SYNAPSE_ADMIN_USER")
    password = env("SYNAPSE_ADMIN_PASSWORD")
    marker = os.path.join(DATA, ".admin-created")
    if not user or not password or os.path.exists(marker):
        return
    if os.fork() != 0:
        return
    # Child: wait for Synapse, register the admin once, then exit.
    url = f"http://localhost:{PORT}"
    for _ in range(200):
        try:
            if urllib.request.urlopen(url + "/health", timeout=5).status == 200:
                break
        except Exception:
            pass
        time.sleep(3)
    r = subprocess.run(["register_new_matrix_user", "-c", CONFIG, "--exists-ok", "-u", user,
                        "-p", password, "-a", url], capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip().replace(password, "***")
    if r.returncode == 0:
        open(marker, "w").write(user + "\n")
        log(f"admin account @{user} ready ({out.splitlines()[-1] if out else 'ok'})")
    else:
        log(f"could not create admin @{user}: {out}")
    os._exit(0)


def main():
    server_name = env("SYNAPSE_SERVER_NAME") or env("RAILWAY_PUBLIC_DOMAIN")
    if not server_name:
        sys.exit("railway-start: set SYNAPSE_SERVER_NAME (or give the service a public domain)")
    public_baseurl = env("SYNAPSE_PUBLIC_BASEURL", f"https://{server_name}/")
    if not public_baseurl.endswith("/"):
        public_baseurl += "/"
    db_url = env("DATABASE_URL")
    if not db_url:
        sys.exit("railway-start: DATABASE_URL is missing; reference it from the Postgres service")

    for d in (DATA, SECRETS, CONFD):
        os.makedirs(d, exist_ok=True)
    if os.stat(DATA).st_uid != UID:
        log(f"setting ownership of {DATA} to {UID}:{GID}")
        subprocess.run(["chown", "-R", f"{UID}:{GID}", DATA], check=True)
    os.chmod(SECRETS, 0o700)

    name_file = os.path.join(DATA, ".server_name")
    if os.path.exists(name_file):
        old = open(name_file).read().strip()
        if old and old != server_name:
            sys.exit(f"railway-start: this volume belongs to server_name '{old}', but SYNAPSE_SERVER_NAME is "
                     f"'{server_name}'. A Matrix server name can't change after first start; set "
                     f"SYNAPSE_SERVER_NAME={old} (or start over with an empty volume and database).")
    else:
        open(name_file, "w").write(server_name + "\n")

    database = ensure_database(db_url)
    cfg = build_config(server_name, public_baseurl, database)
    with open(CONFIG, "w") as f:
        f.write("# Written by railway-start.py on every start from the service variables.\n"
                "# Don't edit this file: put your own settings in /data/conf.d/*.yaml (loaded after it).\n")
        json.dump(cfg, f, indent=2)
    for p in (DATA, CONFD, CONFIG, name_file):
        os.chown(p, UID, GID)

    args = ["--config-path", CONFIG, "--config-path", CONFD]
    if not os.path.exists(cfg["signing_key_path"]):
        log("generating the server signing key")
        subprocess.run(["gosu", f"{UID}:{GID}", sys.executable, "-m", "synapse.app.homeserver",
                        *args, "--generate-keys"], check=True)

    log(f"starting Synapse {server_name} on port {PORT} (public URL {public_baseurl})")
    create_admin()
    jemalloc = "/usr/lib/%s-linux-gnu/libjemalloc.so.2" % os.uname().machine
    if os.path.isfile(jemalloc):
        os.environ["LD_PRELOAD"] = jemalloc
    os.execv("/usr/sbin/gosu", ["gosu", f"{UID}:{GID}", sys.executable, "-m", "synapse.app.homeserver", *args])


if __name__ == "__main__":
    main()
