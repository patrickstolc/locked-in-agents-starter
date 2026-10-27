"""Locked In: a ready-made CLI and game loop. Build the interpreter separately."""
import argparse
import copy
import json

from errors import ModelError
from interpreter import interpret_request
from world import OPENING, State, apply_action, get_schema, validate_action, view

PROMPTS = ("baseline", "revised")


def play_turn(state, history, text, *, prompt="revised", model=None,
              base_url=None, api_key=None, temperature=0.2, timeout=60.0, backend="framework"):
    """Run a turn only after a valid model action. Failures preserve game progress.

    `interpret_request` receives a PUBLIC observation and PUBLIC action schema.
    It is never given a State object or the private contents of the room.
    """
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 500:
        raise ValueError("Enter between 1 and 500 characters.")
    if prompt not in PROMPTS:
        raise ValueError("Unknown prompt version.")
    schema = get_schema(state)
    proposed, metrics = interpret_request(
        text, view(state), schema, copy.deepcopy(history[-4:]), prompt=prompt,
        model=model, base_url=base_url, api_key=api_key,
        temperature=temperature, timeout=timeout, backend=backend,
    )
    if not isinstance(metrics, dict):
        raise ModelError("The interpreter did not return measurements.")
    try:
        action = validate_action(proposed, schema)
    except (TypeError, ValueError, KeyError) as error:
        raise ModelError("The model proposed an invalid or undiscovered action: " + str(error),
                         {**metrics, "action": None, "first_response_contract_valid": False}) from error

    # `apply_action` is the sole authority for revealing items or changing objects.
    feedback = apply_action(state, action)
    history.append({"player": text, "action": action, "feedback": feedback})
    del history[:-4]
    metrics = {**metrics, "action": action, "first_response_contract_valid": True,
               "feedback": feedback, "state": view(state)}
    return feedback, metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("http", "framework"), default="framework")
    parser.add_argument("--prompt", choices=PROMPTS, default="revised")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--log", default="turns.jsonl", help="Use an empty string to disable logs")
    parser.add_argument("--show-actions", action="store_true", help="Print the validated JSON actions")
    args = parser.parse_args()
    state, history = State(), []
    print(OPENING)
    print("Commands: /state, /reset, /quit.")
    while True:
        try:
            text = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text == "/quit":
            break
        if text == "/reset":
            state, history = State(), []
            print(OPENING)
            continue
        if text == "/state":
            print(json.dumps(view(state), indent=2))
            continue
        try:
            feedback, metrics = play_turn(state, history, text,
                                          prompt=args.prompt, temperature=args.temperature, backend=args.backend,
                                          timeout=args.timeout)
            if args.show_actions:
                print("Action:", json.dumps(metrics["action"]))
            print(feedback)
            record = {"player": text, "prompt": args.prompt, **metrics}
        except ModelError as error:
            print(f"{error} Nothing changed. Check your API settings or try again.")
            record = {"player": text, "prompt": args.prompt,
                      "error": str(error), **error.metrics}
        except (ValueError, NotImplementedError) as error:
            print(error)
            continue
        if args.log:
            try:
                with open(args.log, "a", encoding="utf-8") as log:
                    log.write(json.dumps(record) + "\n")
            except OSError:
                print("Could not write the turn log.")


if __name__ == "__main__":
    main()
