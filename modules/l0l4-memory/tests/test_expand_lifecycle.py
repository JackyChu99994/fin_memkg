"""Collection rules must not select companies using model scores or returns."""
from experiments.expand_lifecycle import followup_candidate, initial_candidate, rank, select_companies


def row(code, ident, day="2024-04-20", title="回购报告书"):
    return {"secCode": code, "announcementId": ident, "announcementTitle": title,
            "adjunctUrl": "finalpage/" + day + "/" + ident + ".PDF"}


def test_initial_titles_exclude_amendments_and_restricted_share_forfeitures():
    assert initial_candidate(row("000001", "1", title="<em>回购</em>报告书"))
    assert not initial_candidate(row("000001", "2", title="回购报告书（修订稿）"))
    assert not initial_candidate(row("000001", "3", title="限制性股票回购报告书"))


def test_first_report_per_company_and_known_development_companies_are_excluded():
    rows = [row("000001", "later", "2024-06-01"), row("000001", "earlier"), row("002594", "known")]
    selected = select_companies(rows)
    assert len(selected) == 1 and selected[0]["announcementId"] == "earlier"


def test_company_assignment_is_stable_under_source_order_and_duplicate_rows():
    rows = [row(f"00000{i}", str(i)) for i in range(1, 8)]
    a = select_companies(rows)
    b = select_companies(list(reversed(rows)) + rows)
    assert [r["secCode"] for r in a] == [r["secCode"] for r in b]
    assert [rank(r["secCode"]) for r in a] == sorted(rank(r["secCode"]) for r in a)


def test_followup_is_a_candidate_filter_not_an_event_identity_claim():
    assert followup_candidate(row("000001", "1", title="关于回购股份进展的公告"))
    assert followup_candidate(row("000001", "2", title="关于终止回购方案的公告"))
    assert not followup_candidate(row("000001", "3", title="关于激励对象限制性股票回购注销完成的公告"))
    assert not followup_candidate(row("000001", "4", title="回购股份前十名股东公告"))
