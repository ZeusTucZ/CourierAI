import json
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class ZoneRegistry:
    def __init__(self, path=ROOT / "config/monterrey_zones.json"):
        self.document = json.loads(Path(path).read_text(encoding="utf-8"))
        self.version = sha256(json.dumps(self.document, sort_keys=True).encode()).hexdigest()
        self.zones = {}
        for zone in self.document["zones"]:
            key = zone["zone_id"]
            if key in self.zones or not zone["name"].strip():
                raise ValueError("Duplicate zone ID or empty name")
            if not 25.5 < zone["latitude"] < 26 or not -100.7 < zone["longitude"] < -100:
                raise ValueError("Zone outside Monterrey study area")
            self.zones[key] = zone
        if not 8 <= len(self.zones) <= 15:
            raise ValueError("Expected 8–15 representative zones")

    def geojson(self):
        return {"type": "FeatureCollection", "zone_mapping_version": self.version, "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [z["longitude"], z["latitude"]]},
             "properties": z} for z in self.zones.values()]}
