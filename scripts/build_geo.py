"""Build a RESQNET city file from OpenStreetMap.

    # from a saved OSM XML extract (offline)
    python scripts/build_geo.py --osm-file aluva.osm --name "Aluva, Kerala" --out aluva

    # or download the extract from the Overpass API (needs network access to overpass-api.de)
    python scripts/build_geo.py --bbox 10.08,76.33,10.13,76.38 --name "Aluva, Kerala" --out aluva

The bounding box above is an approximate example around Aluva town; check it on a map
before use. Output: data/geographic/<out>.city.json, selectable as a city in "New run"
(or the `geography` override). The file carries © OpenStreetMap contributors attribution
and is ODbL-licensed as a derived database. Elevation, jetties and bridge clearances are
scenario-assumed and flagged as such; shelters are hypothetical.
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.geography.osm_city import Options, build_city, overpass_query  # noqa: E402

OVERPASS = os.environ.get("OVERPASS_URL", "https://overpass-api.de/api/interpreter")


def fetch(bbox: str) -> str:
    s, w, n, e = (float(x) for x in bbox.split(","))
    if not (s < n and w < e) or (n - s) * (e - w) > 0.04:
        raise SystemExit("bbox must be south,west,north,east and at most ~0.2° x 0.2° (keep Overpass load small)")
    data = urllib.parse.urlencode({"data": overpass_query(s, w, n, e)}).encode()
    req = urllib.request.Request(OVERPASS, data=data, headers={"User-Agent": "resqnet-ai build_geo (research simulation)"})
    with urllib.request.urlopen(req, timeout=240) as r:
        return r.read().decode("utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--osm-file")
    src.add_argument("--bbox", help="south,west,north,east in degrees")
    ap.add_argument("--name", required=True)
    ap.add_argument("--out", required=True, help="file stem: letters, digits, _ or -")
    ap.add_argument("--merge-km", type=float, default=0.15)
    ap.add_argument("--river-step-km", type=float, default=0.4)
    ap.add_argument("--jetty-max-km", type=float, default=0.4)
    ap.add_argument("--neighbourhoods", type=int, default=5)
    ap.add_argument("--save-osm", help="also save the downloaded XML here")
    ap.add_argument("--synthetic", action="store_true", help="mark the output as a synthetic/test geography")
    a = ap.parse_args()
    if a.osm_file:
        xml = open(a.osm_file, encoding="utf-8").read()
        source = {"input": os.path.basename(a.osm_file)}
    else:
        xml = fetch(a.bbox)
        source = {"input": f"Overpass API bbox {a.bbox}", "overpass": OVERPASS}
        if a.save_osm:
            open(a.save_osm, "w", encoding="utf-8").write(xml)
    city = build_city(xml, Options(merge_km=a.merge_km, river_step_km=a.river_step_km, jetty_max_km=a.jetty_max_km, neighbourhoods=a.neighbourhoods, name=a.name, synthetic=a.synthetic), source)
    out = os.path.join(ROOT, "data", "geographic", f"{a.out}.city.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(city, f, ensure_ascii=False, indent=1)
    print(json.dumps(city["stats"]), "→", out)
    if city["stats"]["river_nodes"] == 0:
        print("warning: no waterway=river|canal found; boats will have no river", file=sys.stderr)
