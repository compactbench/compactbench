"""Run-level metrics."""

from __future__ import annotations

import pytest

from compactbench.contracts import CaseResult, CycleResult, ProbeResult
from compactbench.scoring import compute_metrics

pytestmark = pytest.mark.unit


def _r(
    key: str,
    score: float,
    *,
    stale: bool = False,
    stale_possible: bool = False,
    abstains: bool = False,
    abstained: bool = False,
    answered: bool = True,
    category: str = "decision_state",
) -> ProbeResult:
    return ProbeResult(
        key=key,
        category=category,
        format="single",
        origin_cycle=0,
        score=score,
        answered=answered,
        stale=stale,
        stale_possible=stale_possible,
        expects_abstention=abstains,
        abstained=abstained,
    )


def _cycle(
    index: int,
    results: list[ProbeResult],
    *,
    oracle: float | None = None,
    null: float | None = None,
    artifact_tokens: int = 100,
    over_budget: bool = False,
) -> CycleResult:
    if oracle is not None or null is not None:
        # Controls are kept per probe; the cycle-level numbers are their summary.
        results = [
            r.model_copy(update={"oracle_score": oracle, "null_score": null}) for r in results
        ]
    return CycleResult(
        cycle=index,
        score=sum(r.score for r in results) / len(results),
        probe_results=results,
        source_tokens=1000,
        input_tokens=500,
        artifact_tokens=artifact_tokens,
        budget_tokens=200,
        over_budget=over_budget,
        oracle_score=oracle,
        null_score=null,
    )


def _case(family: str, cycles: list[CycleResult], case_id: str = "c") -> CaseResult:
    scores = [r.score for c in cycles for r in c.probe_results]
    return CaseResult(
        case_id=case_id,
        family=family,
        seed=0,
        cycles=cycles,
        score=sum(scores) / len(scores),
    )


def test_score_is_family_balanced() -> None:
    big = _case("a", [_cycle(0, [_r(f"k{i}", 1.0) for i in range(9)])], "a1")
    small = _case("b", [_cycle(0, [_r("k", 0.0)])], "b1")
    metrics = compute_metrics([big, small])
    assert metrics.score == pytest.approx(0.5)
    assert metrics.by_family["a"].probes == 9


def test_drift_resistance_uses_probes_carried_across_cycles() -> None:
    case = _case(
        "a",
        [
            _cycle(0, [_r("x", 1.0), _r("y", 1.0)]),
            _cycle(1, [_r("x", 1.0), _r("y", 0.0), _r("new", 1.0)]),
        ],
    )
    metrics = compute_metrics([case])
    assert metrics.drift_resistance == pytest.approx(0.5)
    assert metrics.decay == pytest.approx(0.5)
    assert metrics.by_cycle == [pytest.approx(1.0), pytest.approx(2 / 3)]


def test_abstention_probes_do_not_inflate_drift() -> None:
    """An artifact that keeps nothing still answers 'never decided' right every cycle."""
    case = _case(
        "a",
        [
            _cycle(0, [_r("x", 0.0), _r("parked", 1.0, abstains=True, abstained=True)]),
            _cycle(1, [_r("x", 0.0), _r("parked", 1.0, abstains=True, abstained=True)]),
        ],
    )
    assert compute_metrics([case]).drift_resistance == 0.0


def test_no_drift_cycles_means_unmeasured_drift() -> None:
    case = _case("a", [_cycle(0, [_r("x", 1.0)])])
    metrics = compute_metrics([case])
    assert metrics.drift_resistance == 0.0
    assert metrics.decay == 0.0


def test_stale_and_hallucination_rates() -> None:
    case = _case(
        "a",
        [
            _cycle(
                0,
                [
                    _r("s1", 0.0, stale=True, stale_possible=True),
                    _r("s2", 1.0, stale_possible=True),
                    _r("p1", 0.0, abstains=True),
                    _r("p2", 1.0, abstains=True, abstained=True),
                    _r("p3", 0.0, abstains=True, answered=False),
                ],
            )
        ],
    )
    metrics = compute_metrics([case])
    assert metrics.stale_rate == pytest.approx(0.5)
    assert metrics.hallucination_rate == pytest.approx(1 / 3)
    assert metrics.reader_error_rate == pytest.approx(0.2)


def test_normalized_score_from_controls() -> None:
    case = _case("a", [_cycle(0, [_r("x", 0.6)], oracle=0.9, null=0.1)])
    metrics = compute_metrics([case])
    assert metrics.by_family["a"].normalized_score == pytest.approx(0.625)
    assert metrics.normalized_score == pytest.approx(0.625)


def test_normalized_score_absent_without_controls_or_gap() -> None:
    plain = compute_metrics([_case("a", [_cycle(0, [_r("x", 0.6)])])])
    assert plain.normalized_score is None
    flat = compute_metrics([_case("a", [_cycle(0, [_r("x", 0.6)], oracle=0.5, null=0.48)])])
    assert flat.by_family["a"].normalized_score is None


def test_ci_brackets_the_score() -> None:
    cases = [_case("a", [_cycle(0, [_r("x", float(i % 2))])], f"a{i}") for i in range(10)] + [
        _case("b", [_cycle(0, [_r("x", 0.8)])], f"b{i}") for i in range(10)
    ]
    metrics = compute_metrics(cases)
    assert metrics.score_ci_low <= metrics.score <= metrics.score_ci_high
    assert metrics.score_ci_low < metrics.score_ci_high


def test_budget_and_compression() -> None:
    case = _case(
        "a",
        [
            _cycle(0, [_r("x", 1.0)], artifact_tokens=100),
            _cycle(1, [_r("x", 1.0)], artifact_tokens=250, over_budget=True),
        ],
    )
    metrics = compute_metrics([case])
    assert metrics.budget_violations == 1
    assert metrics.mean_artifact_tokens == pytest.approx(175)
    assert metrics.compression_ratio == pytest.approx((10 + 4) / 2)


def test_empty_run() -> None:
    metrics = compute_metrics([])
    assert metrics.score == 0.0
    assert metrics.drift_resistance == 0.0


def test_mixed_cases_score_each_family_from_its_own_probes() -> None:
    def tagged(key: str, score: float, family: str) -> ProbeResult:
        return _r(key, score).model_copy(update={"family": family})

    mixed = [
        _case(
            "mixed",
            [
                _cycle(
                    0, [tagged("a/x", 1.0, "a"), tagged("a/y", 1.0, "a"), tagged("b/x", 0.0, "b")]
                )
            ],
            f"m{i}",
        )
        for i in range(3)
    ]
    metrics = compute_metrics(mixed)
    assert set(metrics.by_family) == {"a", "b"}
    assert metrics.by_family["a"].score == 1.0
    assert metrics.by_family["b"].score == 0.0
    assert metrics.by_family["a"].cases == 3
    # Family-balanced: b's single probe weighs as much as a's two.
    assert metrics.score == pytest.approx(0.5)
