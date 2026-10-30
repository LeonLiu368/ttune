"""Document packets: conversions, noise, reading the facts back, truth with gaps, text and PDF. No PolicyEngine."""

import json
from collections import Counter
from datetime import date
from pathlib import Path

import pytest

from docgen import documents, noise, render_text, rules, truth
from docgen.model import Packet
from envgen.household import Expenses, Household, Member
from envgen.sample import sample
from evals import prompt
from evals.answer import parse_answer
from evals.score import oracle_answer, score

ROOT = Path(__file__).resolve().parents[1]


def households(n=150):
    return [sample(set_, 1, i) for set_ in ("id", "ood") for i in range(n)]


@pytest.mark.parametrize("frequency", list(rules.FREQUENCIES))
def test_pay_totals_convert_back_to_the_exact_monthly_figure(frequency):
    for monthly in [1, 7, 99, 412, 1000, 1733, 2500, 3286, 4999, 8123]:
        total = rules.pay_total(monthly, frequency)
        assert rules.monthly_from_pay([total // 2, total - total // 2], frequency) == monthly


def test_weekly_benefits_convert_back():
    for monthly in [1, 250, 1290, 2043, 3999]:
        assert rules.monthly_from_weekly(rules.weekly_benefit(monthly)) == monthly


def test_pay_periods_are_the_most_recent_before_the_application():
    paid = lambda f, n: [p for _, _, p in documents.pay_periods(f, n)]  # noqa: E731
    assert paid("weekly", 2) == [date(2026, 9, 25), date(2026, 9, 18)]
    assert paid("biweekly", 2) == [date(2026, 9, 25), date(2026, 9, 11)]
    assert paid("semimonthly", 3) == [date(2026, 9, 30), date(2026, 9, 15), date(2026, 8, 31)]
    assert paid("monthly", 2) == [date(2026, 9, 30), date(2026, 8, 31)]
    start, end, _ = documents.pay_periods("biweekly", 1)[0]
    assert (end - start).days == 13


def test_same_household_gives_the_same_packet():
    for h in households(10):
        assert documents.build(h).to_dict() == documents.build(h).to_dict()


def test_documents_give_back_the_households_figures():
    for h in households():
        packet = documents.build(h)
        assert documents.established(packet, h) == documents.expected(h, packet), h.id


def test_every_issue_kind_appears_and_gaps_carry_a_flag_and_range():
    seen = Counter()
    for h in households():
        packet = documents.build(h)
        assert len([i for i in packet.issues if i.gap]) <= 1
        for issue in packet.issues:
            seen[issue.kind] += 1
            if issue.kind in noise.GAPS:
                assert issue.flag and issue.gap["range"][0] == 0 < issue.gap["range"][1]
            else:
                assert issue.gap is None and issue.flag is None
    assert set(seen) == set(noise.KINDS), seen


def test_threshold_edge_households_get_no_gaps():
    for h in households():
        if h.shift == "threshold_edge":
            assert not documents.build(h).gaps


def test_packet_round_trips_through_json():
    packet = documents.build(households(3)[1])
    assert Packet.from_dict(json.loads(json.dumps(packet.to_dict()))).to_dict() == packet.to_dict()


def head_with(**income):
    return Household("t-1", "id", 1, 0, "OH", [Member("p1", "Ana", 30, "head", income=income)], Expenses(900, True))


def test_missing_lease_page_drops_page_two_and_says_so_in_the_numbering():
    h = head_with(wages=2000)
    builder = documents._Builder(h, __import__("random").Random(0), [{"kind": "missing_lease_page"}])
    packet = builder.build()
    lease = next(d for d in packet.documents if d.kind == "lease")
    assert [p.number for p in lease.pages] == [1, 3]
    text = render_text.render(lease)
    assert "[Page 1 of 3]" in text and "[Page 3 of 3]" in text and "Monthly rent" not in text
    application = render_text.render(packet.documents[0])
    assert "Not given (see lease)" in application
    assert documents.established(packet, h)["rent"] is None


def test_partner_moved_out_adds_a_pay_stub_that_is_not_anyones_income():
    h = head_with(wages=2000)
    packet = documents._Builder(h, __import__("random").Random(1), [{"kind": "partner_moved_out", "member": "p1"}]).build()
    stubs = [d for d in packet.documents if d.kind == "pay_stub"]
    assert len(stubs) == 3 and sum(d.about is None for d in stubs) == 1
    assert documents.established(packet, h) == documents.expected(h, packet)
    assert "moved out" in render_text.render(packet.documents[0])


def test_name_variant_shows_up_on_the_members_documents():
    h = head_with(wages=2000)
    packet = documents._Builder(h, __import__("random").Random(2), [{"kind": "name_variant", "member": "p1"}]).build()
    stub = next(d for d in packet.documents if d.kind == "pay_stub")
    assert dict(stub.pages[0].blocks[0]["rows"])["Employee"].startswith("A. ")


# --- truth with gaps -------------------------------------------------------------------------------

def t(snap=True, eitc=0.0, medicaid=(), wic=(), snap_amount=100.0):
    return {"snap": {"eligible": snap, "monthly_benefit": snap_amount if snap else 0.0},
            "eitc": {"eligible": eitc > 0, "annual_amount": eitc},
            "medicaid": {"eligible_members": list(medicaid)}, "wic": {"eligible_members": list(wic), "monthly_value": 0.0},
            "chip": {"eligible_members": []}}


def test_grid_spans_the_range():
    assert truth.grid(0, 4000) == [0, 500, 1000, 1500, 2000, 2500, 3000, 3500, 4000]


def test_a_decision_that_never_changes_stands_and_one_that_does_is_unknown():
    out = truth.combine(t(medicaid=["p1", "p2"]), [t(medicaid=["p1"]), t(medicaid=["p1", "p2"])], ["p1", "p2"], ["X"])
    assert out["snap"] == {"eligible": True, "monthly_benefit": 100.0}
    assert out["medicaid"] == {"eligible_members": ["p1"], "unknown_members": ["p2"]}
    assert out["missing_information"] == ["X"]


def test_eitc_hump_counts_as_unknown_even_when_both_ends_say_no():
    # No EITC at $0 or at the top of the range, but some in between: the ends alone would wrongly settle it.
    others = [t(eitc=0.0), t(eitc=1200.0), t(eitc=0.0)]
    out = truth.combine(t(eitc=0.0), others, ["p1"], [])
    assert out["eitc"] == {"eligible": "unknown", "annual_amount": None}


def test_an_amount_that_moves_is_not_scored_but_eligibility_stands():
    out = truth.combine(t(snap_amount=100.0), [t(snap_amount=250.0)], ["p1"], [])
    assert out["snap"] == {"eligible": True, "monthly_benefit": None}


def test_variants_set_the_missing_fact_across_its_range():
    h = head_with(wages=2000)
    packet = documents._Builder(h, __import__("random").Random(0), [{"kind": "missing_income_doc", "member": "p1",
                                                                    "source": "wages"}]).build()
    vs = truth.variants(h, packet)
    assert [v.member("p1").income.get("wages", 0) for v in vs] == truth.grid(*packet.gaps[0].gap["range"])
    assert len({v.id for v in vs}) == len(vs) and h.member("p1").income == {"wages": 2000}


# --- scoring document cases ------------------------------------------------------------------------

DOC_TRUTH = {"snap": {"eligible": "unknown", "monthly_benefit": None}, "eitc": {"eligible": True, "annual_amount": 600.0},
             "medicaid": {"eligible_members": ["p1"], "unknown_members": ["p2"]},
             "wic": {"eligible_members": [], "unknown_members": []}}
NAMES = {"Ana": "p1", "Leo": "p2"}


def reply(body):
    return "```json\n" + json.dumps(body) + "\n```"


def test_unknown_is_right_where_the_documents_leave_a_gap():
    answer, _ = parse_answer(reply(oracle_answer(DOC_TRUTH, NAMES)), NAMES)
    assert answer["medicaid"] == {"members": ["p1"], "unknown": ["p2"], "unknown_names": []}
    assert score(answer, DOC_TRUTH, ["p1", "p2"])["reward"] == 1.0


def test_guessing_past_a_gap_earns_nothing_but_is_not_a_false_denial():
    body = {"snap": {"eligible": False, "monthly_benefit": 0}, "eitc": {"eligible": True, "annual_amount": 600},
            "medicaid": {"eligible_members": ["Ana"]}, "wic": {"eligible_members": []}}
    answer, _ = parse_answer(reply(body), NAMES)
    s = score(answer, DOC_TRUTH, ["p1", "p2"])
    assert s["programs"]["snap"]["false_denials"] == 0 and s["programs"]["snap"]["correct"] == 0
    assert s["programs"]["medicaid"]["false_denials"] == 0 and s["programs"]["medicaid"]["undetermined"] == 1
    assert s["eligibility"] == pytest.approx((0 + 1 + 0.5 + 1) / 4)


def test_document_prompt_has_the_rules_and_the_text_prompt_is_unchanged():
    assert rules.RULES in prompt.DOCUMENT_SYSTEM and "unknown_members" in prompt.DOCUMENT_ANSWER_FORMAT
    summary = json.loads((ROOT / "evals/results/20261026-0340-local-qwen3-4b-instruct/summary.json").read_text())
    assert prompt.prompt_hash() == summary["prompt_hash"]
    assert prompt.prompt_hash(documents=True) != prompt.prompt_hash()
    assert prompt.messages("x", documents=True)[0]["content"] == prompt.DOCUMENT_SYSTEM


def test_built_sets_score_the_oracle_at_one():
    from evals.run import evaluate, load_set

    for set_ in ("id", "ood"):
        path = ROOT / "data" / "documents" / set_ / "cases.jsonl"
        for row in load_set(path):
            names = {m["name"]: m["id"] for m in row["household"]["members"]}
            assert evaluate(row, reply(oracle_answer(row["truth"], names)))["score"]["reward"] == 1.0, row["id"]
            assert row["case"].startswith(f"Case {row['id']}\n")


# --- rendering ------------------------------------------------------------------------------------

def test_text_twin_shows_every_amount():
    for h in households(20):
        packet = documents.build(h)
        text = render_text.render_packet(packet, f"Case {h.id}")
        for doc in packet.documents:
            for page in doc.pages:
                for block in page.blocks:
                    if block["type"] == "fields":
                        for _, value in block["rows"]:
                            assert value.split()[0] in text


def test_pdf_has_the_amounts_and_the_same_bytes_every_time():
    pytest.importorskip("reportlab")
    pdfplumber = pytest.importorskip("pdfplumber")
    import io

    from docgen import render_pdf

    packet = documents.build(head_with(wages=2345))
    stub = next(d for d in packet.documents if d.kind == "pay_stub")
    pdf = render_pdf.render(stub)
    assert pdf == render_pdf.render(stub)
    text = " ".join(page.extract_text() for page in pdfplumber.open(io.BytesIO(pdf)).pages)
    gross = next(r for r in stub.pages[0].blocks[1]["rows"] if r[0] == "Gross pay")[-1]
    assert gross in text and "Earnings statement" in text
