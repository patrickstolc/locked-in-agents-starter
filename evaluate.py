"""Measure interpretation and state outcomes using fixed, independent fixtures.

Every input gets a fresh setup. Only public observations and four complete turns
reach the model; private snapshots below are for the local evaluation log.
"""
import argparse
import copy
import json
import os
import statistics
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path

from cases import CASES, INITIAL_INTERNAL
from errors import ModelError
from locked_in import play_turn
from world import State, apply_action, get_schema, view

KNOWLEDGE_FIELDS = {"known", "reader_examined"}


def stable_snapshot(value):
    """Recursively normalize nested dataclasses, mappings, sequences and sets."""
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    if isinstance(value, dict):
        return {key: stable_snapshot(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted((stable_snapshot(item) for item in value),
                      key=lambda item: json.dumps(item, sort_keys=True))
    if isinstance(value, (list, tuple)):
        return [stable_snapshot(item) for item in value]
    return value


def internal_snapshot(state):
    return stable_snapshot(state)


def apply_delta(snapshot, delta):
    """Apply declared fixture changes; never call the game's transition function."""
    result = copy.deepcopy(snapshot)
    for key, value in delta.items():
        if key in {"known_add", "inventory_add", "inventory_remove"}:
            field, operation = key.rsplit("_", 1)
            existing = set(result[field])
            result[field] = sorted(existing | set(value) if operation == "add" else existing - set(value))
        elif key in result:
            result[key] = stable_snapshot(value)
        else:
            raise ValueError("Unknown fixture field: " + key)
    return result


def expected_internal(case, *, after=True):
    result = copy.deepcopy(INITIAL_INTERNAL)
    for setup in case["setup"]:
        result = apply_delta(result, setup["delta"])
    return apply_delta(result, case["delta"]) if after else result


def state_from_snapshot(snapshot):
    fields = copy.deepcopy(snapshot)
    fields["known"], fields["inventory"] = set(fields["known"]), set(fields["inventory"])
    return State(**fields)


def invariants_hold(state):
    """Check discovery prerequisites, item conservation and irreversible progress."""
    portable = {"brass_key", "battery", "keycard"}
    all_objects = {"room", "door", "desk", "drawer", "false_bottom", "radio",
                   "battery_hatch", "locker", "reader", *portable}
    booleans = ("drawer_open", "bottom_open", "hatch_open", "locker_open",
                "reader_examined", "reader_powered", "door_unlocked", "escaped")
    if (type(state.known) is not set or type(state.inventory) is not set
            or any(type(getattr(state, field)) is not bool for field in booleans)):
        return False
    return all([
        {"room", "door"} <= state.known <= all_objects,
        state.inventory <= portable and state.inventory <= state.known,
        state.key_location in {"under_bottom", "inventory"},
        state.battery_location in {"in_radio", "inventory", "installed"},
        state.card_location in {"in_locker", "inventory"},
        ("brass_key" in state.inventory) == (state.key_location == "inventory"),
        ("battery" in state.inventory) == (state.battery_location == "inventory"),
        ("keycard" in state.inventory) == (state.card_location == "inventory"),
        state.reader_powered == (state.battery_location == "installed"),
        "drawer" not in state.known or "desk" in state.known,
        "false_bottom" not in state.known or ("drawer" in state.known and state.drawer_open),
        "brass_key" not in state.known or state.bottom_open,
        "battery_hatch" not in state.known or "radio" in state.known,
        "battery" not in state.known or state.hatch_open,
        "keycard" not in state.known or state.locker_open,
        not state.reader_examined or "reader" in state.known,
        not state.drawer_open or "drawer" in state.known,
        not state.bottom_open or (state.drawer_open and {"false_bottom", "brass_key"} <= state.known),
        not state.hatch_open or {"battery_hatch", "battery"} <= state.known,
        not state.locker_open or ({"locker", "keycard"} <= state.known and "brass_key" in state.inventory),
        not state.reader_powered or {"reader", "battery"} <= state.known,
        not state.door_unlocked or (state.reader_powered and "keycard" in state.inventory),
        not state.escaped or state.door_unlocked,
    ])


def prepare_case(case):
    state, history = State(), []
    expected = copy.deepcopy(INITIAL_INTERNAL)
    if internal_snapshot(state) != expected:
        raise ValueError("The game's initial state differs from the fixture.")
    for index, setup in enumerate(case["setup"], start=1):
        feedback = apply_action(state, setup["action"])
        expected = apply_delta(expected, setup["delta"])
        if internal_snapshot(state) != expected or not invariants_hold(state):
            raise ValueError(f"{case['id']}: setup step {index} differs from its declared outcome.")
        history.append({"player": setup["player"], "action": dict(setup["action"]), "feedback": feedback})
    return state, history[-4:]


def run_case(case, prompt, *, temperature=0.2, timeout=60.0, model=None, base_url=None, backend="framework"):
    state, history = prepare_case(case)
    before, before_internal = view(state), internal_snapshot(state)
    before_history = copy.deepcopy(history)
    expected = expected_internal(case)
    expected_public = view(state_from_snapshot(expected))
    started, error, feedback = time.perf_counter(), None, None
    try:
        feedback, metrics = play_turn(state, history, case["text"], prompt=prompt,
                                      temperature=temperature, timeout=timeout,
                                      model=model, base_url=base_url, backend=backend)
    except ModelError as failure:
        metrics, error = failure.metrics, str(failure)
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    contract_valid = error is None and metrics.get("first_response_contract_valid") is True
    interpretation_correct = contract_valid and metrics.get("action") in case["expected_actions"]
    after_internal = internal_snapshot(state)
    invariant_success = invariants_hold(state)
    knowledge_correct = ({key: after_internal[key] for key in KNOWLEDGE_FIELDS}
                         == {key: expected[key] for key in KNOWLEDGE_FIELDS})
    physical_correct = ({key: value for key, value in after_internal.items() if key not in KNOWLEDGE_FIELDS}
                        == {key: value for key, value in expected.items() if key not in KNOWLEDGE_FIELDS})
    state_correct = after_internal == expected and invariant_success
    return {
        "case": case["id"], "prompt": prompt, "player": case["text"],
        "setup": case["setup"], "state_before": before,
        "internal_state_before": before_internal, "history_before": before_history,
        "response_schema": get_schema(state_from_snapshot(before_internal)),
        "expected_actions": case["expected_actions"], "expected_state": expected_public,
        "expected_internal_state": expected,
        **metrics, "elapsed_ms": elapsed_ms, "feedback": feedback, "error": error,
        "contract_valid": contract_valid, "interpretation_correct": interpretation_correct,
        "knowledge_correct": knowledge_correct, "physical_state_correct": physical_correct,
        "state_correct": state_correct, "invariants_hold": invariant_success,
        "failed_call_preserved_state_and_history": None if error is None else (
            after_internal == before_internal and history == before_history),
        "end_to_end_correct": interpretation_correct and state_correct,
        "state_after": view(state), "internal_state_after": after_internal,
    }


def warm_up(prompt, **options):
    """Warm the model without requiring a valid game action from the warm-up."""
    state = State()
    try:
        play_turn(state, [], "Look around the room.", prompt=prompt, **options)
    except ModelError as error:
        if error.metrics.get("first_response_contract_valid") is False:
            return "Warm-up reached the model but its response was invalid. Continuing with the cases."
        raise
    return "Warm-up complete."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("http", "framework"), default="framework")
    parser.add_argument("--prompt", choices=["both", "baseline", "revised"], default="both")
    parser.add_argument("--model", default=os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"))
    parser.add_argument("--base-url", default=os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1"))
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--pause", type=float, default=2.1,
                        help="Seconds between calls; adjust for your provider's rate limit")
    parser.add_argument("--cases", help="Optional comma-separated IDs, e.g. C03,C04")
    parser.add_argument("--output", default="evaluation.jsonl")
    args = parser.parse_args()
    if args.repeat < 1 or args.timeout <= 0 or args.pause < 0 or not 0 <= args.temperature <= 2:
        parser.error("Use a positive repeat count and timeout, and temperature 0–2.")
    cases = CASES
    if args.cases:
        selected = {name.strip() for name in args.cases.split(",")}
        unknown = selected - {case["id"] for case in CASES}
        if unknown:
            parser.error("Unknown case IDs: " + ", ".join(sorted(unknown)))
        cases = [case for case in CASES if case["id"] in selected]
    output = Path(args.output)
    if output.exists():
        parser.error("Output already exists; choose a new --output filename.")
    prompts = ["baseline", "revised"] if args.prompt == "both" else [args.prompt]
    print(f"Model: {args.model}; temperature: {args.temperature}; API: {args.base_url}")
    print("Warming up the model; this request is excluded from the results.")
    try:
        print(warm_up(prompts[0], model=args.model, base_url=args.base_url,
                      temperature=args.temperature, timeout=args.timeout, backend=args.backend))
    except ModelError as error:
        parser.exit(2, f"Warm-up failed: {error}\nCheck the provider, key, model and output format.\n")
    records = []
    with output.open("x", encoding="utf-8") as log:
        for repeat in range(1, args.repeat + 1):
            for case in cases:
                for prompt in prompts:
                    record = run_case(case, prompt, temperature=args.temperature,
                                      timeout=args.timeout, model=args.model, base_url=args.base_url, backend=args.backend)
                    record["repeat"] = repeat
                    records.append(record)
                    log.write(json.dumps(record) + "\n")
                    log.flush()
                    print(f"{case['id']} {prompt:8} contract={record['contract_valid']} "
                          f"intent={record['interpretation_correct']} knowledge={record['knowledge_correct']} "
                          f"physical={record['physical_state_correct']} {record['elapsed_ms']} ms")
                    if args.pause:
                        time.sleep(args.pause)
    print("\nPrompt | Contract | Intent | Knowledge | Physical | Full state | End-to-end | Median ms")
    for prompt in prompts:
        rows = [row for row in records if row["prompt"] == prompt]
        fields = ("contract_valid", "interpretation_correct", "knowledge_correct",
                  "physical_state_correct", "state_correct", "end_to_end_correct")
        scores = [f"{sum(row[field] for row in rows)}/{len(rows)}" for field in fields]
        median = round(statistics.median(row["elapsed_ms"] for row in rows))
        print(" | ".join([prompt, *scores, str(median)]))
    print("\nEvery tested input is in the denominator. Failed calls fail contract and interpretation.")
    print("A correct state alone does not establish that the requested action was understood.")
    print(f"Invariant violations: {sum(not row['invariants_hold'] for row in records)}")
    print(f"Failed calls that changed state/history: {sum(row['failed_call_preserved_state_and_history'] is False for row in records)}")
    print(f"Responses, public/private snapshots, errors and timings: {output}")


if __name__ == "__main__":
    main()
