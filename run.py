#!/usr/bin/env python3
"""Run the triage engine over data/ and write results.json plus the console's data file.

    python3 run.py                 # recorded model outputs, no key needed (default)
    python3 run.py --mode live     # call the model for every stage (LLM_PROVIDER=anthropic|gemini + its key)

Live mode writes results.live.json and unreported_defects.live.json and leaves the committed
recorded outputs and console/data.js untouched. Pass --publish to overwrite them instead.
"""
import argparse
import datetime
import json
import os

from engine.pipeline import run

ROOT = os.path.dirname(os.path.abspath(__file__))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["recorded", "live"], default="recorded")
    ap.add_argument("--publish", action="store_true", help="live mode: overwrite results.json and console/data.js")
    args = ap.parse_args()
    out = run(args.mode)
    sfx = ".live" if args.mode == "live" and not args.publish else ""
    json.dump(out["results"], open(os.path.join(ROOT, f"results{sfx}.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    slim = [{k: x[k] for k in ("questionId", "subject", "chapter", "repair", "edits", "evidence", "confidence", "guards_pass")} for x in out["sweep"]]
    json.dump(slim, open(os.path.join(ROOT, f"unreported_defects{sfx}.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    data = {"generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "mode": out["mode"],
            "cases": out["cases"], "sweep": out["sweep"], "taxonomy": out["taxonomy"]}
    if not sfx:
        with open(os.path.join(ROOT, "console", "data.js"), "w", encoding="utf-8") as f:
            f.write("window.TRIAGE = " + json.dumps(data, ensure_ascii=False) + ";\n")
    from collections import Counter
    print(f"{len(out['results'])} reports on {len(out['cases'])} questions ({out['mode']} mode)")
    print("verdicts:", dict(Counter(r["verdict"] for r in out["results"])))
    print("routes:  ", dict(Counter(r["route"] for r in out["results"])))
    print(f"unreported defects found by the sweep: {len(out['sweep'])}")
