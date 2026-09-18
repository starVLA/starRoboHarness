"""Preflight GPT-6 Astra xhigh without allocating a simulator episode."""

import argparse
import json

from starroboharness.reasoners import CodexCLIReasoner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key-file")
    parser.add_argument("--image")
    args = parser.parse_args()
    reasoner = CodexCLIReasoner(
        args.output,
        executable=args.codex,
        base_url=args.base_url,
        api_key_file=args.api_key_file,
        timeout_seconds=180,
    )
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"status": {"type": "string"}, "description": {"type": "string"}},
        "required": ["status", "description"],
    }
    result = reasoner.infer(
        'Return status="ASTRA_OK". Describe the attached image if present; otherwise say '
        '"text-only probe". Do not call tools. This is a connectivity probe, not an evaluation.',
        schema=schema,
        images=[args.image] if args.image else [],
    )
    if result["response"].get("status") != "ASTRA_OK":
        raise SystemExit("Probe did not return the expected marker")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
