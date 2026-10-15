"""SOS place names on the real-geography map snapshots (and no Riverbend names leaking onto them)."""
import pytest

from app.intelligence.extract import analyse
from app.intelligence.geocode import Gazetteer
from app.simulation.engine import Engine
from app.simulation.scenarios import get_preset


def _gaz(**kw):
    e = Engine(get_preset("normal", seed=1, **kw), "decentralized", record_frames=False)
    return e, Gazetteer.for_world(e.world)


@pytest.mark.parametrize("map_id", ["kerala_aluva", "kerala_chengannur"])
def test_riverbend_places_are_never_found_on_a_real_map(map_id):
    e, g = _gaz(map=map_id)
    for text in ["stuck near the Riverside Shiva Temple", "near Old Quarter Market", "at the Eastmere Bus Stand"]:
        loc = analyse(text, g).location
        assert loc.status != "exact", text  # never placed exactly
        assert not any(n in ("Riverside Shiva Temple", "Old Quarter Market", "Eastmere Bus Stand") for n in loc.matched), text
    for lm in g.data["landmarks"]:
        assert lm["node"] in e.world.nodes


def test_aluva_snapshot_places_in_three_languages_and_never_guesses():
    e, g = _gaz(map="kerala_aluva")
    assert analyse("5 people trapped near Aluva railway station, water rising", g).location.matched == ["Aluva Railway Station"]
    assert analyse("हम 4 लोग आलुवा रेलवे स्टेशन के पास फंसे हैं", g).location.matched == ["Aluva Railway Station"]
    assert analyse("ആലുവ മാർക്കറ്റിനടുത്ത് 4 പേർ കുടുങ്ങി", g).location.matched == ["Aluva Market"]
    assert analyse("help near the bus stand", g).location.status == "ambiguous", "two bus stands"
    node = analyse("trapped at the Manappuram temple", g).location
    assert node.status == "exact" and node.node in e.world.nodes
    assert analyse("stuck in Aluva, please help", g).location.status != "exact", "the town's name is not a place"


def test_riverbend_keeps_its_own_places():
    _, g = _gaz()
    assert analyse("stuck near the Riverside Shiva Temple", g).location.node == "N44"
