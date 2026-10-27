"""Offline checks for the starter framework and the reference implementation."""
import copy
import json
import os
import unittest
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import evaluate
import interpreter_http as interpreter
import locked_in
from cases import CASES
from errors import ModelError
from world import State, apply_action, get_schema, view


def a(action, *, item="", target="", focus=""):
    return {"action": action, "item": item, "target": target, "focus": focus}


class FakeResponse:
    def __init__(self, answer):
        self.body = json.dumps({"choices": [{"finish_reason": "stop", "message": {
            "role": "assistant", "content": json.dumps(answer)}}]}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self.body


class TestRoom(unittest.TestCase):
    def test_first_observation_does_not_leak(self):
        public = view(State())
        self.assertEqual(public["known_ids"], ["door", "room"])
        self.assertNotIn("brass_key", json.dumps(public))
        self.assertEqual(get_schema(State())["properties"]["target"]["enum"], ["", "door", "room"])

    def test_full_discovery_and_escape(self):
        state = State()
        commands = [
            a("look", target="room", focus="general"),
            a("look", target="desk", focus="underneath"),
            a("open", target="drawer"),
            a("look", target="drawer", focus="seams"),
            a("open", target="false_bottom"),
            a("take", item="brass_key"),
            a("use", item="brass_key", target="locker"),
            a("take", item="keycard"),
            a("look", target="radio", focus="back"),
            a("open", target="battery_hatch"),
            a("take", item="battery"),
            a("use", item="battery", target="reader"),
            a("use", item="keycard", target="reader"),
            a("open", target="door"),
        ]
        for command in commands:
            apply_action(state, command)
        self.assertTrue(state.escaped)
        self.assertNotIn("battery", state.inventory)

    def test_asking_does_not_open_a_drawer(self):
        state = State()
        apply_action(state, a("look", target="room", focus="general"))
        apply_action(state, a("look", target="desk", focus="underneath"))
        text = apply_action(state, a("look", target="drawer", focus="inside"))
        self.assertIn("closed", text)
        self.assertFalse(state.drawer_open)

    def test_key_only_after_false_bottom_is_open(self):
        state = State()
        apply_action(state, a("look", target="room", focus="general"))
        apply_action(state, a("look", target="desk", focus="underneath"))
        apply_action(state, a("open", target="drawer"))
        apply_action(state, a("look", target="drawer", focus="seams"))
        self.assertNotIn("brass_key", state.known)
        apply_action(state, a("open", target="false_bottom"))
        self.assertIn("brass_key", state.known)
        self.assertNotIn("brass_key", state.inventory)


class TestAdapter(unittest.TestCase):
    def ok(self, action):
        return action, {"model": "demo", "temperature": 0.2, "attempts": 1,
                        "elapsed_ms": 21, "raw_content": json.dumps(action),
                        "first_response_contract_valid": True}

    def test_public_view_is_only_state_given_to_interpreter(self):
        state, history = State(), []
        with patch("locked_in.interpret_request", return_value=self.ok(a("look", target="room", focus="general"))) as stub:
            locked_in.play_turn(state, history, "What's in the room?")
        self.assertEqual(stub.call_args.args[1]["known_ids"], ["door", "room"])
        self.assertIsInstance(stub.call_args.args[2], dict)
        self.assertNotIsInstance(stub.call_args.args[1], State)

    def test_rejected_physical_action_still_enters_history(self):
        state = State()
        apply_action(state, a("look", target="room", focus="general"))
        apply_action(state, a("look", target="radio", focus="back"))
        apply_action(state, a("open", target="battery_hatch"))
        history = []
        cmd = a("use", item="battery", target="reader")
        with patch("locked_in.interpret_request", return_value=self.ok(cmd)):
            feedback, _ = locked_in.play_turn(state, history, "Fit the battery in the reader")
        self.assertIn("carrying", feedback)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["action"], cmd)

    def test_model_failure_preserves_state_and_history(self):
        state, history = State(), []
        before = copy.deepcopy(state)
        with patch("locked_in.interpret_request", side_effect=ModelError("timeout", {"attempts": 2})):
            with self.assertRaises(ModelError):
                locked_in.play_turn(state, history, "Look around")
        self.assertEqual(state, before)
        self.assertEqual(history, [])

    def test_invalid_action_preserves_state_and_history(self):
        state, history = State(), []
        with patch("locked_in.interpret_request", return_value=self.ok(a("take", item="brass_key"))):
            with self.assertRaises(ModelError) as cm:
                locked_in.play_turn(state, history, "Take the key")
        self.assertIs(cm.exception.metrics["first_response_contract_valid"], False)
        self.assertEqual(state, State())
        self.assertEqual(history, [])

    def test_history_is_limited_to_four_complete_turns(self):
        state, history = State(), []
        with patch("locked_in.interpret_request", return_value=self.ok(a("look", target="room", focus="general"))):
            for i in range(7):
                locked_in.play_turn(state, history, f"Inspect again #{i}")
        self.assertEqual(len(history), 4)
        self.assertEqual(history[0]["player"], "Inspect again #3")
        self.assertTrue(all(set(turn) == {"player", "action", "feedback"} for turn in history))

    def test_invalid_length_never_calls_model(self):
        with patch("locked_in.interpret_request") as stub:
            with self.assertRaises(ValueError):
                locked_in.play_turn(State(), [], " " * 501)
            stub.assert_not_called()


