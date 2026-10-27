# Locked In: Agents starter

This project builds on the Locked In escape room from the previous class. The room and the earlier HTTP interpreter are included. Your work is in `action_model.py`, `interpreter_framework.py` and `agent_tools.py`.

Follow the lab on Moodle or open [lab.md](lab.md). You will connect the game and agent to a hosted model using an API key. Choose an OpenAI-compatible Chat Completions provider and a model that supports tool calling.

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

Set `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` and `LLM_RESPONSE_MODE` as shown in the lab. Choose a current model supported by your provider, check its tool-calling support and free-tier limits, and keep your key out of the repository.

Test your API connection:

```bash
python api_probe.py
```

The probe checks basic chat, not tool calling. After completing the three files, use your hosted model to play and run the agent:

```bash
python -m unittest -v
python locked_in.py --backend framework --show-actions
python agent_runner.py --log agent_trace.jsonl
```

The unit tests use scripted replies and a mocked transport. `python agent_runner.py --demo --log demo_trace.jsonl` is also available to check the tools without a model call. The lab's game and agent runs use the hosted model.

## Files

- `world.py`: the room, discoveries, inventory and rules.
- `interpreter_http.py`: the previous HTTP interpreter.
- `action_model.py`: define the four fields of an action.
- `interpreter_framework.py`: implement one typed framework turn.
- `agent_tools.py`: register the observation and action tools.
- `room_tools.py`: validate tool actions and return the public room view.
- `agent_runner.py`: run the bounded agent and its scripted demo.
- `test_previous.py` and `test_framework.py`: checks using mocked model responses.
- `example_trace.md`: a walkthrough of the scripted demo.

The agent's task is to find the key without taking it. The controller stops after the room confirms the goal. It also limits the number of model turns and tool calls, and sets a timeout.

## Documentation

- [Agents](https://pydantic.dev/docs/ai/core-concepts/agent/)
- [Structured output](https://pydantic.dev/docs/ai/core-concepts/output/)
- [Function tools](https://pydantic.dev/docs/ai/tools-toolsets/tools/)
- [Testing](https://pydantic.dev/docs/ai/guides/testing/)
- [Usage limits](https://pydantic.dev/docs/ai/core-concepts/agent/#usage-limits)
