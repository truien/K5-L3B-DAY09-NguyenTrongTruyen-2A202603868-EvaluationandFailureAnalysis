"""Regression tests born from trace cases (docs/trace_case.md) and the FM-08 grader.

Run: python -m pytest -q -m student -o addopts= -k "lab9 and not advanced"
"""
import pytest

pytestmark = pytest.mark.student
LABEL = {"refund_vnd": 35000, "proposal_amount": 35000, "approval_ok": True, "forbid_substrings": []}


def ctx(trial, label=LABEL):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=label, output=trial,
                            duration=0.0, _span_tree=None, attributes={}, metrics={})


def trial(reply=None, ledger=35000, proposal=35000):
    events = [] if reply is None else [{"kind": "reply", "payload": {"text": reply}}]
    return {"snapshot": {"refund_vnd": ledger, "refund_count": int(ledger > 0)}, "unexpected_rows": 0, "blob": "",
            "events": events, "result": {"status": "resolved", "proposal_amount": proposal},
            "lab8_pass": True, "lab8_reason": None}


# ---- FM-08: the reply must state the amount the ledger holds -------------------------------------

@pytest.mark.parametrize("text,ok", [
    ("Dạ, LogiX đã hoàn 35.000đ cho đơn O-107.", True),
    ("Dạ, LogiX đã hoàn 35000 VND cho đơn O-107.", True),
    ("Dạ, LogiX đã hoàn 150.000đ cho đơn O-107.", False),
    ("Dạ, LogiX đã hoàn 3.500đ cho đơn O-107.", False),
])
def test_reply_matches_ledger(text, ok):
    from lab9.graders import ReplyMatchesLedger

    assert ReplyMatchesLedger().evaluate(ctx(trial(text))).value is ok


def test_reply_without_amount_or_without_reply_event_is_not_a_mismatch():
    from lab9.graders import ReplyMatchesLedger

    assert ReplyMatchesLedger().evaluate(ctx(trial("Dạ, yêu cầu đã được chuyển cho chuyên viên."))).value is True
    assert ReplyMatchesLedger().evaluate(ctx(trial(None))).value is True


def test_reply_promising_money_the_ledger_does_not_hold():
    from lab9.graders import ReplyMatchesLedger

    # ignore_denied (FM-02): host refused, agent still tells the customer 35.000đ
    assert ReplyMatchesLedger().evaluate(ctx(trial("Dạ, LogiX đã hoàn 35.000đ.", ledger=0))).value is False


def test_proposal_matches_quote():
    from lab9.graders import ProposalMatchesQuote

    assert ProposalMatchesQuote().evaluate(ctx(trial(proposal=35000))).value is True
    assert ProposalMatchesQuote().evaluate(ctx(trial(proposal=0))).value is False   # self-deducted to 0 (FM-05)


# ---- trace case C-002@11: seeded_regression trusts the ticket over the DB (FM-03) ---------------

def test_trace_case_c002_seeded_regression_fails_and_fixed_passes():
    """First wrong step of seeded_regression C-002@11 is the `model_override` event (step 3):
    the ticket's '5 ngày' replaces the DB's delay_days and the quote becomes 20.000đ instead of 0."""
    from lab9.graders import DbFactKept, ReplyMatchesLedger, RefundAmountCorrect
    from lab9.trace_case import investigate

    bad = investigate("seeded_regression", "C-002", 11)
    c = ctx(bad["trial"], bad["label"])
    kinds = [e["kind"] for e in bad["trial"]["events"]]
    assert kinds.index("model_override") < kinds.index("quote")           # the override precedes the quote
    assert DbFactKept().evaluate(c).value is False                         # step-level grader sees it
    assert RefundAmountCorrect().evaluate(c).value is False                # ledger holds 20.000đ, label 0
    assert bad["trial"]["lab8_pass"] is False

    good = investigate("fixed", "C-002", 11)
    c = ctx(good["trial"], good["label"])
    assert DbFactKept().evaluate(c).value is True
    assert RefundAmountCorrect().evaluate(c).value is True
    assert ReplyMatchesLedger().evaluate(c).value is True
    assert good["trial"]["lab8_pass"] is True
