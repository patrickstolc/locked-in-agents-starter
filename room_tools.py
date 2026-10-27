"""Trusted boundary between tool calls and the unchanged room engine."""
import copy
import time
from dataclasses import dataclass, field
from world import State, view, get_schema, validate_action, apply_action


class GoalReached(Exception):
    """The Python controller has verified the task and stops the run."""


class BudgetReached(Exception):
    """A local limit stopped a tool before any further action."""


@dataclass
class RoomSession:
    state: State = field(default_factory=State)
    trace: list = field(default_factory=list)
    calls: int = 0
    tool_limit: int = 8
    deadline: float = field(default_factory=lambda: time.monotonic() + 120)

    @property
    def goal_reached(self):
        return ("brass_key" in view(self.state)["visible_items"]
                and "brass_key" not in self.state.inventory)

    def public_result(self, feedback, *, accepted=True):
        return {"accepted": accepted, "feedback": feedback, "observation": view(self.state),
                "schema": get_schema(self.state), "goal_reached": self.goal_reached,
                "tool_calls_remaining": max(0, self.tool_limit - self.calls)}

    def begin_call(self, name, arguments):
        if self.goal_reached:
            raise GoalReached("The key is visible and has not been taken.")
        if time.monotonic() >= self.deadline:
            raise BudgetReached("Time limit reached.")
        if self.calls >= self.tool_limit:
            raise BudgetReached("Tool execution limit reached.")
        self.calls += 1
        record = {"event": "tool", "number": self.calls, "tool": name,
                  "arguments": copy.deepcopy(arguments)}
        self.trace.append(record)
        return record

    def observe(self):
        record = self.begin_call("observe_room", {})
        result = self.public_result("This is what you currently know.")
        record.update(validation="accepted", result=copy.deepcopy(result))
        return result

    def perform(self, action):
        record = self.begin_call("perform_action", {"action": action})
        try:
            action = validate_action(action, get_schema(self.state))
            if action["action"] not in {"look", "open"}:
                raise ValueError("This agent may inspect and open only. It cannot take or use items.")
        except (ValueError, TypeError, KeyError) as error:
            result = self.public_result(str(error), accepted=False)
            record.update(validation="rejected", result=copy.deepcopy(result))
            return result
        feedback = apply_action(self.state, action)
        result = self.public_result(feedback)
        record.update(validation="accepted", result=copy.deepcopy(result))
        return result
