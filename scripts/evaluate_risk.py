"""Evaluate / calibrate the scam risk engine.

python scripts/evaluate_risk.py                    # rule engine on the tune + holdout splits
python scripts/evaluate_risk.py --llm              # full hybrid engine (needs Ollama running)
python scripts/evaluate_risk.py --calibrate        # suggest RISK_*_THRESHOLD values (tune split)
python scripts/evaluate_risk.py --dataset feedback.jsonl --split all
"""

import argparse
import json
import sys
from pathlib import Path

from backend.ai.eval import evaluate as ev
from backend.config import settings

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--dataset", type=Path)
p.add_argument("--split", default=None, help="tune | holdout | all (default: report tune and holdout separately)")
p.add_argument("--llm", action="store_true", help="score with rules + Ollama instead of rules only")
p.add_argument("--calibrate", action="store_true")
p.add_argument("--min-precision", type=float, default=0.95)
p.add_argument("--json", action="store_true", help="machine-readable output")
p.add_argument("--fail-under-f1", type=float, default=None, help="exit 1 if holdout F1 at medium is below this")
a = p.parse_args()

splits = [a.split] if a.split else ["tune", "holdout"]
out = {
    "thresholds": {"medium": settings.RISK_MEDIUM_THRESHOLD, "high": settings.RISK_HIGH_THRESHOLD},
    "engine": "hybrid" if a.llm else "rules",
}
for split in splits:
    scored = ev.score_rows(ev.load(a.dataset, split), use_llm=a.llm)
    if not scored:
        continue
    out[split] = ev.report(scored, settings.RISK_MEDIUM_THRESHOLD, settings.RISK_HIGH_THRESHOLD)
    if a.calibrate and split in ("tune", "all"):
        cal = ev.calibrate(scored, a.min_precision)
        out[split]["calibration"] = {k: v for k, v in cal.items() if k != "sweep"} | {"sweep": cal["sweep"]}

if a.json:
    print(json.dumps(out, indent=2, ensure_ascii=False))
else:
    print(f"engine={out['engine']} thresholds={out['thresholds']}")
    for split in splits:
        if split not in out:
            continue
        r = out[split]
        print(f"\n== {split} ({r['examples']} examples) ==")
        for name in ("warning_level", "scam_level"):
            m = r[name]
            print(
                f"  {name:<14} thr={m['threshold']:<3} precision={m['precision']:.3f} recall={m['recall']:.3f} "
                f"f1={m['f1']:.3f}  (tp={m['tp']} fp={m['fp']} fn={m['fn']} tn={m['tn']})"
            )
        print("  category recall @medium:", r["category_recall_at_medium"])
        for kind, items in r["errors_at_medium"].items():
            print(f"  {kind}:")
            for e in items:
                print(f"    [{e['score']:>3}] {e['flags']} {e['text']}")
        if "calibration" in r:
            c = r["calibration"]
            print(
                f"  suggested RISK_MEDIUM_THRESHOLD={c['suggested_medium_threshold']} "
                f"(max legit score {c['max_legit_score']}); scam score quantiles {c['scam_score_quantiles']}"
            )
            for m in c["sweep"]:
                print(f"    thr={m['threshold']:<3} p={m['precision']:.3f} r={m['recall']:.3f} f1={m['f1']:.3f}")

if a.fail_under_f1 is not None:
    target = out.get("holdout") or out.get(splits[-1])
    if target and target["warning_level"]["f1"] < a.fail_under_f1:
        sys.exit(f"F1 {target['warning_level']['f1']} below {a.fail_under_f1}")
