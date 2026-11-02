"""Scenario engine: determinism, validity, size, and the properties the families promise."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

from compactbench.contracts import NOT_STATED, ProbeFormat
from compactbench.rendering import render_turns
from compactbench.scenarios import (
    PROFILES,
    PUBLIC_FAMILIES,
    PUBLIC_LEXICON,
    SUITES,
    Difficulty,
    expand_suite,
    generate_case,
    get_suite,
    load_suite_pack,
)
from compactbench.scenarios.rng import Rng, derive_seed
from compactbench.tokens import count_tokens

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("family", PUBLIC_FAMILIES)
def test_generation_is_deterministic(family: str) -> None:
    a = generate_case(family, 1234, Difficulty.MEDIUM)
    b = generate_case(family, 1234, Difficulty.MEDIUM)
    assert a.model_dump_json() == b.model_dump_json()


@pytest.mark.parametrize("family", PUBLIC_FAMILIES)
def test_different_seeds_give_different_cases(family: str) -> None:
    a = generate_case(family, 1, Difficulty.EASY)
    b = generate_case(family, 2, Difficulty.EASY)
    assert render_turns(a.cycles[0].turns) != render_turns(b.cycles[0].turns)


@pytest.mark.parametrize("family", PUBLIC_FAMILIES)
@pytest.mark.parametrize("difficulty", [Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD])
def test_cases_hit_their_size_targets(family: str, difficulty: Difficulty) -> None:
    profile = PROFILES[difficulty]
    case = generate_case(family, 99, difficulty)
    assert case.drift_cycles == profile.drift_cycles
    opening = count_tokens(render_turns(case.cycles[0].turns))
    # Signal turns count toward the target, so short profiles can overshoot a little.
    assert profile.initial_tokens * 0.95 <= opening <= profile.initial_tokens + 1_500
    for spec in case.cycles[1:]:
        assert count_tokens(render_turns(spec.turns)) >= profile.cycle_tokens * 0.9


@pytest.mark.slow
@pytest.mark.parametrize("family", PUBLIC_FAMILIES)
def test_elite_cases_are_long(family: str) -> None:
    case = generate_case(family, 7, Difficulty.ELITE)
    assert count_tokens(render_turns(case.cycles[0].turns)) >= 30_000


@pytest.mark.parametrize("family", PUBLIC_FAMILIES)
@pytest.mark.parametrize("seed", [3, 17, 2026])
def test_probe_invariants(family: str, seed: int) -> None:
    case = generate_case(family, seed, Difficulty.HARD)
    for spec in case.cycles:
        assert spec.probes, f"cycle {spec.cycle} asks nothing"
        keys = [p.key for p in spec.probes]
        assert len(keys) == len(set(keys))
        for probe in spec.probes:
            assert probe.origin_cycle <= spec.cycle
            assert not set(probe.stale) & set(probe.answer)
            if probe.format == ProbeFormat.SINGLE:
                assert probe.options[-1] == NOT_STATED
            if probe.format == ProbeFormat.MULTI:
                wrong = len(probe.options) - len(probe.answer)
                assert wrong >= len(probe.answer), "select-all must not pay"


@pytest.mark.parametrize("family", ["entity_confusion", "reference_resolution"])
def test_named_answers_appear_in_the_conversation(family: str) -> None:
    case = generate_case(family, 11, Difficulty.MEDIUM)
    for spec in case.cycles:
        text = render_turns(case.transcript_through(spec.cycle).turns)
        for probe in spec.probes:
            if probe.format == ProbeFormat.SINGLE and probe.answer != [NOT_STATED]:
                assert probe.answer[0] in text, (probe.key, probe.answer)


def test_answers_change_across_cycles_somewhere() -> None:
    """Later cycles must carry real change, or drift measures nothing."""
    changed = 0
    for case in expand_suite(
        get_suite("starter"), cases_per_family=2, difficulty=Difficulty.MEDIUM
    ):
        first = {p.key: p.answer for p in case.cycles[0].probes}
        last = {p.key: p.answer for p in case.cycles[-1].probes}
        changed += sum(1 for k in first.keys() & last.keys() if first[k] != last[k])
    assert changed > 0


def test_entity_confusion_always_has_lookalikes() -> None:
    case = generate_case("entity_confusion", 5, Difficulty.EASY)
    roles = [p for p in case.cycles[0].probes if p.key.startswith("role_")]
    assert len(roles) >= 2


def test_expand_suite_is_stable_and_seed_group_resamples() -> None:
    suite = get_suite("starter")
    a = expand_suite(suite, cases_per_family=2)
    b = expand_suite(suite, cases_per_family=2)
    c = expand_suite(suite, cases_per_family=2, seed_group="other")
    assert [x.case_id for x in a] == [x.case_id for x in b]
    assert len(a) == 2 * len(suite.families)
    assert not {x.case_id for x in a} & {x.case_id for x in c}


def test_builtin_suites() -> None:
    assert SUITES["starter"].difficulty == Difficulty.EASY
    assert SUITES["practice"].difficulty == Difficulty.ELITE
    # Practice mirrors ranked Elite: every case is a mixed session of all families.
    assert SUITES["practice"].families == ("mixed",)
    assert set(SUITES["drills"].families) == set(PUBLIC_FAMILIES)


def test_drift_cycles_override_and_bounds() -> None:
    assert generate_case("decision_override", 1, Difficulty.EASY, drift_cycles=0).drift_cycles == 0
    with pytest.raises(ValueError, match="between 0 and"):
        generate_case("decision_override", 1, Difficulty.EASY, drift_cycles=99)


def test_suite_pack_registers_suites(tmp_path: Path) -> None:
    pack = tmp_path / "pack.py"
    pack.write_text(
        "from compactbench.scenarios import Suite, Difficulty\n"
        "SUITES = [Suite(key='elite_test', version='9.9.9', description='x',\n"
        "    families=('buried_constraint',), difficulty=Difficulty.EASY, cases_per_family=1)]\n",
        encoding="utf-8",
    )
    suites = load_suite_pack(pack)
    assert [s.key for s in suites] == ["elite_test"]
    assert len(expand_suite(get_suite("elite_test"))) == 1


def test_suite_pack_without_suites_is_rejected(tmp_path: Path) -> None:
    pack = tmp_path / "empty.py"
    pack.write_text("X = 1\n", encoding="utf-8")
    with pytest.raises(ImportError, match="SUITES"):
        load_suite_pack(pack)


def test_rng_children_are_independent() -> None:
    root = Rng(42)
    first = root.child("a").random()
    root.random()
    assert root.child("a").random() == first
    assert derive_seed(42, "a") != derive_seed(42, "b")


@pytest.mark.parametrize("family", PUBLIC_FAMILIES)
def test_select_probes_always_have_an_answer(family: str) -> None:
    # An empty right answer is one an empty context would get right for free.
    for seed in range(12):
        case = generate_case(family, seed, Difficulty.HARD)
        for spec in case.cycles:
            for probe in spec.probes:
                if probe.format in (ProbeFormat.MULTI, ProbeFormat.LIST):
                    assert probe.answer, (seed, spec.cycle, probe.key)


def test_ended_scope_policies_get_an_affirmative_answer() -> None:
    seen = 0
    for seed in range(40):
        case = generate_case("conditional_scope", seed, Difficulty.HARD)
        for spec in case.cycles:
            for probe in spec.probes:
                if probe.key.startswith("scope_") and probe.format == ProbeFormat.SINGLE:
                    seen += 1
                    assert probe.answer == ["Nothing: it has ended"]
                    assert NOT_STATED in probe.options
    assert seen


def test_a_blocker_only_lands_once_it_is_done() -> None:
    landed = re.compile(r"([A-Z]+-\d+) landed, so ([A-Z]+-\d+) is unblocked")
    found = 0
    for seed in range(40):
        case = generate_case("task_continuity", seed, Difficulty.HARD)
        text = render_turns(case.transcript_through(case.drift_cycles).turns)
        for match in landed.finditer(text):
            found += 1
            before, blocker = text[: match.start()], match.group(1)
            assert (
                f"{blocker} is Done" in before
                or f"Closing {blocker}" in before
                or re.search(rf"{re.escape(blocker)} — .* — Done", before)
            ), (seed, blocker)
    assert found


def test_the_last_handover_in_the_transcript_is_the_owner_on_record() -> None:
    # Two handovers in one cycle must reach the transcript in the order the answer
    # key applied them, or the last one a reader sees isn't the owner it expects.
    moved = re.compile(
        r"the (?P<c1>[\w -]+) moves from [\w .'-]+ to (?P<n1>[\w .'-]+?), effective now"
        r"|(?P<n2>[\w .'-]+?) has taken over the (?P<c2>[\w -]+?) from "
    )
    checked = 0
    for seed in range(12):
        case = generate_case("entity_confusion", seed, Difficulty.ELITE)
        for spec in case.cycles:
            text = render_turns(case.transcript_through(spec.cycle).turns)
            last: dict[str, str] = {}
            for m in moved.finditer(text):
                component = (m.group("c1") or m.group("c2")).strip()
                # Embedded statements can sit in a bulleted list.
                last[component] = (m.group("n1") or m.group("n2")).strip().lstrip("-*• ")
            for probe in spec.probes:
                component = probe.key.removeprefix("owner_").replace("_", " ")
                if probe.key.startswith("owner_") and component in last:
                    checked += 1
                    assert last[component] == probe.answer[0], (seed, spec.cycle, component)
    assert checked


def _edits(a: str, b: str) -> int:
    row = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, cb in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (ca != cb))
    return row[-1]


def test_lookalike_surnames_are_confusable_but_distinct() -> None:
    # One letter apart is past what even a reader with the full conversation keeps
    # straight; the shared first name is what makes these people confusable.
    for group in PUBLIC_LEXICON.lookalike_last_names:
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                assert _edits(a.casefold(), b.casefold()) >= 2, (a, b)


def test_scoped_policy_statements_name_their_policy() -> None:
    # Otherwise "what does the script lock cover?" asks the reader to guess which
    # statement was the script lock.
    for policy in PUBLIC_LEXICON.scoped_policies:
        for statement in policy.statements:
            assert policy.label.casefold() in statement.casefold(), (policy.key, statement)


def test_mixed_sessions_carry_every_family() -> None:
    case = generate_case("mixed", 5, Difficulty.HARD)
    for spec in case.cycles:
        assert {p.family for p in spec.probes} == set(PUBLIC_FAMILIES)
        assert all(p.key.startswith(f"{p.family}/") for p in spec.probes)
    again = generate_case("mixed", 5, Difficulty.HARD)
    assert case.model_dump_json() == again.model_dump_json()


def test_mixed_members_never_share_a_topic() -> None:
    # decision_override and provenance_authority both draw from the topics pool;
    # sharing one would give the same question two different right answers.
    for seed in range(15):
        case = generate_case("mixed", seed, Difficulty.HARD)
        keys = {p.key for spec in case.cycles for p in spec.probes}
        decided = {k.split("/decision_", 1)[1] for k in keys if "/decision_" in k}
        claimed = {k.split("/authority_", 1)[1] for k in keys if "/authority_" in k}
        assert not decided & claimed, (seed, decided & claimed)


def test_probe_subset_is_family_balanced_and_stable_across_cycles() -> None:
    full = generate_case("mixed", 9, Difficulty.HARD)
    sub = generate_case("mixed", 9, Difficulty.HARD, probes=40)
    assert [c.turns for c in sub.cycles] == [c.turns for c in full.cycles]
    for spec in sub.cycles:
        assert 30 <= len(spec.probes) <= 40
        counts = Counter(p.family for p in spec.probes)
        assert set(counts) == set(PUBLIC_FAMILIES)
        assert max(counts.values()) - min(counts.values()) <= 3
    first = {p.key for p in sub.cycles[0].probes}
    last = {p.key for p in sub.cycles[-1].probes}
    assert len(first & last) >= 30, "carried probes stay in the subset"
