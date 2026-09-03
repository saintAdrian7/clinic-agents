import json
import time

import httpx

from pipeline.config import Config


class LLMError(Exception):
    """Raised on provider failures or unparseable model output."""


class BaseProvider:
    """Shared request/retry/JSON plumbing; subclasses define _request and _extract."""

    def __init__(self, config: Config, client: httpx.Client | None = None):
        self.settings = config.data.get("llm", {})
        self.api_key = config.env(self.settings.get("api_key_env", "ANTHROPIC_API_KEY"))
        self.client = client or httpx.Client(timeout=120)

    def complete(self, messages: list[dict], json_mode: bool = False) -> str | dict:
        """Run one completion; with json_mode, parse the reply as JSON or raise LLMError."""
        response, error = self._attempt(messages)
        if error is not None:
            time.sleep(2)
            response, error = self._attempt(messages)
            if error is not None:
                raise LLMError(f"{self.__class__.__name__}: transport error: {error}") from error
        elif response.status_code in (429,) or response.status_code >= 500:
            time.sleep(2)
            response, error = self._attempt(messages)
            if error is not None:
                raise LLMError(f"{self.__class__.__name__}: transport error: {error}") from error
        if response.status_code != 200:
            raise LLMError(f"{self.__class__.__name__}: HTTP {response.status_code}: {response.text[:200]}")
        try:
            text = self._extract(response.json())
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise LLMError(f"{self.__class__.__name__}: unexpected response shape: {e}") from e
        return _parse_json(text) if json_mode else text

    def _attempt(self, messages: list[dict]) -> tuple[httpx.Response | None, httpx.HTTPError | None]:
        """Call _request once, turning a transport error into a returned exception."""
        try:
            return self._request(messages), None
        except httpx.HTTPError as e:
            return None, e

    def _request(self, messages: list[dict]) -> httpx.Response:
        raise NotImplementedError

    def _extract(self, body: dict) -> str:
        raise NotImplementedError


def _parse_json(text: str) -> dict:
    cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise LLMError(f"model returned invalid JSON: {e}") from e
    if not isinstance(parsed, dict):
        raise LLMError(f"model returned JSON {type(parsed).__name__}, expected an object")
    return parsed


def get_provider(config: Config, client: httpx.Client | None = None) -> BaseProvider:
    """Instantiate the provider named in config llm.provider."""
    from pipeline.llm.anthropic import AnthropicProvider
    from pipeline.llm.openai_compat import OpenAICompatProvider

    providers = {"anthropic": AnthropicProvider, "openai_compat": OpenAICompatProvider}
    name = config.data.get("llm", {}).get("provider", "anthropic")
    if name not in providers:
        raise LLMError(f"unknown provider '{name}'; choose from {sorted(providers)}")
    return providers[name](config, client=client)
