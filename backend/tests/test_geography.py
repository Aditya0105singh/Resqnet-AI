"""OSM → city file → engine. Uses a small FICTIONAL town in OSM XML (tests/fixtures/testvale.osm)."""
import json
import os

import pytest

from app.analysis.runs import verify_replay
from app.geography.osm_city import Options, build_city, overpass_query
from app.intelligence.extract import analyse
from app.intelligence.geocode import Gazetteer
from app.metrics.metrics import compute_metrics
from app.simulation import world as world_mod
from app.simulation.engine import Engine
from app.simulation.scenarios import get_preset

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "testvale.osm")


@pytest.fixture(scope="module")
def city():
    return build_city(open(FIXTURE, encoding="utf-8").read(), Options(name="Testvale (fictional fixture)", synthetic=True, neighbourhoods=4))


@pytest.fixture()
def geo_dir(tmp_path, monkeypatch, city):
    (tmp_path / "testvale.city.json").write_text(json.dumps(city, ensure_ascii=False))
    monkeypatch.setattr(world_mod, "GEO_DIR", str(tmp_path))
    return tmp_path


def test_osm_conversion_keeps_structure_and_provenance(city):
    s = city["stats"]
    assert s["land_nodes"] >= 20 and s["river_nodes"] >= 5 and s["bridges"] == 2 and s["jetties"] >= 2
    assert {e["name"] for e in city["edges"] if e["kind"] == "bridge"} == {"Old Bridge", "New Bridge"}
    assert all(e["provenance"] == "scenario-assumed" for e in city["edges"] if e["kind"] == "jetty")
    assert all(n["lat"] is not None and n["provenance"] for n in city["nodes"])
    assert all("hypothetical" in s["provenance"] for s in city["shelters"]) and len(city["shelters"]) == 3
    assert any("elevation" in a.lower() and "scenario-assumed" in a for a in city["assumptions"])
    names = [z["name"] for z in city["neighbourhoods"]]
    assert len(names) == len(set(names)) and any("Testvale" in n for n in names)
    temple = next(l for l in city["landmarks"] if l["name"] == "Riverside Temple")
    assert "റിവർസൈഡ് ക്ഷേത്രം" in temple["aliases"] and "रिवरसाइड मंदिर" in temple["aliases"]


def test_conversion_is_deterministic(city):
    again = build_city(open(FIXTURE, encoding="utf-8").read(), Options(name="Testvale (fictional fixture)", synthetic=True, neighbourhoods=4))
    assert again == city


def test_simplification_removes_shape_points(city):
    # the fixture has a shape point in every street block; only junctions may remain
    from app.geography.osm_city import parse_osm

    nodes, _w, _m = parse_osm(open(FIXTURE, encoding="utf-8").read())
    assert city["stats"]["land_nodes"] < sum(1 for _ in nodes) / 2


def test_engine_runs_safely_on_an_osm_city(geo_dir):
    assert any(g["id"] == "testvale" for g in world_mod.available_geographies())
    for strategy in ("decentralized", "message_passing", "centralized"):
        e = Engine(get_preset("triple_failure", seed=4, geography="testvale"), strategy, record_frames=False)
        assert e.world.meta["name"].startswith("Testvale") and "B1" in e.world.resources and e.world.nodes[e.world.resources["B1"].node].kind == "river"
        while not e.finished:
            e.step()
        m = compute_metrics(e)
        assert m["invariant_violations"] == 0 and m["route_violations"] == 0
        assert m["people_rescued"] > 0, strategy


def test_osm_city_replays(geo_dir):
    e = Engine(get_preset("normal", seed=2, geography="testvale"), "decentralized")
    for _ in range(20):
        e.step()
    e.inject("CLOSE_EDGE", {"edge_id": "BR1", "reason": "test"})
    for _ in range(10):
        e.step()
    assert verify_replay(e)["identical"]


def test_sos_gazetteer_uses_osm_names_in_every_script(geo_dir):
    e = Engine(get_preset("normal", seed=2, geography="testvale"), "decentralized", record_frames=False)
    gaz = Gazetteer.for_world(e.world)
    x = analyse("ഞങ്ങൾ നാലു പേർ റിവർസൈഡ് ക്ഷേത്രത്തിന്റെ അടുത്ത് കുടുങ്ങി", gaz)
    temple = next(l for l in e.world.meta["landmarks"] if l["name"] == "Riverside Temple")
    assert x.location.status == "exact" and x.location.node == temple["node"]
    assert analyse("stuck near Old Bridge", gaz).location.status == "ambiguous", "a bridge has two banks"


