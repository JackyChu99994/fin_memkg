import hashlib
from repurchase_catalogue import board_decisions, build_catalogue, resolve_source_scheme


def doc(ident, title, text, published="2024-01-02"):
    return {"id": ident, "stock_code": "600001", "title": title, "text": text, "disclosure_date": published,
            "source_url": "https://example.test/" + ident, "text_sha256": hashlib.sha256(text.encode()).hexdigest()}


BODY = "2024年1月1日，公司召开第一届董事会第二次会议，审议通过《关于回购股份方案的议案》。"


def test_deadline_does_not_attach_to_a_later_board_sentence():
    source = doc("S1", "回购报告书", "截止2024年3月31日。审议程序：董事会会议审议通过《关于回购股份方案的议案》。" + BODY)
    assert {d["date"] for d in board_decisions(source)} == {"2024-01-01"}


def test_cited_date_cannot_jump_across_another_date_to_a_board_decision():
    source = doc("S1", "回购报告书", "2023年12月20日披露了提议。" + BODY)
    assert {d["date"] for d in board_decisions(source)} == {"2024-01-01"}


def test_same_company_and_day_do_not_merge_uncited_roots():
    sources = [doc("S1", "第一期回购报告书", "公告编号：2024-001。" + BODY),
               doc("S2", "第二期回购报告书", "公告编号：2024-002。" + BODY)]
    catalogue = build_catalogue(sources, "2024-01-03T00:00:00+08:00")
    assert len(catalogue["schemes"]) == 2
    assert resolve_source_scheme(catalogue, "S1", "2024-01-01")["scheme_ids"] != resolve_source_scheme(catalogue, "S2", "2024-01-01")["scheme_ids"]


def test_unique_explicit_proposal_citation_can_record_a_candidate_alias():
    sources = [doc("S1", "关于回购股份方案的公告", "公告编号：2024-001。" + BODY),
               doc("S2", "回购报告书", "公告编号：2024-002。" + BODY + "方案见公告2024-001。")]
    catalogue = build_catalogue(sources, "2024-01-03T00:00:00+08:00")
    assert len(catalogue["schemes"]) == 1 and len(catalogue["alias_proofs"]) == 1


def test_conflicting_explicit_phases_are_not_merged_even_when_cited():
    sources = [doc("S1", "第一期回购股份方案", "公告编号：2024-001。" + BODY),
               doc("S2", "第二期回购报告书", "公告编号：2024-002。" + BODY + "前一方案公告2024-001。")]
    assert len(build_catalogue(sources, "2024-01-03T00:00:00+08:00")["schemes"]) == 2


def test_future_sources_cannot_create_historical_aliases_or_ids():
    sources = [doc("S1", "关于回购股份方案的公告", "公告编号：2024-001。" + BODY),
               doc("S2", "回购报告书", "公告编号：2024-002。" + BODY + "方案见公告2024-001。", "2024-01-05")]
    catalogue = build_catalogue(sources, "2024-01-03T00:00:00+08:00")
    assert [s["id"] for s in catalogue["sources"]] == ["S1"] and not catalogue["alias_proofs"]
    assert all("S2" not in s["scheme_id"] for s in catalogue["schemes"])


def test_amendment_and_disposal_do_not_create_initial_roots():
    sources = [doc("S1", "回购报告书（修订版）", BODY), doc("S2", "第二期持股计划非交易过户完成", BODY)]
    assert not build_catalogue(sources, "2024-01-03T00:00:00+08:00")["schemes"]


def test_wrong_claimed_date_is_left_unresolved():
    catalogue = build_catalogue([doc("S1", "回购报告书", BODY)], "2024-01-03T00:00:00+08:00")
    assert resolve_source_scheme(catalogue, "S1", "2023-12-01")["status"] == "unresolved_or_ambiguous"


def test_iso_calendar_text_does_not_count_as_an_announcement_number():
    from repurchase_catalogue import mentioned_numbers
    assert "2024-001" not in mentioned_numbers("2024-01-31")
