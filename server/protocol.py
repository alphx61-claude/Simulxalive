"""The wire protocol: what a client may say, and what the server says back.

JSON text frames, one message per frame. Every client message has a `type` and
an optional `id` that is echoed on the responses it causes. Documented in
docs/BACKEND.md - keep the two in step.
"""
import datetime
import json

from . import sources
from .errors import ProtocolError, UnknownAxis, UnknownCommand, UnknownSource

COMMANDS = ("hello", "ping", "sources.list", "corpus.axes", "pull.start", "pull.cancel",
            "jobs.list")

PULL_KEYS = {"source", "axis", "query", "side", "from_year", "to_year", "limit", "per_page",
             "include_known", "stage", "open_access"}
SIDES = ("any", "human", "machine", "bridge")

MIN_YEAR, MAX_YEAR = 1900, 2100
MAX_QUERY_CHARS = 300
MAX_PER_PAGE = 200


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def event(type_, **fields):
    return {"type": type_, "ts": now(), **fields}


def error_event(err, request_id=None):
    e = event("error", error=err.payload())
    if request_id is not None:
        e["id"] = request_id
    return e


def parse(text):
    """(type, id, params) from a raw client frame."""
    try:
        message = json.loads(text)
    except json.JSONDecodeError as e:
        raise ProtocolError(f"message is not json: {e}")
    if not isinstance(message, dict):
        raise ProtocolError("message must be a json object")

    request_id = message.get("id")
    if request_id is not None and not isinstance(request_id, (str, int)):
        raise ProtocolError("'id' must be a string or a number")

    type_ = message.get("type")
    if not isinstance(type_, str):
        raise ProtocolError("message needs a string 'type'", request_id=request_id)
    if type_ not in COMMANDS:
        raise UnknownCommand(f"unknown command {type_!r}", request_id=request_id,
                             detail={"known": list(COMMANDS)})

    params = message.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ProtocolError("'params' must be an object")
    return type_, request_id, params


# ------------------------------------------------------------------ validation
def _int(params, key, default, low, high):
    value = params.get(key, default)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolError(f"'{key}' must be an integer")
    if not low <= value <= high:
        raise ProtocolError(f"'{key}' must be between {low} and {high}")
    return value


def _bool(params, key, default):
    value = params.get(key, default)
    if not isinstance(value, bool):
        raise ProtocolError(f"'{key}' must be true or false")
    return value


def _str(params, key, default=None, max_chars=MAX_QUERY_CHARS):
    value = params.get(key, default)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProtocolError(f"'{key}' must be a string")
    value = value.strip()
    if not value:
        raise ProtocolError(f"'{key}' must not be empty")
    if len(value) > max_chars:
        raise ProtocolError(f"'{key}' must be under {max_chars} characters")
    return value


def validate_pull(params, cfg, corpus):
    """Normalise pull.start parameters, or say exactly what is wrong with them."""
    unknown = set(params) - PULL_KEYS
    if unknown:
        raise ProtocolError(f"unknown parameter(s): {', '.join(sorted(unknown))}",
                            detail={"accepted": sorted(PULL_KEYS)})

    source = _str(params, "source", "openalex", max_chars=40)
    if sources.get(source) is None:
        raise UnknownSource(f"no source named {source!r}", detail={"sources": sources.names()})

    axis = _str(params, "axis", None, max_chars=80)
    query = _str(params, "query", None)
    if not axis and not query:
        raise ProtocolError("give an 'axis' to search for, a 'query', or both")
    if axis and corpus.axis(axis) is None:
        raise UnknownAxis(f"no axis named {axis!r}", detail={"axes": corpus.axis_ids})

    side = _str(params, "side", "any", max_chars=10)
    if side not in SIDES:
        raise ProtocolError(f"'side' must be one of {', '.join(SIDES)}")

    from_year = _int(params, "from_year", None, MIN_YEAR, MAX_YEAR)
    to_year = _int(params, "to_year", None, MIN_YEAR, MAX_YEAR)
    if from_year and to_year and from_year > to_year:
        raise ProtocolError("'from_year' is after 'to_year'")

    limit = _int(params, "limit", cfg.default_results, 1, cfg.max_results)
    per_page = _int(params, "per_page", min(50, limit), 1, MAX_PER_PAGE)

    return {
        "source": source, "axis": axis, "query": query, "side": side,
        "from_year": from_year, "to_year": to_year,
        "limit": limit, "per_page": min(per_page, limit),
        "include_known": _bool(params, "include_known", False),
        "stage": _bool(params, "stage", cfg.stage),
        "open_access": _bool(params, "open_access", False),
    }


def _relative(path, root):
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def hello(cfg, corpus, version):
    return {
        "server": "simulxalive-ingest",
        "version": version,
        "commands": list(COMMANDS),
        "sources": sources.describe(),
        "corpus": {"axes": len(corpus.axes), "sources": len(corpus.sources)},
        "limits": {
            "max_results": cfg.max_results,
            "default_results": cfg.default_results,
            "max_per_page": MAX_PER_PAGE,
            "max_jobs_per_connection": cfg.max_jobs_per_conn,
            "max_message_bytes": cfg.max_message_bytes,
        },
        "staging": {"enabled": cfg.stage, "dir": _relative(cfg.ingest_dir, cfg.root)},
        "contact_set": bool(cfg.contact),
    }