def test_api_lists_and_uses_geographies(geo_dir):
    from fastapi.testclient import TestClient

    from app.api import main as api

    client = TestClient(api.app)
    assert "testvale" in [g["id"] for g in client.get("/api/geographies").json()["geographies"]]
    sid = client.post("/api/simulations", json={"scenario": "normal", "strategy": "decentralized", "overrides": {"geography": "testvale"}}).json()["id"]
    w = client.get(f"/api/world?sim={sid}").json()
    assert w["name"].startswith("Testvale") and "attribution" in w and any(n["lat"] for n in w["nodes"])
    bad = client.post("/api/simulations", json={"scenario": "normal", "strategy": "decentralized", "overrides": {"geography": "../etc/passwd"}})
    assert bad.status_code == 422


def test_overpass_query_is_bounded():
    q = overpass_query(10.08, 76.33, 10.13, 76.38)
    assert "10.08,76.33,10.13,76.38" in q and 'waterway"~"^(river|canal)$"' in q and "out body" in q


def test_clip_to_bounds_splits_ways_at_the_box():
    from app.geography.osm_city import clip_to_bounds
    nodes = {"a": (0.0, 0.0, {}), "b": (0.0, 0.5, {}), "c": (0.0, 5.0, {}), "d": (0.0, 0.8, {}), "e": (0.0, 0.9, {})}
    ways = [("w", ["a", "b", "c", "d", "e"], {"waterway": "river"})]
    inside, out = clip_to_bounds(nodes, ways, (-1.0, -1.0, 1.0, 1.0))
    assert "c" not in inside
    assert out == [("w", ["a", "b"], {"waterway": "river"}), ("w.1", ["d", "e"], {"waterway": "river"})]


ALUVA = os.path.join(os.path.dirname(__file__), "..", "..", "data", "geographic", "aluva.city.json")


@pytest.mark.skipif(not os.path.exists(ALUVA), reason="Aluva city file not built")
def test_aluva_runs_safely_under_triple_failure():
    assert any(g["id"] == "aluva" and not g["synthetic"] for g in world_mod.available_geographies())
    for strategy in ("decentralized", "centralized"):
        e = Engine(get_preset("triple_failure", seed=3, geography="aluva"), strategy, record_frames=False)
        assert e.world.meta["name"] == "Aluva, Kerala"
        while not e.finished:
            e.step()
        m = compute_metrics(e)
        assert m["invariant_violations"] == 0 and m["route_violations"] == 0 and m["people_rescued"] > 0


def test_river_pieces_that_meet_are_chained():
    from app.geography.osm_city import Projection, _river_line
    nodes = {k: (0.0, lon, {}) for k, lon in {"a": 0.0, "b": 0.01, "c": 0.02, "d": 0.03, "x": 0.5, "y": 0.501}.items()}
    ways = [("w1", ["a", "b"], {"waterway": "river"}), ("w2", ["c", "d"], {"waterway": "river"}), ("w3", ["c", "b"], {"waterway": "river"}), ("w4", ["x", "y"], {"waterway": "river"})]
    line = _river_line(nodes, ways, Projection(0.0, 0.0))
    assert len(line) == 4  # a-b-c-d, not the isolated x-y piece


def test_town_name_is_not_a_location():
    from app.geography.osm_city import _drop_town_name
    lms = [
        {"id": "L1", "name": "Aluva", "node": "N1", "aliases": ["Aluva", "ആലുവ"]},
        {"id": "L2", "name": "Aluva", "node": "N2", "aliases": ["Aluva", "Aluva Private Bus Stand", "ആലുവ"]},
        {"id": "L3", "name": "Aluva Railway Station", "node": "N3", "aliases": ["Aluva Railway Station"]},
    ]
    out = _drop_town_name(lms, "Aluva")
    assert [l["name"] for l in out] == ["Aluva Private Bus Stand", "Aluva Railway Station"]
    assert all("ആലുവ" not in l["aliases"] and "Aluva" not in l["aliases"] for l in out)


@pytest.mark.skipif(not os.path.exists(ALUVA), reason="Aluva city file not built")
def test_aluva_sos_in_three_languages_finds_real_places_and_never_guesses():
    e = Engine(get_preset("normal", seed=1, geography="aluva"), "decentralized", record_frames=False)
    gaz = Gazetteer.for_world(e.world)
    assert analyse("5 people trapped near Aluva railway station", gaz).location.matched == ["Aluva Railway Station"]
    assert analyse("हम 4 लोग आलुवा रेलवे स्टेशन के पास फंसे हैं", gaz).location.matched == ["Aluva Railway Station"]
    assert analyse("ആലുവ മാർക്കറ്റിനടുത്ത് 4 പേർ കുടുങ്ങി", gaz).location.matched == ["Aluva Market"]
    assert analyse("stuck near the bus stand", gaz).location.status == "ambiguous", "two bus stands"
    assert analyse("stuck in Aluva, please help", gaz).location.status == "none", "the town name is not a location"
