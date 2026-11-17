"""Text-only tool agent using the existing provider configuration and error policy."""
from __future__ import annotations

import copy
from email.utils import parsedate_to_datetime
import json
import math
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request

from screenplay.agents import (APIError, CapacityError, Decision, OpenAICompatibleAgent,
                             capacity_reason, estimated_cost, normalize_usage)
from screenplay.runner import append_json, write_json
from .fifteen import build_request, tools


def parse_action(raw: dict, condition: str, game: str = "Fifteen") -> tuple[dict, str | None]:
    try:
        choices = raw.get("choices")
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError("expected_one_choice")
        choice = choices[0]
        if choice.get("finish_reason") == "length":
            raise ValueError("output_token_limit")
        calls = choice["message"].get("tool_calls", [])
        if len(calls) != 1:
            raise ValueError("expected_one_tool_call")
        function = calls[0]["function"]
        if function["name"] not in {s["function"]["name"] for s in tools(condition, game)}:
            raise ValueError("unsupported_tool")
        arguments = function["arguments"]
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        if not isinstance(arguments, dict) or "type" in arguments:
            raise ValueError("invalid_tool_arguments")
        return {"type": function["name"], **arguments}, None
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        return {"type": "invalid_model_output"}, str(error)[:160]


class TextAgent(OpenAICompatibleAgent):
    def build_request(self, observation: dict):
        body = build_request(list(self.history), observation, window=self.config.image_window)
        body.update(model=self.public_config["model"], **{
            self.config.token_limit_field: self.config.max_output_tokens})
        if self.config.temperature is not None:
            body["temperature"] = self.config.temperature
        body.update(copy.deepcopy(self.config.extra_body))
        payload = json.dumps(body).encode()
        self.request_metrics = {"image_count": 0, "image_refs": [],
                                "board_observations": min(len(self.history) + 1, self.config.image_window),
                                "text_history_turns": len(self.history),
                                "observation_window": self.config.image_window,
                                "request_bytes": len(payload)}
        if self.config.max_request_bytes is not None and len(payload) > self.config.max_request_bytes:
            raise CapacityError("request_body_too_large")
        return body, payload

    def choose(self, observation: dict, directory: Path) -> Decision:
        self.calls += 1
        self.request_metrics = {}
        start = time.monotonic()
        prefix = f"{self.calls:06d}"
        model_dir = directory / "model"
        model_dir.mkdir(exist_ok=True)
        marker = directory / "private/model_call_active.json"
        activity = {"active": True, "call_index": self.calls,
                    "observation_id": observation["observation_id"],
                    "started_monotonic": start, "deadline_monotonic": start + self.config.timeout_seconds,
                    "request_sent": False}
        record = {"call_index": self.calls, "observation_id": observation["observation_id"],
                  "requested_model": self.public_config["model"], "request_sent": False,
                  "request_file": f"model/{prefix}.request.json"}
        write_json(marker, activity)
        try:
            body, payload = self.build_request(observation)
            write_json(model_dir / f"{prefix}.request.json", self._redact(body))
            base = self.public_config["base_url"].rstrip("/")
            endpoint = base if base.endswith("/chat/completions") else base + "/" + self.config.chat_completions_path
            request = Request(endpoint, data=payload, method="POST", headers={
                "Content-Type": "application/json", "User-Agent": "ScreenPlay/0.1",
                "Authorization": "Bearer " + self.key})
            record["request_sent"] = True
            write_json(marker, {**activity, "request_sent": True, "request_bytes": len(payload)})
            with self.opener.open(request, timeout=self.config.timeout_seconds) as response:
                data = response.read(10_000_001)
                if len(data) > 10_000_000:
                    raise CapacityError("response_body_too_large")
                raw = json.loads(data)
                if not isinstance(raw, dict):
                    raise APIError("Provider response is not an object")
                if raw.get("error"):
                    reason = capacity_reason(None, json.dumps(raw["error"]))
                    if reason:
                        raise CapacityError(reason)
                    raise APIError("Provider returned an error object")
                record["request_id"] = response.headers.get("x-request-id") or raw.get("request_id")
            write_json(model_dir / f"{prefix}.response.json", self._redact(raw))
            action, parse_error = parse_action(raw, observation["condition"], observation.get("game", "Fifteen"))
            usage = normalize_usage(raw)
            choice = raw.get("choices", [{}])[0] if isinstance(raw.get("choices"), list) and raw["choices"] else {}
            choice = choice if isinstance(choice, dict) else {}
            message = choice.get("message") or {}
            message = message if isinstance(message, dict) else {}
            assistant = {k: copy.deepcopy(message[k]) for k in ["role", "content", "tool_calls"] if k in message}
            assistant["role"] = "assistant"
            if self.config.preserve_reasoning and isinstance(message.get("reasoning_content"), str):
                assistant["reasoning_content"] = message["reasoning_content"]
            record.update(status="completed", returned_model=raw.get("model"), usage=usage,
                          estimated_cost_usd=estimated_cost(usage, self.config), parse_error=parse_error,
                          finish_reason=choice.get("finish_reason"), response_file=f"model/{prefix}.response.json")
        except CapacityError as error:
            record.update(status="capacity_error", failure_reason=error.reason, usage=None)
            raise
        except MemoryError as error:
            record.update(status="capacity_error", failure_reason="memory_limit_exceeded", usage=None)
            raise CapacityError("memory_limit_exceeded") from error
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, APIError) as error:
            status = getattr(error, "code", None)
            record.update(status="api_error", error_type=type(error).__name__, http_status=status, usage=None)
            retry_after = None
            detail = ""
            if isinstance(error, HTTPError):
                try:
                    detail = error.read(4096).decode(errors="replace")
                except OSError:
                    pass
                record["provider_error"] = self._redact(detail)
                header = error.headers.get("Retry-After") if error.headers else None
                if header:
                    try:
                        retry_after = float(header)
                    except ValueError:
                        try:
                            retry_after = parsedate_to_datetime(header).timestamp() - time.time()
                        except (ValueError, TypeError, OverflowError):
                            pass
                if retry_after is not None:
                    retry_after = max(0, retry_after) if math.isfinite(retry_after) else None
            reason = capacity_reason(status, detail + " " + str(error))
            if isinstance(error, TimeoutError) or (isinstance(error, URLError) and isinstance(error.reason, TimeoutError)):
                reason = "request_timeout"
            if reason:
                record.update(status="capacity_error", failure_reason=reason)
                raise CapacityError(reason) from error
            raise APIError(f"Model request failed ({type(error).__name__}, HTTP {status})",
                           http_status=status, retry_after_seconds=retry_after) from error
        finally:
            record.update(self.request_metrics, latency_ms=round((time.monotonic() - start) * 1000, 3))
            append_json(directory / "model_calls.jsonl", self._redact(record))
            write_json(marker, {"active": False, "call_index": self.calls})
        return Decision(action, None, record, assistant)

    def remember(self, before: dict, decision: Decision, after: dict):
        self.history.append({"observation": copy.deepcopy(before),
                             "assistant": copy.deepcopy(decision.assistant_message),
                             "receipt": copy.deepcopy(after["receipt"])})
