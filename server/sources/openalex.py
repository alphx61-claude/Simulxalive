"""OpenAlex adapter - the source named in roadmap phase 2.

Gives metadata, a citation count and the work's reference list in one call, so
lineage edges can be proposed later without a second round of requests. Free and
open; a contact address puts us in the polite pool and an api key raises the
budget, and neither is required.
"""
from .base import PaperSource

BASE = "https://api.openalex.org/works"
FIELDS = ("id,doi,display_name,publication_year,publication_date,cited_by_count,type,"
          "primary_location,authorships,referenced_works,referenced_works_count,open_access")
MAX_PER_PAGE = 200


class OpenAlex(PaperSource):
    name = "openalex"
    label = "OpenAlex"
    docs = "https://docs.openalex.org/api-entities/works"

    async def search(self, request):
        cursor, sent = "*", 0
        while cursor and sent < request.limit:
            page = await self.fetcher.get_json(BASE, {
                "search": request.query,
                "filter": _filter(request),
                "per-page": min(MAX_PER_PAGE, request.per_page, request.limit - sent),
                "cursor": cursor,
                "select": FIELDS,
                "mailto": self.cfg.contact,
                "api_key": self.cfg.openalex_key,
            }, source=self.label)

            results = page.get("results") or []
            if not results:
                return
            for work in results:
                yield self.map(work)
                sent += 1
                if sent >= request.limit:
                    return
            cursor = (page.get("meta") or {}).get("next_cursor")

    @classmethod
    def map(cls, work):
        loc = work.get("primary_location") or {}
        venue = (loc.get("source") or {}).get("display_name")
        refs = [_short_id(r) for r in (work.get("referenced_works") or [])]
        return {
            "source_id": _short_id(work.get("id")),
            "title": cls._clean(work.get("display_name") or work.get("title")),
            "authors": [a["author"]["display_name"] for a in (work.get("authorships") or [])
                        if (a.get("author") or {}).get("display_name")],
            "year": work.get("publication_year"),
            "venue": venue,
            "url": loc.get("landing_page_url") or work.get("doi") or work.get("id"),
            "doi": work.get("doi"),
            "citations": work.get("cited_by_count"),
            "citations_field": "openalex.cited_by_count",
            "type": work.get("type"),
            "references": refs,
            "reference_count": work.get("referenced_works_count", len(refs) or None),
        }


def _filter(request):
    parts = []
    if request.from_year:
        parts.append(f"from_publication_date:{request.from_year}-01-01")
    if request.to_year:
        parts.append(f"to_publication_date:{request.to_year}-12-31")
    if request.open_access_only:
        parts.append("is_oa:true")
    return ",".join(parts) or None


def _short_id(url):
    """https://openalex.org/W2741809807 -> W2741809807"""
    return url.rsplit("/", 1)[-1] if isinstance(url, str) else None