class TestHTTP(unittest.TestCase):
    def setUp(self):
        self.state = State()
        self.schema = get_schema(self.state)
        self.messages = interpreter.build_messages("What's in here?", view(self.state), self.schema, [], "baseline")
        self.command = a("look", target="room", focus="general")

    def kwargs(self):
        return {"api_key": "test-key", "base_url": "https://api.example.net/v1", "model": "example-model"}

    def test_baseline_and_revised_are_different(self):
        revised = interpreter.build_messages("What's in here?", view(self.state), self.schema, [], "revised")
        self.assertNotEqual(self.messages[0]["content"], revised[0]["content"])
        self.assertNotIn("brass_key", json.dumps(revised))

    def test_history_includes_actual_engine_feedback(self):
        historical = [{"player": "What's in here?", "action": self.command, "feedback": "A desk is visible."}]
        messages = interpreter.build_messages("Look under it.", view(self.state), self.schema,
                                              historical, "revised")
        self.assertIn("A desk is visible.", json.dumps(messages))
        self.assertEqual(messages[-1], {"role": "user", "content": "Look under it."})

    def test_http_request_and_json(self):
        recorded = {}

        def fake_urlopen(request, timeout):
            recorded["url"] = request.full_url
            recorded["payload"] = json.loads(request.data)
            recorded["auth"] = request.get_header("Authorization")
            return FakeResponse(self.command)

        with patch("interpreter_http.urlopen", side_effect=fake_urlopen):
            answer, metrics = interpreter.call_model(self.messages, self.schema, **self.kwargs())
        self.assertEqual(answer, self.command)
        self.assertEqual(recorded["auth"], "Bearer test-key")
        self.assertEqual(recorded["url"], "https://api.example.net/v1/chat/completions")
        self.assertEqual(recorded["payload"]["response_format"]["type"], "json_object")
        self.assertEqual(metrics["attempts"], 1)

    def test_plain_mode_omits_response_format(self):
        recorded = {}
        def fake_urlopen(request, timeout):
            recorded.update(json.loads(request.data))
            return FakeResponse(self.command)
        with patch.dict(os.environ, {"LLM_RESPONSE_MODE": "plain"}), patch(
            "interpreter_http.urlopen", side_effect=fake_urlopen
        ):
            interpreter.call_model(self.messages, self.schema, **self.kwargs())
        self.assertNotIn("response_format", recorded)

    def test_schema_mode_includes_discovered_ids_only(self):
        recorded = {}
        def fake_urlopen(request, timeout):
            recorded.update(json.loads(request.data))
            return FakeResponse(self.command)
        with patch.dict(os.environ, {"LLM_RESPONSE_MODE": "schema"}), patch(
            "interpreter_http.urlopen", side_effect=fake_urlopen
        ):
            interpreter.call_model(self.messages, self.schema, **self.kwargs())
        self.assertNotIn("brass_key", json.dumps(recorded))
        self.assertEqual(recorded["response_format"]["type"], "json_schema")

    def test_rate_limit_retries_once(self):
        error = HTTPError("https://api.example.net/v1/chat/completions", 429, "rate limit", {}, BytesIO(b""))
        with patch("interpreter_http.urlopen", side_effect=[error, FakeResponse(self.command)]) as open_stub, patch(
            "interpreter_http.time.sleep"):
            _, metrics = interpreter.call_model(self.messages, self.schema, **self.kwargs())
        self.assertEqual(metrics["attempts"], 2)
        self.assertEqual(open_stub.call_count, 2)

    def test_permanent_error_has_no_retry(self):
        error = HTTPError("https://api.example.net/v1/chat/completions", 401, "unauthorized", {}, BytesIO(b""))
        with patch("interpreter_http.urlopen", side_effect=error) as open_stub:
            with self.assertRaises(ModelError):
                interpreter.call_model(self.messages, self.schema, **self.kwargs())
        self.assertEqual(open_stub.call_count, 1)

    def test_second_timeout_stops(self):
        with patch("interpreter_http.urlopen", side_effect=[TimeoutError(), TimeoutError()]) as stub, patch(
            "interpreter_http.time.sleep"):
            with self.assertRaises(ModelError) as cm:
                interpreter.call_model(self.messages, self.schema, **self.kwargs())
        self.assertEqual(stub.call_count, 2)
        self.assertIsNone(cm.exception.metrics["first_response_contract_valid"])

    def test_invalid_model_json_is_not_retried(self):
        fake = FakeResponse(self.command)
        fake.body = b'{"choices":[{"finish_reason":"stop","message":{"role":"assistant","content":"not json"}}]}'
        with patch("interpreter_http.urlopen", return_value=fake) as stub:
            with self.assertRaises(ModelError) as cm:
                interpreter.call_model(self.messages, self.schema, **self.kwargs())
        self.assertEqual(stub.call_count, 1)
        self.assertFalse(cm.exception.metrics["first_response_contract_valid"])

    def test_duplicate_json_keys_rejected(self):
        fake = FakeResponse(self.command)
        fake.body = b'{"choices":[{"finish_reason":"stop","message":{"role":"assistant","content":"{\\"action\\":\\"look\\",\\"action\\":\\"look\\",\\"item\\":\\"\\",\\"target\\":\\"room\\",\\"focus\\":\\"general\\"}"}}]}'
        with patch("interpreter_http.urlopen", return_value=fake):
            with self.assertRaises(ModelError):
                interpreter.call_model(self.messages, self.schema, **self.kwargs())

    def test_bad_endpoint_rejected_before_request(self):
        with patch("interpreter_http.urlopen") as stub:
            with self.assertRaises(ModelError):
                interpreter.call_model(self.messages, self.schema, api_key="key", base_url="http://example.org/v1")
            stub.assert_not_called()

    def test_missing_key_rejected_before_request(self):
        with patch("interpreter_http.urlopen") as stub:
            with self.assertRaises(ModelError):
                interpreter.call_model(self.messages, self.schema, api_key="")
            stub.assert_not_called()


