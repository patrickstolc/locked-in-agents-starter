"""Summarize real evaluation logs; never substitutes scripted outcomes for scores."""
import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+")
    args = parser.parse_args()
    groups = defaultdict(list)
    for name in args.logs:
        for line in Path(name).read_text().splitlines():
            row = json.loads(line)
            if "contract_valid" not in row:
                parser.error("Use evaluate.py logs, not an agent/scripted trace.")
            key = (row.get("backend", "unknown"), row["model"], row["prompt"], row["temperature"])
            groups[key].append(row)
    print("Backend | Model | Prompt | Temp | Contract | Intent | State | Median ms | Attempts")
    for key, rows in groups.items():
        scores = [f"{sum(bool(row[field]) for row in rows)}/{len(rows)}" for field in
                  ("contract_valid", "interpretation_correct", "state_correct")]
        print(" | ".join(map(str, [*key, *scores, round(statistics.median(r['elapsed_ms'] for r in rows)),
                                    sum(r.get('attempts',0) for r in rows)])))
    print("Attempts exclude the unscored warm-up. Compare identical case sets and response modes.")


if __name__ == "__main__": main()
