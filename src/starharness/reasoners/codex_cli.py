"""Bounded, image-aware Codex CLI calls with explicit model and effort."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class ReasonerError(RuntimeError):
    """No executable decision was produced; never replay a simulator action."""


class CodexCLIReasoner:
    """One fresh inference session per request, with caller-managed short memory.

    The provider has no simulator connection. The caller validates the returned
    decision before executing it. A CLI model/effort setting is recorded as a
    request, not as proof of the upstream model or reasoning implementation.
    """

    disabled_features = (
        "shell_tool",
        "multi_agent",
        "sleep_tool",
        "goals",
        "apps",
        "plugins",
        "browser_use",
        "computer_use",
        "image_generation",
        "skill_search",
        "tool_suggest",
        "workspace_dependencies",
        "hooks",
        "memories",
    )

    def __init__(
        self,
        output_dir: str | Path,
        *,
        executable: str = "codex",
        model: str = "gpt-6-astra",
        effort: str = "xhigh",
        base_url: str | None = None,
        api_key_file: str | Path | None = None,
        timeout_seconds: float = 300,
        max_prompt_chars: int = 48000,
    ):
        if timeout_seconds <= 0 or max_prompt_chars <= 0:
            raise ValueError("timeout and prompt limit must be positive")
        if api_key_file is not None and base_url is None:
            raise ValueError("an explicit endpoint is required with an API key file")
        if base_url is not None:
            parsed = urlparse(base_url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError("base_url must be an HTTP(S) endpoint")
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError("credentials and query parameters cannot be in base_url")
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.workspace = self.output_dir / "workspace"
        self.workspace.mkdir(mode=0o700, exist_ok=True)
        self.executable, self.model, self.effort = executable, model, effort
        self.base_url = base_url
        self.api_key_file = Path(api_key_file) if api_key_file is not None else None
        self.timeout_seconds, self.max_prompt_chars = timeout_seconds, max_prompt_chars

    def infer(
        self, prompt: str, *, schema: dict[str, Any], images: list[str | Path] | None = None
    ) -> dict[str, Any]:
        """Return JSON and record latency, usage, requested identity, and CLI events.

        No model fallback or automatic retry occurs here. Every invocation uses
        a fresh UUID directory so a stale output cannot become a new decision.
        """
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be nonempty")
        if len(prompt) > self.max_prompt_chars:
            raise ValueError("prompt exceeds the bounded-context limit")
        paths = [Path(path).resolve(strict=True) for path in (images or [])]
        if len(paths) > 6 or any(not path.is_file() for path in paths):
            raise ValueError("supply at most six image files")
        call_dir = self.output_dir / uuid.uuid4().hex
        call_dir.mkdir(mode=0o700)
        schema_path, result_path = call_dir / "schema.json", call_dir / "response.json"
        schema_path.write_text(json.dumps(schema), encoding="utf-8")
        (call_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
        command = [
            self.executable,
            "exec",
            "--ignore-user-config",
            "--ephemeral",
            "--json",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--color",
            "never",
            "--model",
            self.model,
            "-c",
            f'model_reasoning_effort="{self.effort}"',
            "-c",
            'approval_policy="never"',
            "-c",
            'web_search="disabled"',
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(result_path),
        ]
        for feature in self.disabled_features:
            command.extend(["--disable", feature])
        if self.base_url is not None:
            command.extend(
                [
                    "-c",
                    'model_provider="starharness"',
                    "-c",
                    'model_providers.starharness.name="starRoboHarness"',
                    "-c",
                    f"model_providers.starharness.base_url={json.dumps(self.base_url)}",
                    "-c",
                    'model_providers.starharness.wire_api="responses"',
                    "-c",
                    'model_providers.starharness.env_key="STARHARNESS_API_KEY"',
                    "-c",
                    "model_providers.starharness.request_max_retries=0",
                    "-c",
                    "model_providers.starharness.stream_max_retries=0",
                ]
            )
        for path in paths:
            command.extend(["--image", str(path)])
        command.append("-")
        environment = os.environ.copy()
        if self.api_key_file is not None:
            key = self.api_key_file.read_text(encoding="utf-8").strip()
            if not key:
                raise ValueError("API key file is empty")
            environment["STARHARNESS_API_KEY"] = key
        metadata: dict[str, Any] = {
            "schema": "starharness.codex_call.v1",
            "requested_model": self.model,
            "requested_effort": self.effort,
            "endpoint": self.base_url or "native_codex_default",
            "upstream_identity_verified": False,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "images": [
                {"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                for path in paths
            ],
            "command": command,
            "status": "running",
            "usage": {},
        }
        meta_path = call_dir / "call.json"
        meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        started = time.monotonic()
        try:
            with (
                (call_dir / "events.jsonl").open("w") as out,
                (call_dir / "stderr.log").open("w") as err,
            ):
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE,
                    text=True,
                    stdout=out,
                    stderr=err,
                    cwd=self.workspace,
                    env=environment,
                    start_new_session=True,
                )
                try:
                    process.communicate(input=prompt, timeout=self.timeout_seconds)
                except BaseException:
                    # Only this invocation's new process group is owned here.
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
                    raise
            metadata["returncode"] = process.returncode
            if process.returncode:
                raise ReasonerError(f"Codex exited {process.returncode}; evidence: {call_dir}")
            completed = False
            for line in (call_dir / "events.jsonl").read_text(encoding="utf-8").splitlines():
                event = json.loads(line)
                if event.get("type") == "turn.completed":
                    completed = True
                    metadata["usage"] = event.get("usage", {})
                if event.get("type") in {"turn.failed", "error"}:
                    raise ReasonerError(f"Codex emitted an error; evidence: {call_dir}")
                if event.get("type") in {"item.started", "item.completed"}:
                    kind = event.get("item", {}).get("type")
                    if kind not in {"agent_message", "reasoning"}:
                        raise ReasonerError(
                            f"Unexpected Codex tool item {kind}; evidence: {call_dir}"
                        )
            if not completed:
                raise ReasonerError(f"No completed Codex turn; evidence: {call_dir}")
            response = json.loads(result_path.read_text(encoding="utf-8"))
            if not isinstance(response, dict):
                raise ReasonerError("Codex response must be an object")
            metadata["status"] = "completed"
            return {"response": response, "call_dir": str(call_dir), "metadata": metadata}
        except (OSError, ValueError, subprocess.TimeoutExpired, ReasonerError) as error:
            metadata["status"] = "failed"
            metadata["error_type"] = type(error).__name__
            raise ReasonerError(f"Codex inference failed; inspect {call_dir}") from error
        finally:
            metadata["wall_seconds"] = time.monotonic() - started
            meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
