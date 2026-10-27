# Locked In: From API calls to agents

Last time, you connected the escape room to an LLM through an HTTP request. This time, you will use PydanticAI to handle the model interaction, then give an agent two tools for exploring the same room.

Work on your own or with a partner. You need a hosted model with an OpenAI-compatible Chat Completions API, an API key and a model that supports tool calling. You can use the same provider as last week if its model supports these features. Check its model list and free-tier limits before you start.

You will write code in three places: the four fields of `Action`, the `run_typed` function and two tool functions. The room, prompts, provider setup, agent loop and tests are already in the starter. You will then play the game, run the agent with a real model and inspect what it does.

---

## 1. Set up and connect to a model

Clone the starter repository linked from Moodle. Open its folder and create a virtual environment with Python 3.11 or newer:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manual_room.py --demo
python -m unittest -v test_previous
```

On Windows PowerShell, use `py -3.11 -m venv .venv` and `.\.venv\Scripts\Activate.ps1` to create and activate the environment.

Set your provider's base URL, model and API key in the same terminal. For example, for a Groq endpoint on macOS or Linux:

```bash
export LLM_BASE_URL="https://api.groq.com/openai/v1"
export LLM_MODEL="your-tool-capable-model"
export LLM_API_KEY="your-api-key"
export LLM_RESPONSE_MODE="json"
python api_probe.py
```

On Windows PowerShell:

```powershell
$env:LLM_BASE_URL="https://api.groq.com/openai/v1"
$env:LLM_MODEL="your-tool-capable-model"
$env:LLM_API_KEY="your-api-key"
$env:LLM_RESPONSE_MODE="json"
python api_probe.py
```

Replace the placeholders with your provider's current values. The probe should print a model response. It tests a basic chat request; it does not establish that the model supports tool calling. Keep your key out of your code, Git commits, screenshots and forum posts.

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

Run the interpreter tests, then play with your hosted model:

```bash
python -m unittest -v test_framework.TestTypedInterpreter
python locked_in.py --backend framework --show-actions
```

Try a short conversation:

```text
> What's in the room?
> Look at the desk.
> What's inside the drawer?
> Open it.
```

Look at the action printed for each input. Does asking about the drawer open it? Does the model resolve `it`? The Python room decides what actually happens.

The tests use scripted replies and a mocked transport to help you debug. The game command sends requests to your hosted model. If your provider does not support JSON mode, set `LLM_RESPONSE_MODE` to `plain` and try again.

---

## 4. Give the agent room tools

Open `agent_tools.py`, `room_tools.py` and `agent_runner.py`.

1. Register `observe_room(ctx)` and return `ctx.deps.observe()`.
2. Register `perform_action(ctx, action: Action)` and pass `action.model_dump()` to `ctx.deps.perform(...)`.
3. Make both tools sequential and set their validation retries to zero.
4. After an action, check `ctx.deps.goal_reached`. If it is true, raise `GoalReached`. The session has already recorded the final result.
5. Otherwise, return the tool result.

`RunContext[RoomSession]` is supplied by your program. The model supplies the action. The room state stays in Python.

Run the tool tests, then ask your hosted model to work on the room:

```bash
python -m unittest -v test_framework.TestAgentBoundary
python agent_runner.py --log agent_trace.jsonl
```

The task is: **Find the brass key, leave it where it is, and stop.** Open `agent_trace.jsonl` and follow the model's tool calls and the room's replies.

- Which actions did the model choose? Did they lead it towards the key?
- Did a tool reject an action? What did the model do next?
- Did the room actually reveal the key, and is the inventory still empty?
- Why did the run stop? If it reached a limit or failed, what would you change before trying again?

Use a new log filename for each run. The agent has limits on model requests, tool calls and run time. The engine checks whether the goal was reached. A model saying it found the key is not enough.

If you need to check your tools separately, `python agent_runner.py --demo --log demo_trace.jsonl` runs the same tools with scripted replies. It is a debugging aid, not a test of your hosted model.

---

## 5. Compare the two interpreters

The original HTTP interpreter is in `interpreter_http.py`; your framework adapter is in `interpreter_framework.py`. Run the same cases through both using the same model, prompt, temperature and response mode:

```bash
python evaluate.py --backend http --prompt revised --cases C01,C03,C04,C11 --output http_trial.jsonl
python evaluate.py --backend framework --prompt revised --cases C01,C03,C04,C11 --output framework_trial.jsonl
python compare_results.py http_trial.jsonl framework_trial.jsonl
```

Each evaluation includes one warm-up request and four scored requests before any retries. Use `--pause` if your provider requires more space between requests. Choose new output filenames if you run the comparison again.

Look at the actions, correct interpretations and resulting room states. Did the framework change the model's answers? What work did it take over from your HTTP implementation? Find one case where a valid action and a correct interpretation are not the same thing.

Run the full test suite when you are ready:

```bash
python -m unittest -v
```

---

## 6. Finish the Moodle activities

Take the quiz, join the discussion and answer the exit poll. You do not need to upload your code or write a report.
