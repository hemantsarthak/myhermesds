#!/usr/bin/env python3
"""
Ad-slot injection for both builders.

Every page template emits an empty `<div class="adslot">` and no ad script. This
module lets a network tag be dropped in without touching either builder:

    ads.json   (gitignored)
    {
      "network": "monetag",
      "head": "<script src='//...' data-zone='...'></script>",
      "slot": "<div class='adslot' id='ad-slot-1'><script>...</script></div>"
    }

If ads.json is absent the sites ship with the empty container and no tags, which
is the correct state until an account exists.
"""
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONF = ROOT / "ads.json"

_EMPTY = {
    "network": None,
    "head": "",
    "slot": '<div class="adslot" id="ad-slot-1"></div>',
}


def load() -> dict:
    if not CONF.exists():
        return dict(_EMPTY)
    try:
        data = json.loads(CONF.read_text(encoding="utf-8"))
    except Exception as exc:                                    # bad JSON must not break a build
        print(f"  warning: ads.json unreadable ({exc}) — building without tags")
        return dict(_EMPTY)
    out = dict(_EMPTY)
    out.update({k: v for k, v in data.items() if k in ("network", "head", "slot")})
    return out


ADS = load()


def head() -> str:
    """Anything that belongs inside <head> (loader scripts, meta verification)."""
    return ADS.get("head") or ""


def slot() -> str:
    """The in-page container. Empty div when no tag is configured."""
    return ADS.get("slot") or _EMPTY["slot"]


def network() -> str:
    return ADS.get("network") or "none"
