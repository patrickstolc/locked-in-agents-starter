# Locked In: Agents starter

This project builds on the Locked In escape room from the previous class. The room and the earlier HTTP interpreter are included. Your work is in `action_model.py`, `interpreter_framework.py` and `agent_tools.py`.

Follow the lab on Moodle or open [lab.md](lab.md). The required exercises use scripted model replies and run locally after setup. You do not need an API key.

## Setup

Use Python 3.11 or newer.

macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Start with the room and the existing tests:

```bash
python manual_room.py --demo
python -m unittest -v test_previous
```

After completing the three files:

```bash
python -m unittest -v
python agent_runner.py --demo --log my_trace.jsonl
```

`--demo` uses fixed model replies. It exercises the framework and the room tools without a network connection. It does not measure an LLM's language understanding.

## Files

- `world.py`: the room, discoveries, inventory and rules.
- `interpreter_http.py`: the previous HTTP interpreter.
- `action_model.py`: define the four fields of an action.
- `interpreter_framework.py`: implement one typed framework turn.
- `agent_tools.py`: register the observation and action tools.
- `room_tools.py`: validate tool actions and return the public room view.
- `agent_runner.py`: run the bounded agent and its scripted demo.
- `test_previous.py` and `test_framework.py`: offline checks.
- `example_trace.md`: a walkthrough of the scripted run.

The agent's task is to find the key without taking it. The controller stops after the room confirms the goal. It also limits the number of model turns and tool calls, and sets a timeout.

## Documentation

- [Agents](https://pydantic.dev/docs/ai/core-concepts/agent/)
- [Structured output](https://pydantic.dev/docs/ai/core-concepts/output/)
- [Function tools](https://pydantic.dev/docs/ai/tools-toolsets/tools/)
- [Testing](https://pydantic.dev/docs/ai/guides/testing/)
- [Usage limits](https://pydantic.dev/docs/ai/core-concepts/agent/#usage-limits)
