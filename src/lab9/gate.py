"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    rows = pr.get("rows") or []
    man = pr.get("manifest") or {}
    graded = [m["id"] for m in spec.get("metrics", []) if m["id"] in GRADERS]

    # 1. NaN / inf in the reported metrics ("nan < min" is False: a naive gate waves it through)
    for k, v in (pr.get("metrics") or {}).items():
        if isinstance(v, float) and not math.isfinite(v):
            problems.append(f"metric {k} is {v} (not a finite number)")

    # 2. row count vs the manifest (dropped / duplicated rows)
    n_seeds = len(man.get("seeds") or [])
    want = int(man.get("items", 0)) * n_seeds
    if len(rows) != want:
        problems.append(f"{len(rows)} rows, manifest promises {man.get('items')} items x {n_seeds} seeds = {want}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    if len(set(keys)) != len(keys):
        problems.append(f"{len(keys) - len(set(keys))} duplicated (item_id, seed) row(s)")

    # 3. the PR must cover exactly the baseline's (item, seed) set (cherry-picked seeds / items)
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base.get("rows") or []}
    if set(keys) != base_keys:
        problems.append(f"(item, seed) set differs from baseline: {len(base_keys - set(keys))} missing, "
                        f"{len(set(keys) - base_keys)} extra")
    base_seeds = (base.get("manifest") or {}).get("seeds") or []
    if sorted(man.get("seeds") or []) != sorted(base_seeds):
        problems.append(f"manifest seeds {man.get('seeds')} differ from baseline seeds {base_seeds}")

    # 4. crashed graders: evaluator_failures, or a graded metric that is None / missing on a row
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s), first: {pr['evaluator_failures'][0]}")
    for m in graded:
        none_rows = sum(1 for r in rows if r.get(m) is None)
        if none_rows:
            problems.append(f"{none_rows} row(s) have no value for graded metric {m} (grader crashed or row edited)")

    # 5. reported metrics must be recomputable from the rows: the rows are the evidence
    for spec_metric in spec.get("metrics", []):
        m = spec_metric["id"]
        vals = [r[m] for r in rows if r.get(m) is not None] if m in graded else []
        reported = (pr.get("metrics") or {}).get(m)
        if not vals or not isinstance(reported, (int, float)) or not math.isfinite(reported):
            continue
        actual = sum(vals) if spec_metric.get("kind") == "safety" else sum(vals) / len(vals)
        if abs(actual - reported) > 1e-3:
            problems.append(f"metric {m} reported {reported} but its rows give {round(actual, 4)}")

    # 6. an item's slice tags must match the baseline's (relabelling hides it from the slice gate)
    def tags(rep: dict) -> dict:
        return {r.get("item_id"): sorted(r.get("slices") or []) for r in rep.get("rows") or []}
    pt, bt = tags(pr), tags(base)
    moved = sorted(str(i) for i in pt.keys() & bt.keys() if pt[i] != bt[i])
    if moved:
        problems.append(f"slice tags differ from baseline for {', '.join(moved[:5])}")

    # 7. ratchet: same eval-set version => thresholds may only get stricter
    if base_spec is not None and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        problems += _ratchet(spec, base_spec)
    return problems


def _loosened(new: dict, old: dict, label: str, new_blocking: bool, old_blocking: bool) -> list[str]:
    out = []
    if "max" in old and ("max" not in new or new["max"] > old["max"]):
        out.append(f"{label}: max {old['max']} -> {new.get('max')} (looser)")
    if "min" in old and ("min" not in new or new["min"] < old["min"]):
        out.append(f"{label}: min {old['min']} -> {new.get('min')} (looser)")
    if "max_increase" in old and ("max_increase" not in new or new["max_increase"] > old["max_increase"]):
        out.append(f"{label}: max_increase {old['max_increase']} -> {new.get('max_increase')} (looser)")
    if old.get("no_significant_drop") and not new.get("no_significant_drop"):
        out.append(f"{label}: no_significant_drop dropped")
    if old_blocking and not new_blocking:
        out.append(f"{label}: no longer blocking")
    return out


def _ratchet(spec: dict, base_spec: dict) -> list[str]:
    out: list[str] = []
    cur_metrics = {m["id"]: m for m in spec.get("metrics", [])}
    for old in base_spec.get("metrics", []):
        cur = cur_metrics.get(old["id"])
        if cur is None:
            out.append(f"metric {old['id']} removed from spec")
            continue
        out += _loosened(cur.get("threshold", {}), old.get("threshold", {}), f"metric {old['id']}",
                         bool(cur.get("blocking")), bool(old.get("blocking")))
        if old.get("kind") == "safety" and cur.get("kind") != "safety":
            out.append(f"metric {old['id']}: no longer a safety metric")
    cur_slices = {(s["name"], s["metric"]): s for s in spec.get("slices") or []}
    keys = ("min", "max", "no_significant_drop")
    for old in base_spec.get("slices") or []:
        label = f"slice {old['name']}/{old['metric']}"
        cur = cur_slices.get((old["name"], old["metric"]))
        if cur is None:
            out.append(f"{label} removed from spec")
            continue
        out += _loosened({k: cur[k] for k in keys if k in cur}, {k: old[k] for k in keys if k in old},
                         label, bool(cur.get("blocking")), bool(old.get("blocking")))
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, metric = sl["name"], sl["metric"]
        sid = f"slice:{name}/{metric}"
        a = per_item(pr, metric, slice_name=name)
        b = per_item(base, metric, slice_name=name)
        verdict, note, value = "ok", "", None
        if not a:
            verdict = "missing"          # an empty slice proves nothing; never read it as green
        else:
            value = sum(a.values()) / len(a)
            if "min" in sl and value < sl["min"]:
                verdict = "fail"
            if sl.get("no_significant_drop"):
                ks = sorted(set(a) & set(b))
                if ks:
                    d, lo, hi = stats.paired_bootstrap([a[k] for k in ks], [b[k] for k in ks],
                                                       n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
                    note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                    if hi < 0:
                        verdict = "fail"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok"}.get(verdict, "BLOCK" if sl.get("blocking") else "warn")
        shown = "-" if value is None else f"{value:.4f}"
        floor = json.dumps({"min": sl["min"]}) if "min" in sl else "{}"
        lines.append(f"  {sid:<34} {shown:<8} {floor:<14} n={len(a):<3} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
