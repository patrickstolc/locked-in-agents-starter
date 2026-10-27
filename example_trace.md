# A scripted trace: find the key and leave it

**This is an offline demonstration, not a live LLM result.** `FunctionModel` supplies fixed model replies. PydanticAI executes the registered tools against the real unchanged room engine.

| Call | Tool / action | Why this matters |
|---|---|---|
| 1 | `observe_room()` | Only `room` and `door` are known initially. The schema does not reveal hidden IDs. |
| 2 | `look room / general` | The engine discovers the desk, radio, locker and reader. |
| 3 | `look desk / underneath` | The drawer becomes known; it is still closed. |
| 4 | `open drawer` | The engine opens it and describes its unusual depth. The key is not yet visible. |
| 5 | `look drawer / seams` | The base panel is discovered. Looking alone does not lift it. |
| 6 | `open false_bottom` | The engine reveals the key. Python verifies that it is visible and not in the inventory, records the result and stops the run. |

Every tool event in `example_trace.jsonl` contains the proposed arguments, validation outcome, feedback and updated public observation/schema. The final summary includes the captured model transcript. The run header says `scripted_offline`.

The final inventory is empty. The run used six tool executions. There is no seventh call asking the model to declare success: the Python controller already established it.

Run your own trace with a new filename:

```bash
python agent_runner.py --demo --log my_demo.jsonl
```

After implementing the tools in the starter, this command should produce the same sequence. A live model may choose a different route or reach a limit. Keep that trace and explain it; do not replace it with this example.
