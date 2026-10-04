"""XSS protection: strip all HTML from user-supplied text before storing or echoing it."""

from __future__ import annotations

import html

import nh3


def strip_html(value: str) -> str:
    """Remove every tag / attribute, then unescape entities so plain text stays readable.

    Output is returned as JSON (never rendered as HTML by the API), and clients must still
    escape on render; this is defence in depth against stored XSS.
    """
    if not value:
        return value
    cleaned = nh3.clean(value, tags=set(), attributes={}, strip_comments=True)
    cleaned = html.unescape(cleaned)
    # A second pass catches entity-encoded markup such as &lt;script&gt;.
    if "<" in cleaned and ">" in cleaned:
        cleaned = html.unescape(nh3.clean(cleaned, tags=set(), attributes={}))
    return cleaned
