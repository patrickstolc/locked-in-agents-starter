"""No API account required. Tests exercise real PydanticAI and mocked transport."""
import asyncio
import copy
import json
import time
import unittest
from unittest.mock import patch
import httpx2
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from action_model import Action
from agent_runner import demo_model, execute, run
from config import Settings
from errors import ModelError
from interpreter_framework import run_typed, interpret_request
from interpreter_http import build_messages
from room_tools import RoomSession, GoalReached, BudgetReached
from world import State, view, get_schema


def action(kind, target="", focus="", item=""):
    return {"action": kind, "item": item, "target": target, "focus": focus}


class TestTypedInterpreter(unittest.TestCase):
    def test_typed_action_rejects_extra_fields_and_coercion(self):
        for invalid in [dict(action("look", "room", "general"), secret=True),
                        action("look", 4, "general"), action("dance")]:
            with self.assertRaises(ValueError):
                Action.model_validate(invalid)

    def test_valid_typed_response_uses_real_framework(self):
        wanted = action("look", "room", "general")
        model = FunctionModel(lambda messages, info: ModelResponse(parts=[TextPart(json.dumps(wanted))]))
        result, _ = asyncio.run(run_typed(model, build_messages("Look around", view(State()),
            get_schema(State()), [], "revised"), get_schema(State())))
        self.assertEqual(result, wanted)

    def test_discovery_and_combination_checks_still_apply(self):
        for proposed in [action("take", item="brass_key"), action("open", "room"),
                         action("look", "room", "")]:
            model = FunctionModel(lambda messages, info: ModelResponse(parts=[TextPart(json.dumps(proposed))]))
            with self.assertRaises(ValueError):
                asyncio.run(run_typed(model, [{"role": "user", "content": "Look"}], get_schema(State())))

    def test_invalid_output_has_no_repair_call(self):
        calls = []
        def invalid(messages, info):
            calls.append(messages)
            return ModelResponse(parts=[TextPart("not JSON")])
        with self.assertRaises(Exception):
            asyncio.run(run_typed(FunctionModel(invalid), [{"role": "user", "content": "Look"}], get_schema(State())))
        self.assertEqual(len(calls), 1)

    def test_four_turns_and_current_public_view(self):
        history = [{"player": f"turn {n}", "action": action("clarify"), "feedback": "No change"}
                   for n in range(6)]
        messages = build_messages("now", view(State()), get_schema(State()), history, "revised")
        contents = json.dumps(messages)
        self.assertNotIn("turn 0", contents)
        self.assertNotIn("turn 1", contents)
        self.assertIn("turn 5", contents)
        self.assertNotIn("key_location", contents)
        self.assertNotIn("brass_key", contents)

    def call_mock(self, responses):
        import provider
        real_client = httpx2.AsyncClient
        seen = []
        def handler(request):
            seen.append(json.loads(request.content))
            response = responses[min(len(seen)-1, len(responses)-1)]
            if isinstance(response, int):
                return httpx2.Response(response, json={"error": {"message": "temporary", "type": "test"}})
            return httpx2.Response(200, json={"id": "offline", "object": "chat.completion",
                "created": 0, "model": "mock", "choices": [{"index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": response}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}})
        def client(**kwargs):
            return real_client(transport=httpx2.MockTransport(handler), **kwargs)
        with patch.object(provider, "HTTP_CLIENT", side_effect=client), patch.dict(
                "os.environ", {"LLM_RESPONSE_MODE": "json"}):
            try:
                result = interpret_request("Look around", view(State()), get_schema(State()), [],
                                           api_key="offline-test", model="mock", base_url="https://example.test/v1")
                return result, seen
            except ModelError as error:
                return error, seen

    def test_real_provider_mapping_and_measurements_offline(self):
        (returned, metrics), seen = self.call_mock([json.dumps(action("look", "room", "general"))])
        self.assertTrue(metrics["first_response_contract_valid"])
        self.assertEqual(metrics["attempts"], 1)
        self.assertEqual(metrics["backend"], "framework")
        self.assertEqual(seen[0]["response_format"], {"type": "json_object"})
        self.assertNotIn("tools", seen[0])
        self.assertEqual(returned["target"], "room")

    def test_transport_retries_once_and_counts_actual_attempts(self):
        (_, metrics), seen = self.call_mock([503, json.dumps(action("look", "room", "general"))])
        self.assertEqual(metrics["attempts"], 2)
        self.assertEqual(len(seen), 2)

    def test_permanent_error_does_not_retry(self):
        error, seen = self.call_mock([401])
        self.assertIsInstance(error, ModelError)
        self.assertEqual(len(seen), 1)
        self.assertNotIn("offline-test", str(error))

    def test_duplicate_json_or_unknown_ids_fail_without_repair(self):
        for content in ['{"action":"clarify","action":"clarify","item":"","target":"","focus":""}',
                        json.dumps(action("take", item="brass_key"))]:
            error, seen = self.call_mock([content])
            self.assertIsInstance(error, ModelError)
            self.assertEqual(len(seen), 1)
            self.assertFalse(error.metrics["first_response_contract_valid"])

    def test_missing_key_is_caught_without_a_request(self):
        with self.assertRaises(ModelError) as result:
            interpret_request("Look", view(State()), get_schema(State()), [], api_key="")
        self.assertEqual(result.exception.metrics["attempts"], 0)


