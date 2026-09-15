#!/usr/bin/env python3
"""Self-test for the socket layer. No network, no fixtures on disk.

    python3 tools/test_sockets.py          # or: python3 -m pytest tools/ -q

Every test runs against a throwaway copy of data/, so the real inbox and
bibliography are never touched. Modify a socket, run this: it checks routing,
identifier normalisation, dedupe and - the one that matters - that a draft with
missing bibliography fields cannot become a citation.
"""
import json
import pathlib
import shutil
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import sockets                                                    # noqa: E402
from sockets import SocketError, get, identifiers as ids, store   # noqa: E402

DATA = store.DATA                       # the real one, captured before patching


@pytest.fixture(autouse=True)
def sandbox(tmp_path, monkeypatch):
    """Point the store at a fresh copy of data/ for the duration of one test."""
    for name in ("axes.json", "sources.json"):
        shutil.copy(DATA / name, tmp_path / name)
    (tmp_path / "inbox.json").write_text(json.dumps({"submissions": []}))
    for attr, path in (("DATA", tmp_path), ("INBOX", tmp_path / "inbox.json"),
                       ("SOURCES", tmp_path / "sources.json"), ("AXES", tmp_path / "axes.json")):
        monkeypatch.setattr(store, attr, path)


def refuses(code, fn, *args, **kw):
    """Assert the layer refuses with a particular stable code, and hand it back."""
    with pytest.raises(SocketError) as caught:
        fn(*args, **kw)
    assert caught.value.code == code, f"expected {code}, got {caught.value.code}"
    return caught.value


# ------------------------------------------------------------------- routing
@pytest.mark.parametrize("raw,expected", [
    ("10.1073/pnas.2405460121", "doi"),
    ("https://doi.org/10.1038/s41562-024-01882-z", "doi"),
    ("arXiv:2303.11436", "arxiv"),
    ("https://arxiv.org/abs/2410.05229v2", "arxiv"),
    ("W2741809807", "openalex"),
    ("https://consensus.app/papers/details/cd3618ac46e15447b9a943510708dc4b/", "consensus"),
    ("https://www.nature.com/articles/s41562-024-01882-z", "link"),
])
def test_each_identifier_routes_to_its_own_socket(raw, expected):
    assert sockets.route(raw).name == expected


def test_an_unrecognisable_reference_routes_nowhere():
    refuses("unroutable", sockets.route, "a paper about theory of mind")


def test_manual_is_never_auto_routed():
    assert get("manual").detect("anything at all") == 0.0


# -------------------------------------------------------------- normalisation
def test_tracking_and_versions_normalise_away():
    a = ids.sniff("https://consensus.app/papers/details/abc123def456/?utm_source=x")
    b = ids.sniff("https://consensus.app/papers/details/abc123def456/")
    assert a["consensus"] == b["consensus"]
    assert ids.parse_arxiv("arXiv:2410.05229v3") == "2410.05229"
    assert ids.parse_doi("https://DOI.org/10.1038/ABC.2024;") == "10.1038/abc.2024"


def test_a_doi_inside_a_publisher_url_still_wins():
    ident = ids.sniff("https://www.pnas.org/doi/10.1073/pnas.2405460121")
    assert ident["doi"] == "10.1073/pnas.2405460121"
    assert "arxiv" not in ident


def test_identifier_sockets_derive_a_canonical_url():
    assert get("doi").build({"raw": "10.1073/pnas.2405460121"}).url == \
        "https://doi.org/10.1073/pnas.2405460121"
    assert get("arxiv").build({"raw": "arXiv:2303.11436"}).url == \
        "https://arxiv.org/abs/2303.11436"


# -------------------------------------------------------------------- honesty
def test_nothing_is_invented_for_a_bare_identifier():
    d = get("doi").build({"raw": "10.1073/pnas.2405460121"})
    assert (d.title, d.authors, d.year) == (None, None, None)
    assert set(d.missing) == {"title", "authors", "year", "venue"}
    assert not d.citable


def test_an_incomplete_draft_cannot_become_a_citation():
    sockets.submit({"values": {"raw": "10.1073/pnas.2405460121"}})
    e = refuses("incomplete", sockets.accept, "doi:10.1073/pnas.2405460121", by="tester")
    assert "title" in e.extra["missing"]


def test_a_complete_draft_is_accepted_with_provenance():
    sockets.submit({"socket": "manual", "submitted_by": "tester",
                    "values": {"title": "A paper that does not exist", "authors": "Nobody, A.",
                               "year": "2024", "venue": "Nowhere",
                               "url": "https://example.org/nobody-2024"}})
    result = sockets.accept("url:https://example.org/nobody-2024", by="reviewer")
    assert result["source_id"] == "nobody2024"
    provenance = store.load_sources()["sources"]["nobody2024"]["provenance"]
    assert provenance["submitted_by"] == "tester" and provenance["accepted_by"] == "reviewer"


# ------------------------------------------------------------------- refusals
def test_duplicates_are_refused_against_the_corpus():
    kosinski = "https://consensus.app/papers/details/9dde24b7c9e05c78a5c5243d6065b871/"
    assert refuses("duplicate", sockets.submit, {"values": {"raw": kosinski}}).extra["where"] \
        == "sources"


def test_duplicates_are_refused_against_the_queue():
    sockets.submit({"values": {"raw": "arXiv:2303.11436"}})
    e = refuses("duplicate", sockets.submit, {"values": {"raw": "https://arxiv.org/abs/2303.11436v2"}})
    assert e.extra["where"] == "inbox"


def test_unknown_axes_and_domains_are_refused():
    refuses("unknown_axis", sockets.submit,
            {"values": {"raw": "10.1000/x.1"}, "axes": ["no-such-axis"]})
    refuses("bad_domain", sockets.submit, {"values": {"raw": "10.1000/x.2"}, "domain": "robot"})
    refuses("field_missing", sockets.submit, {"socket": "manual", "values": {"title": "x"}})
    refuses("unknown_socket", sockets.submit, {"socket": "telepathy", "values": {"raw": "x"}})


def test_a_submission_lands_in_the_queue_as_pending():
    result = sockets.submit({"values": {"raw": "10.1000/x.3"}, "submitted_by": "tester"})
    assert result["status"] == "pending" and result["warnings"]
    assert [r["key"] for r in sockets.queue()] == ["doi:10.1000/x.3"]
    sockets.reject("doi:10.1000/x.3", reason="testing")
    assert sockets.queue() == []


# --------------------------------------------------------------- the manifest
@pytest.mark.parametrize("socket", sockets.manifest()["sockets"], ids=lambda s: s["name"])
def test_every_socket_is_fully_described(socket):
    import re
    assert socket["label"] and socket["help"] and socket["example"], "underdescribed"
    assert socket["fields"], "declares no fields"
    for pattern in socket["patterns"]:
        re.compile(pattern)                      # valid, and ECMAScript-safe by rule
        assert "(?P<" not in pattern and "(?<" not in pattern, \
            "pattern will not compile in a browser"


def test_the_manifest_covers_every_socket_and_the_common_fields():
    m = sockets.manifest()
    assert {s["name"] for s in m["sockets"]} == {"doi", "arxiv", "openalex", "consensus",
                                                 "link", "manual"}
    assert [f["name"] for f in m["common"]] == ["axes", "domain", "note", "submitted_by"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
