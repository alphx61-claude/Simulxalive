"""Adapter mapping and paging, against trimmed sample payloads - no network."""
import asyncio
import unittest

from server.config import Config
from server.sources import get, names
from server.sources.base import SearchRequest
from server.sources.crossref import Crossref
from server.sources.openalex import OpenAlex

# Trimmed to the fields the adapters select; shapes follow each API's docs.
OPENALEX_WORK = {
    "id": "https://openalex.org/W4389012345",
    "doi": "https://doi.org/10.1073/pnas.2405460121",
    "display_name": "Evaluating  large language models in theory of mind tasks",
    "publication_year": 2024,
    "cited_by_count": 412,
    "type": "article",
    "primary_location": {"source": {"display_name": "PNAS"},
                         "landing_page_url": "https://www.pnas.org/doi/10.1073/pnas.2405460121"},
    "authorships": [{"author": {"display_name": "Michal Kosinski"}}, {"author": {}}],
    "referenced_works": ["https://openalex.org/W1", "https://openalex.org/W2"],
    "referenced_works_count": 2,
}
CROSSREF_ITEM = {
    "DOI": "10.2139/ssrn.4916298",
    "title": ["Large Model Strategic Thinking"],
    "author": [{"given": "Nunzio", "family": "Loré"}, {"name": "The Consortium"}],
    "issued": {"date-parts": [[2024, 8]]},
    "container-title": ["SSRN Electronic Journal"],
    "type": "posted-content",
    "is-referenced-by-count": 1,
    "URL": "https://doi.org/10.2139/ssrn.4916298",
    "references-count": 31,
}


class FakeFetcher:
    """Hands back queued pages and remembers what was asked for."""

    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    async def get_json(self, url, params=None, **kw):
        self.calls.append({"url": url, **(params or {})})
        return self.pages.pop(0)


def drain(source, request):
    async def go():
        return [r async for r in source.search(request)]
    return asyncio.run(go())


class TestRegistry(unittest.TestCase):
    def test_both_adapters_are_registered(self):
        self.assertEqual(names(), ["crossref", "openalex"])
        self.assertIs(get("openalex"), OpenAlex)
        self.assertIsNone(get("nope"))


class TestOpenAlexMapping(unittest.TestCase):
    def test_fields_map_across(self):
        got = OpenAlex.map(OPENALEX_WORK)
        self.assertEqual(got["source_id"], "W4389012345")
        self.assertEqual(got["title"], "Evaluating large language models in theory of mind tasks")
        self.assertEqual(got["authors"], ["Michal Kosinski"])
        self.assertEqual(got["year"], 2024)
        self.assertEqual(got["venue"], "PNAS")
        self.assertEqual(got["citations"], 412)
        self.assertEqual(got["citations_field"], "openalex.cited_by_count")
        self.assertEqual(got["references"], ["W1", "W2"])

    def test_sparse_record_yields_nulls_not_guesses(self):
        got = OpenAlex.map({"id": "https://openalex.org/W9", "display_name": "Untitled"})
        self.assertIsNone(got["year"])
        self.assertIsNone(got["venue"])
        self.assertIsNone(got["doi"])
        self.assertIsNone(got["citations"])
        self.assertEqual(got["authors"], [])


class TestCrossrefMapping(unittest.TestCase):
    def test_fields_map_across(self):
        got = Crossref.map(CROSSREF_ITEM)
        self.assertEqual(got["doi"], "10.2139/ssrn.4916298")
        self.assertEqual(got["authors"], ["Nunzio Loré", "The Consortium"])
        self.assertEqual(got["year"], 2024)
        self.assertEqual(got["venue"], "SSRN Electronic Journal")
        self.assertEqual(got["citations_field"], "crossref.is-referenced-by-count")
        self.assertEqual(got["reference_count"], 31)

    def test_year_falls_back_through_the_date_fields(self):
        self.assertEqual(Crossref.map({"published": {"date-parts": [[2019]]}})["year"], 2019)
        self.assertIsNone(Crossref.map({"title": ["x"]})["year"])


class TestTitleCleaning(unittest.TestCase):
    def test_entities_and_markup_are_resolved(self):
        item = {"title": ["Kahneman &amp; Tversky (1979) as <i>Math</i> Problems"]}
        self.assertEqual(Crossref.map(item)["title"],
                         "Kahneman & Tversky (1979) as Math Problems")

    def test_an_escaped_tag_in_a_real_title_survives(self):
        item = {"title": ["Parsing &lt;i&gt; in titles"]}
        self.assertEqual(Crossref.map(item)["title"], "Parsing <i> in titles")

    def test_whitespace_is_collapsed(self):
        self.assertEqual(OpenAlex.map({"display_name": "A  b\n c"})["title"], "A b c")


class TestPaging(unittest.TestCase):
    def test_openalex_follows_the_cursor_and_stops_at_the_limit(self):
        pages = [{"results": [OPENALEX_WORK] * 2, "meta": {"next_cursor": "c2"}},
                 {"results": [OPENALEX_WORK] * 2, "meta": {"next_cursor": "c3"}}]
        fetcher = FakeFetcher(pages)
        cfg = Config()
        got = drain(OpenAlex(fetcher, cfg), SearchRequest(query="tom", limit=3, per_page=2))
        self.assertEqual(len(got), 3)
        self.assertEqual(fetcher.calls[0]["cursor"], "*")
        self.assertEqual(fetcher.calls[1]["cursor"], "c2")
        self.assertEqual(fetcher.calls[1]["per-page"], 1)   # only one result still wanted

    def test_openalex_stops_on_an_empty_page(self):
        fetcher = FakeFetcher([{"results": [], "meta": {"next_cursor": "c2"}}])
        got = drain(OpenAlex(fetcher, Config()), SearchRequest(query="tom", limit=50))
        self.assertEqual(got, [])

    def test_openalex_year_filter(self):
        fetcher = FakeFetcher([{"results": [], "meta": {}}])
        drain(OpenAlex(fetcher, Config()),
              SearchRequest(query="tom", from_year=2015, to_year=2024, open_access_only=True))
        self.assertEqual(fetcher.calls[0]["filter"],
                         "from_publication_date:2015-01-01,to_publication_date:2024-12-31,is_oa:true")

    def test_crossref_asks_for_relevance_order(self):
        fetcher = FakeFetcher([{"message": {"items": [CROSSREF_ITEM], "next-cursor": None}}])
        got = drain(Crossref(fetcher, Config()), SearchRequest(query="tom", limit=10))
        self.assertEqual(len(got), 1)
        self.assertEqual(fetcher.calls[0]["sort"], "score")
        self.assertEqual(fetcher.calls[0]["order"], "desc")

    def test_contact_is_passed_upstream_when_set(self):
        import dataclasses
        cfg = dataclasses.replace(Config(), contact="someone@example.org")
        fetcher = FakeFetcher([{"results": [], "meta": {}}])
        drain(OpenAlex(fetcher, cfg), SearchRequest(query="tom"))
        self.assertEqual(fetcher.calls[0]["mailto"], "someone@example.org")


if __name__ == "__main__":
    unittest.main()
