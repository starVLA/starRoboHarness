"""Build a receipt-verified index of reusable terminal campaign results."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from starharness.evaluation import panel_digest


def build_resume_index(sources: list[Path], output: Path) -> list[dict]:
    if output.exists():
        raise FileExistsError(output)
    if not sources:
        raise ValueError("at least one source campaign is required")
    panel = json.loads((sources[0] / "panel.json").read_text())
    digest = panel_digest(panel)
    accepted: dict[tuple[str, str], dict] = {}
    excluded_rows = 0
    excluded_nonterminal_rows = []
    orphaned_controller_attempts = []
    for source in sources:
        candidate_panel = json.loads((source / "panel.json").read_text())
        if panel_digest(candidate_panel) != digest:
            raise ValueError(f"panel mismatch: {source}")
        rows = json.loads((source / "outcomes.json").read_text())
        indexed = {(row["method"], row["case_id"]) for row in rows}
        for row in rows:
            origin = Path(row.get("source_run", source)).resolve()
            receipt = origin / row["method"] / row["case_id"] / "native-outcome.json"
            native = json.loads(receipt.read_text()) if receipt.is_file() else None
            if not row.get("complete") or not row.get("valid_for_success_rate"):
                if not (
                    native
                    and native.get("complete")
                    and native.get("valid_for_success_rate")
                ):
                    excluded_rows += 1
                    excluded_nonterminal_rows.append(
                        {
                            "source": str(source.resolve()),
                            "method": row["method"],
                            "case_id": row["case_id"],
                            "termination": row.get("termination"),
                            "error_type": row.get("error_type"),
                        }
                    )
                    continue
                steps = native.get("native_control_steps")
                limit = native.get("native_step_limit")
                row = dict(
                    row,
                    complete=True,
                    valid_for_success_rate=True,
                    success=native.get("native_success"),
                    score=native.get("native_score"),
                    termination=(
                        "native_success"
                        if native.get("native_success")
                        else "native_timeout"
                        if steps is not None and steps == limit
                        else "native_failure"
                    ),
                    recovered_from_native_receipt=True,
                )
                row.pop("error_type", None)
            actual = hashlib.sha256(json.dumps(native, sort_keys=True).encode()).hexdigest()
            if row.get("native_sha256") not in (None, actual):
                raise ValueError(f"native receipt digest mismatch: {receipt}")
            accepted[(row["method"], row["case_id"])] = dict(
                row, native_sha256=actual, source_run=str(origin)
            )
        for method in panel["methods"]:
            method_root = source / method
            if not method_root.is_dir():
                continue
            for controller in method_root.glob("*/controller"):
                key = (method, controller.parent.name)
                if key not in indexed and any(
                    (controller / name).exists()
                    for name in ("run.json", "progress.json", "history.json")
                ):
                    orphaned_controller_attempts.append(
                        {"source": str(source.resolve()), "method": method,
                         "case_id": controller.parent.name}
                    )
    output.mkdir(parents=True)
    rows = list(accepted.values())
    (output / "panel.json").write_text(json.dumps(panel, indent=2) + "\n")
    (output / "outcomes.json").write_text(json.dumps(rows, indent=2) + "\n")
    lineage = {
        "schema": "starharness.resume_index.v1",
        "panel_sha256": digest,
        "sources": [str(path.resolve()) for path in sources],
        "accepted": len(rows),
        "excluded_nonterminal_attempts": excluded_rows + len(orphaned_controller_attempts),
        "excluded_nonterminal_rows": excluded_nonterminal_rows,
        "orphaned_controller_attempts": orphaned_controller_attempts,
    }
    (output / "lineage.json").write_text(json.dumps(lineage, indent=2) + "\n")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = build_resume_index(args.source, args.output)
    print(json.dumps({"output": str(args.output.resolve()), "accepted": len(rows)}))


if __name__ == "__main__":
    main()
