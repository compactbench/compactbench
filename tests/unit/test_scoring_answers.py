"""Mechanical answer scoring."""

from __future__ import annotations

import pytest

from compactbench.contracts import NOT_STATED, Probe, ProbeCategory, ProbeFormat, ValueKind
from compactbench.scoring import counted, normalize, score_probe

pytestmark = pytest.mark.unit


def _probe(fmt: ProbeFormat, **fields: object) -> Probe:
    base: dict[str, object] = {
        "key": "k",
        "category": ProbeCategory.DECISION_STATE,
        "format": fmt,
        "question": "q?",
        "origin_cycle": 0,
    }
    base.update(fields)
    return Probe.model_validate(base)


SINGLE = _probe(
    ProbeFormat.SINGLE,
    options=["Postgres", "MySQL", "a 5% canary", NOT_STATED],
    answer=["MySQL"],
    stale=["Postgres"],
)
MULTI = _probe(
    ProbeFormat.MULTI,
    options=["r1", "r2", "w1", "w2", "old"],
    answer=["r1", "r2"],
    stale=["old"],
)


class TestNormalize:
    @pytest.mark.parametrize(
        ("raw", "kind", "expected"),
        [
            ("$12,500", ValueKind.MONEY, "12500"),
            ("12.5k", ValueKind.MONEY, "12500"),
            ("$12,500/year", ValueKind.MONEY, "12500"),
            ("6,500 dollars", ValueKind.MONEY, "6500"),
            ("17:00", ValueKind.NUMBER, "17"),
            ("iOS 16", ValueKind.NUMBER, "16"),
            ("March 16, 2026", ValueKind.DATE, "2026-03-16"),
            ("16 March 2026", ValueKind.DATE, "2026-03-16"),
            ("Mar 16 2026", ValueKind.DATE, "2026-03-16"),
            ("2026-03-16", ValueKind.DATE, "2026-03-16"),
            ("v2.5.0", ValueKind.VERSION, "2.5.0"),
            ("Version 2.5.0", ValueKind.VERSION, "2.5.0"),
            ("ops-4821", ValueKind.IDENT, "OPS4821"),
            ("The billing service.", ValueKind.TEXT, "billing service"),
            ("Atlas's rate limiter", ValueKind.TEXT, "rate limiter"),
        ],
    )
    def test_kinds(self, raw: str, kind: ValueKind, expected: str) -> None:
        assert normalize(raw, kind) == expected


class TestSingle:
    def test_letter(self) -> None:
        assert score_probe(SINGLE, "B").score == 1.0

    def test_letter_with_text(self) -> None:
        assert score_probe(SINGLE, "B. MySQL").score == 1.0

    def test_option_text(self) -> None:
        assert score_probe(SINGLE, "mysql").score == 1.0

    def test_option_text_that_starts_like_a_letter(self) -> None:
        assert score_probe(SINGLE, "a 5% canary").score == 0.0
        assert score_probe(SINGLE, "a 5% canary").answered

    def test_hedging_scores_zero(self) -> None:
        result = score_probe(SINGLE, ["A", "B"])
        assert result.score == 0.0
        assert result.answered

    def test_stale_answer_flagged(self) -> None:
        result = score_probe(SINGLE, "A")
        assert result.stale
        assert result.stale_possible

    def test_not_stated(self) -> None:
        result = score_probe(SINGLE, "D")
        assert result.abstained
        assert result.score == 0.0

    def test_unparseable(self) -> None:
        assert not score_probe(SINGLE, "Z").answered
        assert not score_probe(SINGLE, None).answered
        assert not score_probe(SINGLE, {"x": 1}).answered


class TestMulti:
    def test_exact(self) -> None:
        assert score_probe(MULTI, ["A", "B"]).score == 1.0

    def test_partial(self) -> None:
        assert score_probe(MULTI, ["A"]).score == 0.5

    def test_wrong_picks_cost(self) -> None:
        assert score_probe(MULTI, ["A", "B", "C"]).score == 0.5

    def test_select_everything_does_not_pay(self) -> None:
        assert score_probe(MULTI, ["A", "B", "C", "D", "E"]).score == 0.0

    def test_comma_string(self) -> None:
        assert score_probe(MULTI, "A, B").score == 1.0

    def test_empty_when_nothing_applies(self) -> None:
        none_apply = _probe(ProbeFormat.MULTI, options=["x", "y"], answer=[])
        assert score_probe(none_apply, []).score == 1.0
        assert score_probe(none_apply, ["A"]).score == 0.0

    def test_stale_pick_flagged(self) -> None:
        assert score_probe(MULTI, ["A", "B", "E"]).stale


class TestValue:
    MONEY = _probe(
        ProbeFormat.VALUE, answer=["$62,500"], value_kind=ValueKind.MONEY, stale=["$48,000"]
    )

    def test_match_across_formats(self) -> None:
        assert score_probe(self.MONEY, "62.5k").score == 1.0

    def test_stale(self) -> None:
        result = score_probe(self.MONEY, "$48,000")
        assert result.score == 0.0
        assert result.stale

    def test_numeric_answer_accepted(self) -> None:
        assert score_probe(self.MONEY, 62500).score == 1.0

    def test_abstention_probe(self) -> None:
        probe = _probe(ProbeFormat.VALUE, answer=[NOT_STATED], value_kind=ValueKind.MONEY)
        right = score_probe(probe, "NOT_STATED")
        assert right.score == 1.0
        assert right.expects_abstention
        assert score_probe(probe, "$10").score == 0.0

    def test_not_stated_on_a_real_value_scores_zero(self) -> None:
        result = score_probe(self.MONEY, "not stated")
        assert result.score == 0.0
        assert result.abstained


class TestList:
    PROBE = _probe(
        ProbeFormat.LIST,
        answer=["billing service", "rate limiter"],
        value_kind=ValueKind.TEXT,
        stale=["session store"],
    )

    def test_exact_set_any_order(self) -> None:
        assert score_probe(self.PROBE, ["Rate limiter", "the billing service"]).score == 1.0

    def test_extra_values_cost(self) -> None:
        result = score_probe(self.PROBE, ["billing service", "rate limiter", "session store"])
        assert result.score == 0.5
        assert result.stale

    def test_not_stated(self) -> None:
        assert score_probe(self.PROBE, ["NOT_STATED"]).abstained


class TestCounted:
    ABSTAIN = _probe(
        ProbeFormat.SINGLE,
        category=ProbeCategory.ABSTENTION,
        options=["Postgres", "MySQL", NOT_STATED],
        answer=[NOT_STATED],
    )

    def test_a_right_abstention_earns_nothing(self) -> None:
        results = [score_probe(self.ABSTAIN, "C"), score_probe(SINGLE, "B")]
        assert counted(results) == [1.0]

    def test_a_wrong_abstention_counts_as_a_miss(self) -> None:
        results = [score_probe(self.ABSTAIN, "A"), score_probe(SINGLE, "B")]
        assert counted(results) == [0.0, 1.0]

    def test_an_empty_selection_is_treated_as_an_abstention(self) -> None:
        empty = _probe(ProbeFormat.MULTI, options=["a", "b", "c"], answer=[])
        assert score_probe(empty, []).expects_abstention
        assert counted([score_probe(empty, [])]) == []
        assert counted([score_probe(empty, ["A"])]) == [0.0]
