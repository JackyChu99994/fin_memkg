from scripts.analyze_stage5_study import bootstrap, company_rates


def test_company_macro_does_not_treat_repeated_cards_as_independent_companies():
    rows = [{"stock_code": "A", "score": {"exact_answer_correct": True}} for _ in range(3)]
    rows.append({"stock_code": "B", "score": {"exact_answer_correct": False}})
    rates = company_rates(rows)
    assert rates == {"A": 1, "B": 0}
    assert sum(rates.values()) / len(rates) == .5


def test_company_bootstrap_is_reproducible_and_does_not_invent_spread_for_ties():
    assert bootstrap([0, 0, 0]) == [0, 0]
    assert bootstrap([0, .5, 1]) == bootstrap([0, .5, 1])
