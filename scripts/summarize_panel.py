"""Summarize native outcome receipts for one frozen three-method panel."""

import argparse
import json
from pathlib import Path

from starroboharness.evaluation import summarize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument(
        "--outcomes", type=Path, required=True, help="JSON list of outcome receipts"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = summarize(json.loads(args.panel.read_text()), json.loads(args.outcomes.read_text()))
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2)
        output.write("\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
