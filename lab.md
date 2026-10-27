# Locked In: From API calls to agents

Last time, you wrote an interpreter that turned a player's sentence into an action. This time, you will use PydanticAI to handle the model interaction, then give an agent two tools for exploring the same room.

Work through the steps yourself or with a partner. Once you have cloned the repository and installed the dependencies, the required exercises run locally. You do not need an API key or a hosted model.

You will write code in three places: the four fields of `Action`, the `run_typed` function and two tool functions. The room, prompts, provider setup, agent loop and tests are already in the starter. You will also trace an example through both interpreters and inspect the agent trace.

---

## 1. Set up and explore

Clone the starter repository linked from Moodle. Open its folder and create a virtual environment with Python 3.11 or newer:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manual_room.py --demo
python -m unittest -v test_previous
```

On Windows PowerShell, use `py -3.11 -m venv .venv` and `.\.venv\Scripts\Activate.ps1` to create and activate the environment.

Open `world.py`. Find `view`, `get_schema` and `apply_action`.

- What does the player know at the start?
- Which function decides whether an action changes the room?
- Why is finding an object different from picking it up?

---

## 2. Describe an action

Open `action_model.py` and complete the `Action` type. It needs four required string fields: `action`, `item`, `target` and `focus`. Use `Literal` to restrict action names and focus values. Reject extra fields.

For example:

```python
{"action": "look", "item": "", "target": "drawer", "focus": "inside"}
```

The current room schema determines which object IDs are known. Do not hard-code the hidden objects into your type.

Run the type check:

```bash
python -m unittest -v test_framework.TestTypedInterpreter.test_typed_action_rejects_extra_fields_and_coercion
```

A well-formed action can still be impossible. For example, `take` with `brass_key` has the right fields but must be rejected before the key is discovered.

---

## 3. Use the framework for one turn

Open `interpreter_framework.py` and complete `run_typed`.

1. Create an `Agent` with `PromptedOutput(Action, template=False)`. Use `NativeOutput(Action)` for the supplied `schema` mode.
2. Disable output repair with `retries=0`.
3. Pass `framework_messages(messages)` to the run. The supplied messages contain the public room view and up to four completed turns.
4. Limit the run to one model request with `UsageLimits(request_limit=1)`. Pass the supplied temperature and timeout, and set `max_tokens` to 160.
5. Convert the result with `model_dump()`, validate it against the current schema, and return the action and framework result.

Run the interpreter tests:

```bash
python -m unittest -v test_framework.TestTypedInterpreter
```

These tests use scripted replies and a mocked transport. They do not send requests to a model provider.

Look at the tests for an undiscovered object, malformed output and retry behaviour. Which checks come from PydanticAI, and which are still handled by the room code?

---

## 4. Register the room tools

Open `agent_tools.py`, `room_tools.py` and `agent_runner.py`.

1. Register `observe_room(ctx)` and return `ctx.deps.observe()`.
2. Register `perform_action(ctx, action: Action)` and pass `action.model_dump()` to `ctx.deps.perform(...)`.
3. Make both tools sequential and set their validation retries to zero.
4. After an action, check `ctx.deps.goal_reached`. If it is true, raise `GoalReached`. The session has already recorded the final result.
5. Otherwise, return the tool result.

`RunContext[RoomSession]` is supplied by your program. The model supplies the action. The room state stays in Python.

Run the tool tests and scripted demo:

```bash
python -m unittest -v test_framework.TestAgentBoundary
python agent_runner.py --demo --log my_trace.jsonl
```

The demo uses scripted model replies with real framework tools. It does not test how well an LLM understands the task.

The task is: **Find the brass key, leave it where it is, and stop.** Read `my_trace.jsonl` and follow the calls:

- Which action reveals the drawer?
- What does the engine return when the base is inspected?
- How does Python decide that the task is complete?
- What happens if a tool tries to take an item or use an undiscovered ID?

---

## 5. Compare the two approaches

The original HTTP interpreter is in `interpreter_http.py`; your framework adapter is in `interpreter_framework.py`. Read the two implementations and their tests.

Pick one case from `cases.py`, such as asking what is inside the drawer. Trace how the player's words, public room view and recent history reach each interpreter. Then trace what happens to the result before the room changes.

Run all offline tests when you are ready:

```bash
python -m unittest -v
```

A model connection is optional. If you already have a local OpenAI-compatible model with tool support, you can use it to try the game and agent without a hosted service. The `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY` settings are described in `config.py`. Results from a live model can differ from the scripted test.

---

## 6. Finish the Moodle activities

Take the quiz, join the discussion and answer the exit poll. You do not need to upload your code or write a report.
