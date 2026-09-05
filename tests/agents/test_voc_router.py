import json

from agents.llm.base import LLMResponse, LLMUsage
from agents.llm.fake import FakeLLMProvider
from agents.voc_router.router import FeedbackItemFact, classify_tag, dedupe_and_rank

FAKE_USAGE = LLMUsage(provider="fake", model="fake", latency_ms=1.0, input_tokens=1, output_tokens=1, cost_usd=0.0)


def _classification(tag: str) -> LLMResponse:
    parsed = {"tag": tag, "confidence": "medium"}
    return LLMResponse(text=json.dumps(parsed), parsed=parsed, usage=FAKE_USAGE)


def test_already_tagged_items_are_not_reclassified():
    items = [FeedbackItemFact(id="1", account_id="a1", verbatim="bug in the export", tag="product_friction")]
    classifier = FakeLLMProvider(responses=[])  # must never be called

    themes, newly_tagged = dedupe_and_rank(items, {}, classifier)

    assert newly_tagged == {}
    assert themes[0].tag == "product_friction"


def test_untagged_items_are_classified_and_reported_as_newly_tagged():
    items = [FeedbackItemFact(id="1", account_id="a1", verbatim="would love a feature for this", tag=None)]
    classifier = FakeLLMProvider(responses=[_classification("feature_request")])

    themes, newly_tagged = dedupe_and_rank(items, {}, classifier)

    assert newly_tagged == {"1": "feature_request"}
    assert themes[0].tag == "feature_request"


def test_items_are_grouped_across_accounts_by_tag():
    items = [
        FeedbackItemFact(id="1", account_id="a1", verbatim="bug 1", tag="product_friction"),
        FeedbackItemFact(id="2", account_id="a2", verbatim="bug 2", tag="product_friction"),
        FeedbackItemFact(id="3", account_id="a1", verbatim="love it", tag="positive_feedback"),
    ]
    themes, _ = dedupe_and_rank(items, {}, FakeLLMProvider())

    friction = next(t for t in themes if t.tag == "product_friction")
    assert friction.accounts_affected == 2
    assert set(friction.account_ids) == {"a1", "a2"}


def test_ranking_prefers_more_accounts_affected_over_revenue():
    items = [
        FeedbackItemFact(id="1", account_id="a1", verbatim="x", tag="pricing_concern"),  # 1 account, huge revenue
        FeedbackItemFact(id="2", account_id="a2", verbatim="y", tag="onboarding_gap"),
        FeedbackItemFact(id="3", account_id="a3", verbatim="y", tag="onboarding_gap"),  # 2 accounts, small revenue
    ]
    revenue = {"a1": 1_000_000, "a2": 100, "a3": 100}
    themes, _ = dedupe_and_rank(items, revenue, FakeLLMProvider())

    assert themes[0].tag == "onboarding_gap"  # more accounts affected wins


def test_ranking_breaks_ties_by_revenue():
    items = [
        FeedbackItemFact(id="1", account_id="a1", verbatim="x", tag="pricing_concern"),
        FeedbackItemFact(id="2", account_id="a2", verbatim="y", tag="onboarding_gap"),
    ]
    revenue = {"a1": 100, "a2": 1000}
    themes, _ = dedupe_and_rank(items, revenue, FakeLLMProvider())

    assert themes[0].tag == "onboarding_gap"


def test_top_n_caps_the_returned_themes():
    items = [
        FeedbackItemFact(id=str(i), account_id=f"a{i}", verbatim="x", tag=f"tag{i}")
        for i in range(5)
    ]
    themes, _ = dedupe_and_rank(items, {}, FakeLLMProvider(), top_n=2)
    assert len(themes) == 2


def test_sample_verbatims_capped_at_three():
    items = [FeedbackItemFact(id=str(i), account_id="a1", verbatim=f"verbatim {i}", tag="product_friction") for i in range(5)]
    themes, _ = dedupe_and_rank(items, {}, FakeLLMProvider())
    assert len(themes[0].sample_verbatims) == 3


def test_classify_tag_returns_the_parsed_tag():
    classifier = FakeLLMProvider(responses=[_classification("onboarding_gap")])
    assert classify_tag("I couldn't figure out how to set this up", classifier) == "onboarding_gap"


def test_heuristic_provider_classifies_voc_verbatims_by_keyword():
    from agents.llm.fake import HeuristicLLMProvider
    assert classify_tag("this crashed when I tried to save", HeuristicLLMProvider()) == "product_friction"
    assert classify_tag("would be great if you could add bulk export", HeuristicLLMProvider()) == "feature_request"
    assert classify_tag("this is too expensive for our budget", HeuristicLLMProvider()) == "pricing_concern"
    assert classify_tag("the setup was really confusing", HeuristicLLMProvider()) == "onboarding_gap"
    assert classify_tag("we love how this works", HeuristicLLMProvider()) == "positive_feedback"
    assert classify_tag("just a general comment", HeuristicLLMProvider()) == "other"
