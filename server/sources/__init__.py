"""Bibliographic sources. One adapter per upstream API, one shared interface."""
from .base import PaperSource, SearchRequest
from .crossref import Crossref
from .openalex import OpenAlex

REGISTRY = {}


def register(cls):
    REGISTRY[cls.name] = cls
    return cls


def get(name):
    """Adapter class by name, or None."""
    return REGISTRY.get(name)


def names():
    return sorted(REGISTRY)


def describe():
    return [{"name": c.name, "label": c.label, "docs": c.docs} for c in
            (REGISTRY[n] for n in names())]


register(OpenAlex)
register(Crossref)

__all__ = ["PaperSource", "SearchRequest", "REGISTRY", "register", "get", "names", "describe"]
