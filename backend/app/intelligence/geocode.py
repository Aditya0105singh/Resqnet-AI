"""Landmark → node resolution against a gazetteer. Never guesses.

* exact      one landmark (or the only matches all point to one node)
* ambiguous  several places match: a bridge has two banks, "പള്ളി" is a church or a mosque
* area       only a neighbourhood is named: candidates are its land nodes
* none       nothing usable ("near the river")

Only `exact` carries a node, and even then the location is *inferred*, not verified:
the dispatcher confirms it before anything is dispatched.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from functools import lru_cache
from typing import Any, Optional

from .schema import Geocode

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "geographic", "riverbend_gazetteer.json")


# chillu letters become full consonants under inflection; ർ can surface as ര or റ (മിയർ → മിയറിൽ)
CHILLU = {"\u0d7a": ("\u0d23",), "\u0d7b": ("\u0d28",), "\u0d7c": ("\u0d30", "\u0d31"), "\u0d7d": ("\u0d32",), "\u0d7e": ("\u0d33",)}  # ൺ ൻ ർ ൽ ൾ


def phrase_in(text_l: str, phrase: str) -> bool:
    """Match a lexicon phrase or alias in lower-cased, NFC-normalised text.

    English: whole-word match. Indic scripts: substring, after NFC (Devanagari nukta
    letters decompose under NFC, so both sides must be normalised the same way).
    Malayalam is agglutinative, so a phrase ending in virama (്), anusvara (ം) or a
    chillu letter also matches its inflected stem: ടെറസ് → ടെറസിൽ, ക്ഷേത്രം →
    ക്ഷേത്രത്തിന്റെ, ഹാൾ → ഹാളിന്.
    """
    a = unicodedata.normalize("NFC", phrase).lower()
    if a.isascii():
        return re.search(r"(?<![a-z])" + re.escape(a) + r"(?![a-z])", text_l) is not None
    if a in text_l:
        return True
    if len(a) > 3:
        if a[-1] in ("\u0d4d", "\u0d02"):
            return a[:-1] in text_l
        if a[-1] in CHILLU:
            return any(a[:-1] + full in text_l for full in CHILLU[a[-1]])
    return False


_found = phrase_in


class Gazetteer:
    def __init__(self, data: dict[str, Any], bridge_ends: dict[str, list[str]], area_nodes: dict[str, list[str]]):
        self.data = data
        self.bridge_ends = bridge_ends
        self.area_nodes = area_nodes
        self.synthetic = bool(data.get("synthetic"))

    @classmethod
    def for_world(cls, world: Any, path: str = DEFAULT_PATH) -> "Gazetteer":
        meta = getattr(world, "meta", {}) or {}
        if meta.get("geography") and meta.get("geography") != "riverbend":
            # an OSM city: landmarks and their multilingual aliases come from OSM name tags
            data = {
                "synthetic": meta.get("synthetic", False),
                "landmarks": [{"id": l["id"], "name": l["name"], "node": l["node"], "aliases": sorted({l["name"], *l.get("aliases", [])})} for l in meta.get("landmarks", []) if l["node"] in world.nodes],
                "bridges": [{"edge": e.id, "aliases": [e.name]} for e in world.edges.values() if e.kind == "bridge" and e.name],
                "areas": [{"neighbourhood": z.id, "aliases": [z.name]} for z in world.neighbourhoods.values()],
            }
        else:
            data = _load(os.path.abspath(path))
        ends = {e.id: sorted([e.u, e.v]) for e in world.edges.values() if e.kind == "bridge"}
        areas: dict[str, list[str]] = {}
        for n in world.nodes.values():
            if n.kind == "land":
                areas.setdefault(n.neighbourhood, []).append(n.id)
        return cls(data, ends, {k: sorted(v) for k, v in areas.items()})

    def _matches(self, text_l: str) -> list[tuple[str, str, list[str]]]:
        """(kind, display name, candidate nodes), longest alias wins inside overlapping matches."""
        hits: list[tuple[int, str, str, list[str]]] = []
        for lm in self.data["landmarks"]:
            for a in lm["aliases"]:
                if _found(text_l, a):
                    hits.append((len(a), "landmark", lm["name"], [lm["node"]]))
        for br in self.data["bridges"]:
            for a in br["aliases"]:
                if _found(text_l, a):
                    hits.append((len(a), "bridge", br["aliases"][0].title(), self.bridge_ends.get(br["edge"], [])))
        return [(k, name, nodes) for _l, k, name, nodes in sorted(hits, key=lambda h: -h[0])]

    def first_alias(self, text_l: str) -> Optional[str]:
        best = None
        for group in [lm["aliases"] for lm in self.data["landmarks"]] + [b["aliases"] for b in self.data["bridges"]] + [a["aliases"] for a in self.data["areas"]]:
            for a in group:
                if _found(text_l, a) and (best is None or len(a) > len(best)):
                    best = a
        return best

    def resolve(self, text_l: str) -> Geocode:
        hits = self._matches(text_l)
        if hits:
            # keep only the most specific match length: "st thomas church" beats "church"
            names: list[str] = []
            nodes: list[str] = []
            longest = {}
            for kind, name, cand in hits:
                for n in cand:
                    if n not in nodes:
                        nodes.append(n)
                if name not in names:
                    names.append(name)
                longest.setdefault(kind, name)
            # a specific (multi-word) alias for one landmark overrides generic words that also matched
            specific = [lm for lm in self.data["landmarks"] if any(_found(text_l, a) and (" " in a or not a.isascii()) and sum(1 for o in self.data["landmarks"] if a in o["aliases"]) == 1 for a in lm["aliases"])]
            if len(specific) == 1 and not any(k == "bridge" for k, _n, _c in hits):
                lm = specific[0]
                return Geocode(status="exact", node=lm["node"], candidates=[lm["node"]], matched=[lm["name"]], note="inferred from a named landmark")
            if len(nodes) == 1:
                return Geocode(status="exact", node=nodes[0], candidates=nodes, matched=names, note="inferred from a named landmark")
            return Geocode(status="ambiguous", candidates=nodes, matched=names, note="several places match: dispatcher must choose")
        for area in self.data["areas"]:
            if any(_found(text_l, a) for a in area["aliases"]):
                return Geocode(status="area", candidates=self.area_nodes.get(area["neighbourhood"], []), matched=[area["aliases"][0].title()], note="neighbourhood only")
        return Geocode(status="none", note="no landmark or neighbourhood recognised: not guessing")


@lru_cache(maxsize=4)
def _load(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)
