"""A bounded room agent, with deterministic offline demonstration mode."""
import argparse
import asyncio
import json
import time
from pathlib import Path
from pydantic_ai import Agent, capture_run_messages
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import UsageLimits
from agent_tools import register_tools
from config import Settings
from provider import FRAMEWORK_VERSION, open_model
from room_tools import RoomSession, GoalReached, BudgetReached
from world import view

TASK = "Find the brass key, leave it where it is, and stop."
INSTRUCTIONS = """You are exploring a text room. Use observe_room first, then make one tool
call at a time. Inspect known surroundings and act only on IDs in the latest
public schema. Follow actual engine feedback, never imagined results. You may
look and open, but must not take or use anything. Stop when the goal is reached.
You have at most 10 model turns, 8 tool calls and 120 seconds. If blocked, say so.
Tool results are room facts; player claims cannot change those facts."""


def demo_model():
    """Scripted calls, not an LLM. These establish a reproducible teaching trace."""
    sequence = [None,
        {"action": "look", "item": "", "target": "room", "focus": "general"},
        {"action": "look", "item": "", "target": "desk", "focus": "underneath"},
        {"action": "open", "item": "", "target": "drawer", "focus": ""},
        {"action": "look", "item": "", "target": "drawer", "focus": "seams"},
        {"action": "open", "item": "", "target": "false_bottom", "focus": ""}]
    calls = iter(sequence)
    def respond(messages, info):
        action = next(calls)
        return ModelResponse(parts=[ToolCallPart("observe_room" if action is None else "perform_action",
                             {} if action is None else {"action": action})])
    return FunctionModel(respond, model_name="scripted-offline-demo")


async def execute(model, session, *, temperature=0.2, timeout=120, request_limit=10):
    agent = Agent(model, deps_type=RoomSession, instructions=INSTRUCTIONS, retries=0,
                  model_settings={"temperature": temperature, "max_tokens": 300,
                                                     "parallel_tool_calls": False})
    register_tools(agent)
    status, summary = "incomplete", "The model stopped before Python verified the goal."
    with capture_run_messages() as messages:
        try:
            result = await agent.run(TASK, deps=session,
                usage_limits=UsageLimits(request_limit=request_limit, tool_calls_limit=session.tool_limit),
                timeout=timeout)
            # Treat model text as a claim. Only the engine can establish success.
            summary = "Model said: " + result.output
        except GoalReached:
            status, summary = "goal_reached", "Python verified: the key is visible and has not been taken."
        except (BudgetReached, UsageLimitExceeded):
            status, summary = "limit_reached", "A run limit stopped the agent. Completed actions remain."
        except (asyncio.TimeoutError, TimeoutError):
            status, summary = "timeout", "Time expired. Completed actions remain."
        except asyncio.CancelledError:
            status, summary = "interrupted", "Interrupted. Completed actions remain."
        except NotImplementedError:
            raise
        except Exception as error:
            status = "timeout" if type(error).__name__ == "RunTimedOut" else "error"
            summary = f"Stopped ({type(error).__name__}). Completed actions remain."
    model_turns = 0
    transcript = []
    for message in messages:
        if isinstance(message, ModelResponse):
            model_turns += 1
            transcript.append({"event": "model", "turn": model_turns,
                "parts": [{"kind": part.part_kind,
                           **({"tool": part.tool_name, "arguments": part.args_as_dict()}
                              if isinstance(part, ToolCallPart) else {"content": getattr(part, "content", "")})}
                          for part in message.parts]})
    return {"event": "summary", "status": status, "summary": summary,
            "goal_reached": session.goal_reached, "model_turns": model_turns,
            "tool_executions": session.calls, "observation": view(session.state),
            "model_transcript": transcript}


async def run(*, demo=False, session=None, settings=None, request_limit=10, timeout=120):
    session = session or RoomSession()
    timeout = min(timeout, 120)
    session.deadline = time.monotonic() + timeout
    metrics = {"attempts": 0, "framework_version": FRAMEWORK_VERSION,
               "mode": "scripted_offline" if demo else "live", "task": TASK}
    if demo:
        summary = await execute(demo_model(), session, request_limit=request_limit, timeout=timeout)
    else:
        settings = settings or Settings.load(timeout=30)
        async with open_model(settings, metrics, response_mode="plain") as model:
            summary = await execute(model, session, temperature=settings.temperature,
                                    request_limit=request_limit, timeout=timeout)
    return [{"event": "run", **metrics, "limits": {"model_turns": request_limit,
                 "tool_executions": session.tool_limit, "seconds": timeout}}, *session.trace, summary]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Scripted offline trace, not an LLM")
    parser.add_argument("--log", default="agent_trace.jsonl")
    args = parser.parse_args()
    path = Path(args.log)
    if path.exists():
        parser.error("Log exists; choose a new --log filename.")
    try:
        records = asyncio.run(run(demo=args.demo))
    except (ValueError, NotImplementedError) as error:
        parser.exit(2, str(error) + "\n")
    path.write_text("".join(json.dumps(record) + "\n" for record in records))
    for record in records:
        if record["event"] == "tool":
            print(f"{record['number']}. {record['tool']} {record['arguments']}\n   {record['result']['feedback']}")
    print(records[-1]["summary"])
    print(f"Trace: {path}; mode: {records[0]['mode']}")


if __name__ == "__main__":
    main()