class TestEvaluator(unittest.TestCase):
    def test_all_fixtures_setup_and_expected_state_are_consistent(self):
        for case in CASES:
            state, _ = evaluate.prepare_case(case)
            before = evaluate.internal_snapshot(state)
            expected = evaluate.expected_internal(case)
            for proposed in case["expected_actions"]:
                trial = copy.deepcopy(state)
                apply_action(trial, proposed)
                self.assertEqual(evaluate.internal_snapshot(trial), expected,
                                 (case["id"], proposed))
                self.assertTrue(evaluate.invariants_hold(trial))
            self.assertTrue(evaluate.invariants_hold(state))
            self.assertTrue(before)

    def test_scoring_separates_intent_and_state(self):
        case = next(case for case in CASES if case["id"] == "C09")
        with patch("evaluate.play_turn") as fake:
            def wrong_action(state, history, text, **kwargs):
                return "That does not help.", {"action": a("look", target="room", focus="general"),
                                              "first_response_contract_valid": True}
            fake.side_effect = wrong_action
            result = evaluate.run_case(case, "baseline")
        self.assertFalse(result["interpretation_correct"])
        self.assertTrue(result["state_correct"])
        self.assertFalse(result["end_to_end_correct"])

    def test_failed_request_does_not_score_even_if_state_unchanged(self):
        case = next(case for case in CASES if case["id"] == "C03")
        with patch("evaluate.play_turn", side_effect=ModelError("failure", {"action": None,
             "first_response_contract_valid": None})):
            result = evaluate.run_case(case, "baseline")
        self.assertFalse(result["contract_valid"])
        self.assertFalse(result["interpretation_correct"])
        self.assertTrue(result["failed_call_preserved_state_and_history"])


if __name__ == "__main__":
    unittest.main()
