"""Document truth through PolicyEngine. Skipped without policyengine-us."""

import pytest

pytest.importorskip("policyengine_us")

from docgen import documents, truth  # noqa: E402
from envgen import truth as pe  # noqa: E402
from envgen.household import Expenses, Household, Member  # noqa: E402


def single_parent(hid):
    return Household(hid, "id", 1, 0, "OH", [Member("p1", "Ana", 30, "head", income={"wages": 1800}),
                                            Member("p2", "Leo", 3, "child")], Expenses(900, True))


def test_a_missing_pay_stub_leaves_snap_unknown_and_a_complete_packet_keeps_its_truth():
    gap_h, full_h = single_parent("t-gap"), single_parent("t-full")
    gap_p = documents._Builder(gap_h, __import__("random").Random(0),
                               [{"kind": "missing_income_doc", "member": "p1", "source": "wages"}]).build()
    full_p = documents._Builder(full_h, __import__("random").Random(0), []).build()
    base = pe.compute([gap_h, full_h])
    gap_t, full_t = truth.compute([(gap_h, gap_p, base[0]), (full_h, full_p, base[1])])
    # $0 to 300% of the poverty line a month spans SNAP's limit and the EITC's whole range.
    assert gap_t["snap"]["eligible"] == "unknown" and gap_t["eitc"]["eligible"] == "unknown"
    assert gap_t["missing_information"] == [gap_p.gaps[0].flag] and gap_p.gaps[0].flag.startswith("Pay stubs for Ana ")
    assert full_t["snap"]["eligible"] == base[1]["snap"]["eligible"] and full_t["missing_information"] == []
    assert full_t["medicaid"]["unknown_members"] == []