class TestAgentBoundary(unittest.TestCase):
    def test_fresh_session_cannot_see_hidden_details(self):
        result = RoomSession().observe()
        self.assertNotIn("brass_key", json.dumps(result))
        self.assertNotIn("key_location", json.dumps(result))

    def test_rejections_preserve_state(self):
        session = RoomSession()
        before = copy.deepcopy(session.state)
        for proposed in [action("take", item="brass_key"), action("open", "drawer"),
                         action("use", "door", item="keycard")]:
            self.assertFalse(session.perform(proposed)["accepted"])
            self.assertEqual(session.state, before)

    def test_known_visible_item_still_cannot_be_taken(self):
        session = RoomSession()
        session.perform(action("look", "room", "general"))
        session.perform(action("look", "radio", "back"))
        session.perform(action("open", "battery_hatch"))
        before = copy.deepcopy(session.state)
        self.assertIn("battery", view(session.state)["visible_items"])
        self.assertFalse(session.perform(action("take", item="battery"))["accepted"])
        self.assertEqual(session.state, before)

    def test_invalid_typed_tool_arguments_have_no_effect(self):
        def model(messages, info):
            return ModelResponse(parts=[ToolCallPart("perform_action", {"action": {"action": "open"}})])
        session = RoomSession()
        before = copy.deepcopy(session.state)
        result = asyncio.run(execute(FunctionModel(model), session))
        self.assertEqual(result["status"], "error")
        self.assertEqual(session.state, before)
        self.assertEqual(session.calls, 0)

    def test_observations_do_not_open_drawers(self):
        session = RoomSession()
        session.perform(action("look", "room", "general"))
        session.perform(action("look", "desk", "general"))
        session.perform(action("look", "drawer", "inside"))
        self.assertFalse(session.state.drawer_open)

    def test_independent_sessions(self):
        first, second = RoomSession(), RoomSession()
        first.perform(action("look", "room", "general"))
        self.assertNotIn("desk", second.state.known)
        self.assertEqual(second.calls, 0)

    def test_tool_limit_and_time_limit(self):
        session = RoomSession(tool_limit=1)
        session.observe()
        with self.assertRaises(BudgetReached): session.observe()
        expired = RoomSession(deadline=time.monotonic()-1)
        with self.assertRaises(BudgetReached): expired.observe()
        self.assertEqual(expired.calls, 0)

    def test_demo_uses_real_tools_and_stops_after_goal(self):
        session = RoomSession()
        records = asyncio.run(run(demo=True, session=session))
        self.assertEqual(records[-1]["status"], "goal_reached")
        self.assertEqual(session.calls, 6)
        self.assertIn("brass_key", view(session.state)["visible_items"])
        self.assertEqual(session.state.inventory, set())
        with self.assertRaises(GoalReached): session.perform(action("open", "door"))
        self.assertFalse(session.state.escaped)

    def test_parallel_proposals_are_executed_sequentially(self):
        def model(messages, info):
            return ModelResponse(parts=[
                ToolCallPart("perform_action", {"action": action("look", "room", "general")}),
                ToolCallPart("perform_action", {"action": action("look", "desk", "general")})])
        session = RoomSession()
        result = asyncio.run(execute(FunctionModel(model), session, request_limit=1))
        self.assertIn("drawer", session.state.known)
        self.assertEqual(session.trace[1]["validation"], "accepted")
        self.assertEqual(result["status"], "limit_reached")

    def test_request_limit_retains_partial_progress(self):
        session = RoomSession()
        result = asyncio.run(execute(demo_model(), session, request_limit=3))
        self.assertEqual(result["status"], "limit_reached")
        self.assertIn("drawer", session.state.known)
        self.assertFalse(session.goal_reached)

    def test_false_success_claim_is_not_success(self):
        model = FunctionModel(lambda messages, info: ModelResponse(parts=[TextPart("I found the key!")]))
        result = asyncio.run(execute(model, RoomSession()))
        self.assertEqual(result["status"], "incomplete")
        self.assertFalse(result["goal_reached"])

    def test_provider_failure_retains_completed_actions(self):
        turns = [0]
        def model(messages, info):
            turns[0] += 1
            if turns[0] > 1: raise RuntimeError("provider failed")
            return ModelResponse(parts=[ToolCallPart("perform_action", {"action": action("look", "room", "general")})])
        session = RoomSession()
        result = asyncio.run(execute(FunctionModel(model), session))
        self.assertEqual(result["status"], "error")
        self.assertIn("desk", session.state.known)

    def test_timeout_stops_run(self):
        async def slow(messages, info):
            await asyncio.sleep(0.2)
            return ModelResponse(parts=[TextPart("done")])
        result = asyncio.run(execute(FunctionModel(slow), RoomSession(), timeout=0.01))
        self.assertEqual(result["status"], "timeout")


if __name__ == "__main__":
    unittest.main()
