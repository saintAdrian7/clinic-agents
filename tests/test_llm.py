import json

import httpx
import pytest

from pipeline.config import Config
from pipeline.llm import LLMError, get_provider

ANTHROPIC_BODY = {"content": [{"type": "text", "text": '{"score": 0.8}'}]}
OPENAI_BODY = {"choices": [{"message": {"content": "hello"}}]}
OPENAI_JSON_BODY = {"choices": [{"message": {"content": '{"status": "assigned"}'}}]}


def make_config(tmp_path, provider, api_key_env="ANTHROPIC_API_KEY"):
    (tmp_path / "config.yaml").write_text("x: 1", encoding="utf-8")
    config = Config.load(tmp_path)
    config.data = {
        "llm": {
            "provider": provider,
            "model": "m",
            "api_key_env": api_key_env,
            "base_url": "https://api.example.com/v1",
            "max_tokens": 100,
        }
    }
    return config


def client_returning(status, body):
    def handler(request):
        return httpx.Response(status, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_anthropic_extracts_text_and_system_field(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    captured = {}

    def handler(request):
        captured.update(json.loads(request.content))
        assert request.headers["x-api-key"] == "k"
        return httpx.Response(200, json=ANTHROPIC_BODY)

    provider = get_provider(
        make_config(tmp_path, "anthropic"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    messages = [{"role": "system", "content": "be brief"}, {"role": "user", "content": "hi"}]
    assert provider.complete(messages) == '{"score": 0.8}'
    assert captured["system"] == "be brief"
    assert captured["messages"] == [{"role": "user", "content": "hi"}]


def test_json_mode_parses_and_strips_fences(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    body = {"content": [{"type": "text", "text": '```json\n{"a": 1}\n```'}]}
    provider = get_provider(make_config(tmp_path, "anthropic"), client=client_returning(200, body))
    assert provider.complete([{"role": "user", "content": "x"}], json_mode=True) == {"a": 1}


def test_openai_compat_extracts_choice(tmp_path, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    provider = get_provider(
        make_config(tmp_path, "openai_compat", api_key_env="MISTRAL_API_KEY"),
        client=client_returning(200, OPENAI_BODY),
    )
    assert provider.complete([{"role": "user", "content": "hi"}]) == "hello"


def test_openai_compat_json_mode_returns_dict(tmp_path, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    provider = get_provider(
        make_config(tmp_path, "openai_compat", api_key_env="MISTRAL_API_KEY"),
        client=client_returning(200, OPENAI_JSON_BODY),
    )
    result = provider.complete([{"role": "user", "content": "hi"}], json_mode=True)
    assert result == {"status": "assigned"}


def test_server_error_retries_then_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(500, json={})

    provider = get_provider(
        make_config(tmp_path, "anthropic"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(LLMError):
        provider.complete([{"role": "user", "content": "hi"}])
    assert len(calls) == 2


def test_transport_error_once_then_success_returns_text(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, json=ANTHROPIC_BODY)

    provider = get_provider(
        make_config(tmp_path, "anthropic"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert provider.complete([{"role": "user", "content": "hi"}]) == '{"score": 0.8}'
    assert len(calls) == 2


def test_transport_error_twice_raises_llm_error(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ConnectError("boom", request=request)

    provider = get_provider(
        make_config(tmp_path, "anthropic"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(LLMError, match="transport error"):
        provider.complete([{"role": "user", "content": "hi"}])
    assert len(calls) == 2


def test_unknown_provider_raises(tmp_path):
    with pytest.raises(LLMError, match="unknown"):
        get_provider(make_config(tmp_path, "unknown"))


def test_anthropic_payload_includes_temperature_zero_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    captured = {}

    def handler(request):
        captured.update(json.loads(request.content))
        return httpx.Response(200, json=ANTHROPIC_BODY)

    provider = get_provider(
        make_config(tmp_path, "anthropic"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    provider.complete([{"role": "user", "content": "hi"}])
    assert captured["temperature"] == 0


def test_openai_compat_payload_includes_temperature_zero_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    captured = {}

    def handler(request):
        captured.update(json.loads(request.content))
        return httpx.Response(200, json=OPENAI_BODY)

    provider = get_provider(
        make_config(tmp_path, "openai_compat", api_key_env="MISTRAL_API_KEY"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    provider.complete([{"role": "user", "content": "hi"}])
    assert captured["temperature"] == 0


def test_openai_compat_sends_response_format_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    captured = {}

    def handler(request):
        captured.update(json.loads(request.content))
        return httpx.Response(200, json=OPENAI_BODY)

    provider = get_provider(
        make_config(tmp_path, "openai_compat", api_key_env="MISTRAL_API_KEY"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    provider.complete([{"role": "user", "content": "hi"}])
    assert captured["response_format"] == {"type": "json_object"}


def test_json_mode_rejects_non_object_payload(tmp_path, monkeypatch):
    """A JSON array is not a decision; it must surface as LLMError, not flow downstream."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    body = {"content": [{"type": "text", "text": "[1, 2, 3]"}]}
    provider = get_provider(make_config(tmp_path, "anthropic"), client=client_returning(200, body))
    with pytest.raises(LLMError):
        provider.complete([{"role": "user", "content": "x"}], json_mode=True)
