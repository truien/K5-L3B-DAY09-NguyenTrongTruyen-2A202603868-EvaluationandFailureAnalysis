"""Extra M5-M7 checks on the gate (hand-built reports, no shape run).
Run: python -m pytest -q -m student -o addopts= -k advanced"""
import copy
import math

import pytest

pytestmark = pytest.mark.student

ROWS = [{"item_id": f"E-{i:03d}", "seed": s, "pass_rate": True, "slices": ["money_movement"] if i < 2 else []}
        for i in range(4) for s in (1, 2)]
SPEC = {"eval_set_version": "v2",
        "metrics": [{"id": "pass_rate", "kind": "capability", "blocking": True,
                     "threshold": {"min": 0.8, "no_significant_drop": True}}],
        "slices": [{"name": "money_movement", "metric": "pass_rate", "min": 0.95, "blocking": True}]}


def report(rows=None, metrics=None, **extra):
    return {"manifest": {"eval_set_sha": "x", "items": 4, "seeds": [1, 2]}, "rows": copy.deepcopy(rows or ROWS),
            "metrics": metrics or {"pass_rate": 1.0}, "evaluator_failures": [], **extra}


def test_integrity_flags_infinity_duplicates_and_failures():
    from lab9 import gate

    base = report()
    assert gate.integrity_check(base, base, SPEC) == []
    assert gate.integrity_check(report(metrics={"pass_rate": math.inf}), base, SPEC)
    dup = report(rows=ROWS[:-1] + [ROWS[0]])
    assert any("duplicated" in p for p in gate.integrity_check(dup, base, SPEC))
    assert gate.integrity_check(report(evaluator_failures=["E-001@1:SecretLeak:boom"]), base, SPEC)


def test_integrity_flags_none_value_and_edited_metric():
    from lab9 import gate

    base = report()
    rows = copy.deepcopy(ROWS)
    rows[0]["pass_rate"] = None
    assert gate.integrity_check(report(rows=rows, metrics={"pass_rate": 1.0}), base, SPEC)
    rows = copy.deepcopy(ROWS)
    rows[0]["pass_rate"] = False
    assert any("reported" in p for p in gate.integrity_check(report(rows=rows, metrics={"pass_rate": 1.0}), base, SPEC))


def test_integrity_flags_relabelled_slice():
    from lab9 import gate

    base = report()
    rows = copy.deepcopy(ROWS)
    for r in rows:
        if r["item_id"] == "E-000":
            r["slices"] = []
    assert any("slice tags" in p for p in gate.integrity_check(report(rows=rows), base, SPEC))


def test_ratchet_flags_dropped_slice_and_nonblocking_metric():
    from lab9 import gate

    base = report()
    no_slice = dict(copy.deepcopy(SPEC), slices=[])
    assert any("removed" in p for p in gate.integrity_check(base, base, no_slice, SPEC))
    soft = copy.deepcopy(SPEC)
    soft["metrics"][0]["blocking"] = False
    assert any("no longer blocking" in p for p in gate.integrity_check(base, base, soft, SPEC))
    stricter = copy.deepcopy(SPEC)
    stricter["metrics"][0]["threshold"]["min"] = 0.9
    assert gate.integrity_check(base, base, stricter, SPEC) == []


def test_empty_slice_is_not_green():
    from lab9 import gate

    base = report()
    rows = [dict(r, slices=[]) for r in ROWS]
    blocked, _ = gate.slice_check(report(rows=rows), base, SPEC)
    assert blocked == ["slice:money_movement/pass_rate"]
