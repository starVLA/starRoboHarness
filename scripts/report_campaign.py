"""Print a human-readable table recomputed from native outcome receipts."""

import argparse
import json
from pathlib import Path

from starharness.evaluation import summarize


def cell(metric):
    if metric["success_rate"] is None:
        return f"pending (0/{metric['planned']} valid)"
    return (
        f"{100 * metric['success_rate']:.1f}% ({metric['successes']}/{metric['valid']}), "
        f"Score {metric['score']:.2f}, coverage {metric['valid']}/{metric['planned']}"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    args = parser.parse_args()
    panel = json.loads((args.campaign / "panel.json").read_text())
    outcomes = args.campaign / "outcomes.json"
    report = summarize(panel, json.loads(outcomes.read_text()) if outcomes.exists() else [])
    labels = {
        "qwenpi_v3": "StarVLA / QwenPI_v3",
        "qwenpi_v3_plus_gpt": "StarVLA + GPT-6 Astra xhigh",
        "gpt_direct": "GPT-6 Astra xhigh direct",
    }
    order = tuple(panel["methods"])
    print("| Task | " + " | ".join(labels[method] for method in order) + " |")
    print("| --- | " + " | ".join("---" for _ in order) + " |")
    for task, methods in report["tasks"].items():
        print("| " + " | ".join([task] + [cell(methods[m]) for m in order]) + " |")
    print("| Overall | " + " | ".join(cell(report["methods"][m]) for m in order) + " |")
    print(f"\nPaired coverage: {len(report['paired_case_ids'])}/{len(panel['cases'])} cases.")
    print("Complete panel: " + str(report["complete"]))
    print("\nEfficiency (valid completed episodes with recorded counters only):")
    for method in order:
        values = report["methods"][method]["efficiency"]
        print(f"- {method}: " + json.dumps(values, sort_keys=True))
    print("\nRecorded costs including invalid attempts in this campaign (not prior run roots):")
    for method in order:
        print(f"- {method}: " + json.dumps(
            report["methods"][method]["all_attempts_efficiency"], sort_keys=True))
    print(
        "\nSource: native terminal outcomes only; missing/aborted cases are not scored as failures."
    )


if __name__ == "__main__":
    main()
