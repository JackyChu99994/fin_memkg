from experiments.source_adjudicate import stage_proof,reference_at


def test_monthly_inactivity_does_not_erase_cumulative_purchases():
    doc={"role":"followup_candidate","title":"回购进展公告","text":"2024年4月，公司未实施股份回购。截至月底，公司已累计回购股份1,368,268股。"}
    assert stage_proof(doc)[0]=="STARTED"


def test_future_completion_condition_is_not_real_completion():
    doc={"role":"followup_candidate","title":"回购进展公告","text":"如果本次回购方案已实施完毕后，公司将另行公告。截至目前尚未实施股份回购。"}
    assert stage_proof(doc)[0]=="NO_EXECUTION_DISCLOSED"


def test_same_day_actual_purchase_overrides_plan_only_reference():
    items=[({"id":"plan","disclosure_date":"2024-02-08"},{"main_reference":{"repurchase_stage":"NO_EXECUTION_DISCLOSED"}}),
           ({"id":"purchase","disclosure_date":"2024-02-08"},{"main_reference":{"repurchase_stage":"STARTED"}}),
           ({"id":"later","disclosure_date":"2024-03-08"},{"main_reference":{"repurchase_stage":"COMPLETED"}})]
    assert reference_at(items,"2024-02-08")[0]["id"]=="purchase"
