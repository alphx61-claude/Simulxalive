"""The contract every adapter meets, so the job loop never knows which API it hit."""
import dataclasses
import html
import re

_TAG = re.compile(r"<[^>]+>")


@dataclasses.dataclass(frozen=True)
class SearchRequest:
    """One discovery query, as the job loop states it."""

    query: str
    from_year: int | None = None
    to_year: int | None = None
    limit: int = 100
    per_page: int = 50
    open_access_only: bool = False

    def replace(self, **kw):
        return dataclasses.replace(self, **kw)


class PaperSource:
    """Adapter interface.

    `search` is an async generator of normalised records. Each record uses the
    keys `source_id, title, authors, year, venue, url, doi, citations,
    citations_field, type, references, reference_count`; anything the upstream
    does not report is None rather than guessed.
    """

    name = "base"
    label = "Base"
    docs = ""

    def __init__(self, fetcher, cfg):
        self.fetcher = fetcher
        self.cfg = cfg

    async def search(self, request):
        raise NotImplementedError

    @staticmethod
    def _clean(text):
        """Titles arrive with markup and entities in them; a reviewer wants prose.

        Tags first, then entities: an escaped &lt;i&gt; in a real title survives.
        """
        if not isinstance(text, str):
            return text
        return " ".join(html.unescape(_TAG.sub(" ", text)).split())
