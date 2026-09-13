"""Local-cache integration verification, including real routing-worker isolation."""
import json
from pathlib import Path
from statistics import median
from time import perf_counter
from concurrent.futures import ThreadPoolExecutor


def main():
    from fastapi.testclient import TestClient
    from app.main import create_app
    from validate_format import PROBE, check_event_log
    report={}
    with TestClient(create_app()) as client:
        payload={"origin_zone":7,"destination_zone":11}
        first=client.post("/routing/route",json=payload)
        assert first.status_code==200,first.text
        comparison=client.post("/routing/compare",json=payload)
        assert comparison.status_code==200,comparison.text
        data=comparison.json()
        assert abs(data["astar"]["eta_min"]-data["dijkstra"]["eta_min"])<1e-8
        report["api_route_distance_km"]=first.json()["distance_km"]
        client.post("/decide",json=PROBE)
        timings=[]
        # Uncached Dijkstra request on the process worker while /decide remains available.
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(client.post,"/routing/route",json={"origin_zone":12,"destination_zone":11,"algorithm":"dijkstra"})
            for _ in range(30):
                start=perf_counter()
                response=client.post("/decide",json=PROBE)
                timings.append((perf_counter()-start)*1000)
                assert response.status_code==200,response.text
                assert response.json()["latency_ms"]<50
            assert pending.result().status_code==200
        report["decide_concurrent_roundtrip_ms"]={"median":median(timings),"max":max(timings),"samples":len(timings)}
        assert max(timings)<50
        edge=first.json()["edge_path"][-2]
        closure=client.post("/routing/closures",json={"closure_id":"api-smoke","edges":[edge],"duration_min":5})
        assert closure.status_code==200,closure.text
        changed=client.post("/routing/route",json=payload)
        assert changed.status_code==200,changed.text
        assert edge not in changed.json()["edge_path"]
        restored=client.post("/routing/route",json={**payload,"sim_time":"2000-01-01T00:05:00"})
        assert restored.json()["route_hash"]==first.json()["route_hash"]
        report["api_closure_expiry"]="PASS"
        report["api_simulation_routes"]=client.get("/simulation/osm-seed-202635/routes").status_code
    paths=list(Path("artifacts/geospatial/runs").glob("*/*.jsonl"))
    logs=[p for p in paths if not any(s in p.name for s in (".trace.",".routing.","source."))]
    for path in logs:
        errors,_=check_event_log(path)
        assert not errors,(str(path),errors)
    report["official_logs_validated"]=len(logs)
    from hashlib import sha256
    baseline_path=Path("artifacts/geospatial/before_hashes.json")
    original=json.loads(baseline_path.read_text()) if baseline_path.exists() else {}
    allowed={".gitignore","app/main.py","app/simulation/simulator.py","app/simulation/strategic.py",
        "requirements.txt","requirements-lock.txt"}
    changed=[p for p,h in original.items() if p.replace('\\','/') not in allowed and (not Path(p).exists() or sha256(Path(p).read_bytes()).hexdigest()!=h)]
    assert not changed,changed
    report["protected_files_unchanged"]=len(original)-len(allowed) if original else "No pre-change fingerprint captured in this checkout"
    Path("artifacts/geospatial/verification.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__=="__main__":
    main()
