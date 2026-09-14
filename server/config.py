"""Server configuration: defaults, environment overrides, command-line flags.

Defaults are deliberately local-only. This backend talks to upstream APIs on
your behalf and writes into the repository, so it binds to loopback and refuses
browser origins it was not told about.
"""
import argparse
import dataclasses
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

HARD_MAX_RESULTS = 2000  # a single pull may never ask upstream for more than this


def _env_int(name, default):
    v = os.environ.get(name)
    if v is None or v.strip() == "":
        return default
    try:
        return int(v)
    except ValueError:
        raise SystemExit(f"{name} must be an integer, got {v!r}")


@dataclasses.dataclass
class Config:
    host: str = "127.0.0.1"
    port: int = 8787
    token: str | None = None
    allowed_origins: tuple[str, ...] = (
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:8000", "http://127.0.0.1:8000",
    )
    allow_any_origin: bool = False

    # Politeness. Both OpenAlex and Crossref give faster, more reliable service
    # to callers who identify themselves; neither requires it.
    contact: str | None = None
    openalex_key: str | None = None

    # Connection limits.
    max_message_bytes: int = 1 << 20
    send_queue: int = 64
    ping_interval: float = 20.0
    ping_timeout: float = 10.0

    # Job limits.
    max_jobs_per_conn: int = 2
    max_jobs_total: int = 4
    default_results: int = 100
    max_results: int = HARD_MAX_RESULTS

    # Upstream HTTP behaviour.
    request_timeout: float = 30.0
    max_attempts: int = 4
    max_backoff: float = 30.0
    max_retry_wait: float = 60.0   # a Retry-After beyond this fails the job instead
    max_response_bytes: int = 8 << 20
    rate_per_second: float = 5.0
    rate_burst: int = 5

    # Paths. The two overrides exist so tests (and a scratch run) can stage
    # somewhere other than the repository without copying data/ around.
    root: pathlib.Path = ROOT
    stage: bool = True
    data_dir_override: pathlib.Path | None = None
    ingest_dir_override: pathlib.Path | None = None

    @property
    def data_dir(self):
        return self.data_dir_override or self.root / "data"

    @property
    def ingest_dir(self):
        return self.ingest_dir_override or self.root / "data" / "ingest"

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        origins = env.get("SIMULXALIVE_WS_ORIGINS")
        kw = {
            "host": env.get("SIMULXALIVE_WS_HOST", cls.host),
            "port": _env_int("SIMULXALIVE_WS_PORT", cls.port),
            "token": env.get("SIMULXALIVE_WS_TOKEN") or None,
            "contact": env.get("SIMULXALIVE_CONTACT") or None,
            "openalex_key": env.get("SIMULXALIVE_OPENALEX_KEY") or None,
        }
        if origins:
            kw["allowed_origins"] = tuple(o.strip() for o in origins.split(",") if o.strip())
        return cls(**kw)


def parse_args(argv=None):
    cfg = Config.from_env()
    p = argparse.ArgumentParser(
        prog="python3 -m server",
        description="WebSocket backend for pulling papers into the Simulxalive corpus.",
    )
    p.add_argument("--host", default=cfg.host, help=f"bind address (default {cfg.host})")
    p.add_argument("--port", type=int, default=cfg.port, help=f"bind port (default {cfg.port})")
    p.add_argument("--token", default=cfg.token,
                   help="require ?token=... on connect (default: from SIMULXALIVE_WS_TOKEN)")
    p.add_argument("--allow-origin", action="append", default=None, metavar="ORIGIN",
                   help="browser origin to accept; repeatable")
    p.add_argument("--allow-any-origin", action="store_true",
                   help="accept any browser Origin (use only on a trusted machine)")
    p.add_argument("--contact", default=cfg.contact, metavar="EMAIL",
                   help="contact address sent to upstream APIs for the polite pool")
    p.add_argument("--no-stage", action="store_true",
                   help="stream results without writing them to data/ingest/")
    p.add_argument("--rate", type=float, default=cfg.rate_per_second, metavar="RPS",
                   help=f"upstream requests per second (default {cfg.rate_per_second})")
    a = p.parse_args(argv)

    return dataclasses.replace(
        cfg,
        host=a.host, port=a.port, token=a.token,
        allowed_origins=tuple(a.allow_origin) if a.allow_origin else cfg.allowed_origins,
        allow_any_origin=a.allow_any_origin,
        contact=a.contact, stage=not a.no_stage, rate_per_second=a.rate,
    )
