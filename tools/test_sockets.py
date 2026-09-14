#!/usr/bin/env python3
"""Self-test for the socket layer. No dependencies, no network, no fixtures.

    python3 tools/test_sockets.py

Runs against a temporary copy of data/, so it never touches the real inbox or
bibliography. Modify a socket, run this: it checks routing, identifier
normalisation, dedupe and - the one that matters - that a draft with missing
bibliography fields cannot become a citation.
"""
import json
import pathlib
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


def sandbox():
    """Point the store at a throwaway copy of data/."""
    from sockets import store
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="sockets-test-"))
    shutil.copy(store.DATA / "axes.json", tmp / "axes.json")
    shutil.copy(store.DATA / "sources.json", tmp / "sources.json")
    (tmp / "inbox.json").write_text(json.dumps({"submissions": []}))
    store.DATA, store.INBOX = tmp, tmp / "inbox.json"
    store.SOURCES, store.AXES = tmp / "sources.json", tmp / "axes.json"
    return tmp


def raises(code, fn, *args, **kw):
    from sockets import SocketError
    try:
        fn(*args, **kw)
    except SocketError as e:
        assert e.code == code, f"expected {code}, got {e.code}: {e.message}"
        return e
    raise AssertionError(f"expected SocketError[{code}], nothing raised")


# ------------------------------------------------------------------- routing
@check
def routes_each_identifier_to_its_own_socket():
    import sockets
    cases = {
        "10.1073/pnas.2405460121": "doi",
        "https://doi.org/10.1038/s41562-024-01882-z": "doi",
        "arXiv:2303.11436": "arxiv",
        "https://arxiv.org/abs/2410.05229v2": "arxiv",
        "W2741809807": "openalex",
        "https://consensus.app/papers/details/cd3618ac46e15447b9a943510708dc4b/": "consensus",
        "https://www.nature.com/articles/s41562-024-01882-z": "link",
    }
    for raw, expected in cases.items():
        got = sockets.route(raw).name
        assert got == expected, f"{raw!r} routed to {got}, expected {expected}"
    raises("unroutable", sockets.route, "a paper about theory of mind")


@check
def manual_is_never_auto_routed():
    from sockets import get
    assert get("manual").detect("anything at all") == 0.0


# ---------------------------------------------------------- normalisation
@check
def tracking_and_versions_normalise_away():
    from sockets import identifiers as I
    a = I.sniff("https://consensus.app/papers/details/abc123def456/?utm_source=x")
    b = I.sniff("https://consensus.app/papers/details/abc123def456/")
    assert a["consensus"] == b["consensus"]
    assert I.parse_arxiv("arXiv:2410.05229v3") == "2410.05229"
    assert I.parse_doi("https://DOI.org/10.1038/ABC.2024;") == "10.1038/abc.2024"


@check
def a_doi_inside_a_publisher_url_still_wins():
    from sockets import identifiers as I
    ident = I.sniff("https://www.pnas.org/doi/10.1073/pnas.2405460121")
    assert ident["doi"] == "10.1073/pnas.2405460121"
    assert "arxiv" not in ident


@check
def identifier_sockets_derive_a_canonical_url():
    from sockets import get
    d = get("doi").build({"raw": "10.1073/pnas.2405460121"})
    assert d.url == "https://doi.org/10.1073/pnas.2405460121"
    assert get("arxiv").build({"raw": "arXiv:2303.11436"}).url == \
        "https://arxiv.org/abs/2303.11436"


# ------------------------------------------------------------------ honesty
@check
def nothing_is_invented_for_a_bare_identifier():
    from sockets import get
    d = get("doi").build({"raw": "10.1073/pnas.2405460121"})
    assert d.title is None and d.authors is None and d.year is None
    assert set(d.missing) == {"title", "authors", "year", "venue"}
    assert not d.citable


@check
def an_incomplete_draft_cannot_become_a_citation():
    import sockets
    sandbox()
    sockets.submit({"values": {"raw": "10.1073/pnas.2405460121"}})
    e = raises("incomplete", sockets.accept, "doi:10.1073/pnas.2405460121", by="tester")
    assert "title" in e.extra["missing"]


@check
def a_complete_draft_is_accepted_with_provenance():
    import sockets
    from sockets import store
    sandbox()
    sockets.submit({"socket": "manual", "submitted_by": "tester",
                    "values": {"title": "A paper that does not exist",
                               "authors": "Nobody, A.", "year": "2024",
                               "venue": "Nowhere",
                               "url": "https://example.org/nobody-2024"}})
    result = sockets.accept("url:https://example.org/nobody-2024", by="reviewer")
    assert result["source_id"] == "nobody2024"
    entry = store.load_sources()["sources"]["nobody2024"]
    assert entry["provenance"]["submitted_by"] == "tester"
    assert entry["provenance"]["accepted_by"] == "reviewer"


# ------------------------------------------------------------------- refusals
@check
def duplicates_are_refused_against_corpus_and_inbox():
    import sockets
    sandbox()
    kosinski = "https://consensus.app/papers/details/9dde24b7c9e05c78a5c5243d6065b871/"
    e = raises("duplicate", sockets.submit, {"values": {"raw": kosinski}})
    assert e.extra["where"] == "sources"

    sockets.submit({"values": {"raw": "arXiv:2303.11436"}})
    e = raises("duplicate", sockets.submit, {"values": {"raw": "https://arxiv.org/abs/2303.11436v2"}})
    assert e.extra["where"] == "inbox"


@check
def unknown_axes_and_domains_are_refused():
    import sockets
    sandbox()
    raises("unknown_axis", sockets.submit,
           {"values": {"raw": "10.1000/x.1"}, "axes": ["no-such-axis"]})
    raises("bad_domain", sockets.submit,
           {"values": {"raw": "10.1000/x.2"}, "domain": "robot"})
    raises("field_missing", sockets.submit, {"socket": "manual", "values": {"title": "x"}})
    raises("unknown_socket", sockets.submit, {"socket": "telepathy", "values": {"raw": "x"}})


@check
def a_submission_lands_in_the_queue_as_pending():
    import sockets
    sandbox()
    r = sockets.submit({"values": {"raw": "10.1000/x.3"}, "submitted_by": "tester"})
    assert r["status"] == "pending" and r["warnings"]
    q = sockets.queue()
    assert len(q) == 1 and q[0]["key"] == "doi:10.1000/x.3"
    sockets.reject("doi:10.1000/x.3", reason="testing")
    assert sockets.queue() == []


# -------------------------------------------------------------- the manifest
@check
def the_manifest_describes_every_socket_completely():
    import re
    import sockets
    m = sockets.manifest()
    assert {s["name"] for s in m["sockets"]} == {"doi", "arxiv", "openalex",
                                                 "consensus", "link", "manual"}
    for s in m["sockets"]:
        assert s["label"] and s["help"] and s["example"], f"{s['name']} is underdescribed"
        assert s["fields"], f"{s['name']} declares no fields"
        for pattern in s["patterns"]:
            re.compile(pattern)                     # valid, and ECMAScript-safe by rule
            assert "(?P<" not in pattern and "(?<" not in pattern, \
                f"{s['name']}: pattern will not compile in a browser"
    assert [f["name"] for f in m["common"]] == ["axes", "domain", "note", "submitted_by"]


def main():
    failed = 0
    for fn in CHECKS:
        try:
            fn()
            print(f"pass  {fn.__name__.replace('_', ' ')}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {fn.__name__.replace('_', ' ')}\n      {e}")
    print(f"\n{len(CHECKS) - failed}/{len(CHECKS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
