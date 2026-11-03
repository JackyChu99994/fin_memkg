"""Expanded scoring preserves the review gate and whole-group weighting."""
import pytest

from experiments.prepare_expanded_episodes import prepare
from experiments.run_expanded_comparison import METHODS, summary, validate_episodes
from test_prepare_expanded_episodes import data


def test_unreviewed_episodes_cannot_enter_formal_evaluation():
    corpus, refs = data()
    episodes, _ = prepare(corpus, refs, "development", allow_draft=True)
    with pytest.raises(ValueError, match="review"):
        validate_episodes(episodes, False)
    validate_episodes(episodes, True)


def test_reserved_test_never_accepts_draft_override():
    corpus, refs = data("test_reserved", reviewed=True)
    episodes, _ = prepare(corpus, refs, "test_reserved")
    validate_episodes(episodes, False)
    with pytest.raises(ValueError, match="forbidden"):
        validate_episodes(episodes, True)


def test_group_macro_accuracy_does_not_overweight_longer_timelines():
    episodes = [{"independence_group": "a"}, {"independence_group": "a"}, {"independence_group": "b"}]
    records = []
    for method in METHODS:
        for group, correct in (("a", True), ("a", False), ("b", True)):
            records.append({"method": method, "independence_group": group, "correct": correct,
                            "status": "ok" if correct else "failed", "usage": {}})
    result = summary(records, episodes)
    assert result["independent_groups"] == 2 and result["cutoffs"] == 3
    assert result["methods"][METHODS[0]]["accuracy_including_failures"] == pytest.approx(2/3)
    assert result["methods"][METHODS[0]]["macro_group_accuracy"] == .75
    assert result["methods"][METHODS[0]]["failures"] == 1
