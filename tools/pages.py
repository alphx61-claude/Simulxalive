"""The Jinja environment the page generators share.

One place for the autoescape rule, because getting it wrong is silent: escaping
a Markdown template turns every apostrophe into `&#39;`, and not escaping an
HTML one is an injection. Templates ending `.html.j2` are escaped; everything
else is emitted verbatim.
"""
import pathlib

from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "tools" / "templates"

PALETTE = {"void": "#000000", "bone": "#ffffff", "ash": "#9a9a9a", "silver": "#bdbdbd",
           "iris": "#8052ff", "saffron": "#ffb829", "muted": "#6a6a6a", "hair": "#1c1c1c"}


def render(template, **context):
    """Render one template from tools/templates. Unknown names are an error."""
    env = Environment(loader=FileSystemLoader(TEMPLATES),
                      autoescape=lambda name: bool(name) and name.endswith(".html.j2"),
                      undefined=StrictUndefined, keep_trailing_newline=True)
    return env.get_template(template).render(**context)
