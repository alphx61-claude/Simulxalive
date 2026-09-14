"""Crossref adapter - DOI-registered metadata, and the fallback when OpenAlex
is out of budget or unreachable.

Crossref reports citation counts as is-referenced-by-count. It is not the same
measure as OpenAlex's cited_by_count, so the field name travels with the number.
"""
from .base import PaperSource

BASE = "https://api.crossref.org/works"
FIELDS = ("DOI,title,author,issued,container-title,type,is-referenced-by-count,URL,"
          "references-count")
MAX_ROWS = 100


class Crossref(PaperSource):
    name = "crossref"
    label = "Crossref"
    docs = "https://api.crossref.org/swagger-ui/index.html"

    async def search(self, request):
        cursor, sent = "*", 0
        while cursor and sent < request.limit:
            page = await self.fetcher.get_json(BASE, {
                "query.bibliographic": request.query,
                "filter": _filter(request),
                "rows": min(MAX_ROWS, request.per_page, request.limit - sent),
                "cursor": cursor,
                "select": FIELDS,
                # Cursor paging defaults to index order; without this the pages
                # come back in no useful order at all.
                "sort": "score",
                "order": "desc",
                "mailto": self.cfg.contact,
            }, source=self.label)

            message = page.get("message") or {}
            items = message.get("items") or []
            if not items:
                return
            for item in items:
                yield self.map(item)
                sent += 1
                if sent >= request.limit:
                    return
            cursor = message.get("next-cursor")

    @classmethod
    def map(cls, item):
        doi = item.get("DOI")
        return {
            "source_id": doi,
            "title": cls._clean(_first(item.get("title"))),
            "authors": [_name(a) for a in (item.get("author") or []) if _name(a)],
            "year": _year(item),
            "venue": cls._clean(_first(item.get("container-title"))),
            "url": item.get("URL") or (f"https://doi.org/{doi}" if doi else None),
            "doi": doi,
            "citations": item.get("is-referenced-by-count"),
            "citations_field": "crossref.is-referenced-by-count",
            "type": item.get("type"),
            "references": [],           # Crossref returns these only in the full record
            "reference_count": item.get("references-count"),
        }


def _filter(request):
    parts = []
    if request.from_year:
        parts.append(f"from-pub-date:{request.from_year}-01-01")
    if request.to_year:
        parts.append(f"until-pub-date:{request.to_year}-12-31")
    if request.open_access_only:
        parts.append("has-full-text:true")
    return ",".join(parts) or None


def _first(value):
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _name(author):
    if author.get("family"):
        return " ".join(p for p in (author.get("given"), author["family"]) if p)
    return author.get("name")


def _year(item):
    for key in ("issued", "published", "published-print", "published-online", "created"):
        parts = ((item.get(key) or {}).get("date-parts") or [[None]])[0]
        if parts and parts[0]:
            return int(parts[0])
    return None
