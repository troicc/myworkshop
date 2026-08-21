from __future__ import annotations

import json
import re
from typing import Any

import httpx


class ProviderError(RuntimeError):
    pass


def _endpoint(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def extract_json(value: Any) -> dict[str, Any]:
    """Extract one JSON object from common OpenAI-compatible response shapes."""

    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        fragments: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    fragments.append(text)
            elif isinstance(item, str):
                fragments.append(item)
        value = "".join(fragments)
    if not isinstance(value, str):
        raise ProviderError(f"model returned unsupported content type: {type(value)!r}")

    text = value.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ProviderError("model did not return a JSON object") from None
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ProviderError(f"invalid JSON from model: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ProviderError("model JSON root must be an object")
    return parsed


class OpenAICompatibleTextProvider:
    """Small HTTP adapter for OpenAI-compatible Chat Completions APIs.

    It first attempts strict JSON Schema mode. Providers that reject the field
    are retried with a plain schema prompt; the result is always validated by
    Pydantic in the planner.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float,
        temperature: float,
        max_tokens: int,
        use_json_schema: bool,
    ) -> None:
        if not api_key:
            raise ValueError("LLM API key is empty")
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.use_json_schema = use_json_schema

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        schema_name: str,
    ) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        if self.use_json_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            }
        try:
            response = self._post(payload)
        except ProviderError:
            if not self.use_json_schema:
                raise
            fallback = dict(payload)
            fallback.pop("response_format", None)
            fallback["messages"] = [
                messages[0],
                {
                    "role": "user",
                    "content": (
                        f"{user_prompt}\n\n只返回一个 JSON 对象，不要 Markdown。"
                        f"必须符合以下 JSON Schema：\n{json.dumps(schema, ensure_ascii=False)}"
                    ),
                },
            ]
            response = self._post(fallback)
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"unexpected Chat Completions response: {response!r}") from exc
        return extract_json(content)

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = _endpoint(self.base_url, "chat/completions")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise ProviderError(f"LLM request failed: {exc}") from exc
        if response.status_code >= 400:
            body = response.text[:1200]
            raise ProviderError(f"LLM HTTP {response.status_code}: {body}")
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError("LLM returned non-JSON HTTP response") from exc
        if not isinstance(data, dict):
            raise ProviderError("LLM response root must be an object")
        return data
