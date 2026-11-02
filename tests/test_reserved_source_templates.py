import hashlib
from reserved_source_templates import build_question, explicit_stage, first_purchase


def doc(ident, board, count, published):
    year,month,day = map(int, board.split("-"))
    text = f"公司于{year}年{month}月{day}日召开董事会会议，审议通过《关于回购股份方案的议案》。本次回购股份方案已实施完成。累计回购公司股份{count}股。"
    return {"id": ident, "stock_code": "600001", "company": "Example", "title": "关于回购实施完成的公告", "text": text,
            "text_sha256": hashlib.sha256(text.encode()).hexdigest(), "disclosure_date": published, "source_url": "https://example.test/" + ident}


def test_termination_preserves_started_history_without_becoming_completion():
    source = doc("A", "2023-01-01", 100, "2023-01-02")
    source["title"] = "关于终止回购股份的公告"
    assert explicit_stage(source)[0] == "STARTED"


def test_future_first_purchase_cannot_be_an_actual_disclosed_date():
    source = doc("A", "2023-01-01", 100, "2023-01-02")
    source["text"] += "2023年2月1日，公司首次回购100股。"
    assert first_purchase(source) is None


def test_statistics_date_before_heading_is_not_first_transaction_date():
    source = doc("A", "2024-01-01", 100, "2024-02-03")
    source["text"] = "截至2024年1月31日）的回购进展如下：一、首次回购情况2024年2月2日，公司首次回购4,553,820股。"
    result = first_purchase(source)
    assert result[0] == "2024-02-02"
    assert result[1]["quote"].startswith("2024年2月2日")


def test_later_publication_date_does_not_hide_true_purchase_date():
    source = doc("A", "2022-01-01", 100, "2022-06-17")
    source["text"] = "2022年6月16日，公司首次回购100股，并于2022年6月17日披露公告。"
    assert first_purchase(source)[0] == "2022-06-16"


def test_two_scheme_sum_keeps_later_board_identity_even_if_older_scheme_report_is_later():
    sources = [doc("A", "2023-01-01", 100, "2023-03-01"), doc("B", "2023-02-01", 200, "2023-02-02")]
    item = {"stock_code": "600001", "company": "Example"}
    question, reason = build_question(item, "evidence_trace", sources)
    assert reason is None and question["reference_draft"] == {"shares": 300}
    assert question["target_scheme"] == "600001_BOARD_2023-02-01"
    assert question["identity_proof"]["source_id"] == "B"
    assert {p["source_id"] for p in question["reference_proofs"]} == {"A", "B"}
    assert not question["human_reviewed"] and question["source_qualification"] == "pending"


def test_one_scheme_cannot_be_counted_twice_for_a_cross_scheme_sum():
    sources = [doc("A", "2023-01-01", 100, "2023-02-01"), doc("B", "2023-01-01", 100, "2023-02-02")]
    question, reason = build_question({"stock_code": "600001", "company": "Example"}, "evidence_trace", sources)
    assert question is None and reason


def test_unavailable_first_date_does_not_generate_a_future_answer():
    source = doc("A", "2023-01-01", 100, "2023-01-02")
    question, reason = build_question({"stock_code": "600001", "company": "Example"}, "historical", [source])
    assert question is None and reason
