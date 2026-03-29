import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True

from actors.llm_actor import ACTION_TOOL_SCHEMA, LLMDecisionActor
from engine.loop import SimulationEngine
from experiments.runner import run_single
from providers.base import LLMProvider, ProviderCallResult
from providers.openrouter_provider import OpenRouterProvider
from scenarios.taiwan_strait import TaiwanStraitScenario


class _FakeToolFunction:
    def __init__(self, arguments: str):
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, arguments: str):
        self.function = _FakeToolFunction(arguments)


class _FakeMessage:
    def __init__(self, content: str, tool_calls):
        self.content = content
        self.tool_calls = tool_calls


class _FakeChoice:
    def __init__(self, message, finish_reason: str = "tool_calls"):
        self.message = message
        self.finish_reason = finish_reason


class _FakeResponse:
    def __init__(self, message, finish_reason: str = "tool_calls"):
        self.choices = [_FakeChoice(message, finish_reason=finish_reason)]
        self.usage = type(
            "Usage",
            (),
            {"prompt_tokens": 123, "completion_tokens": 45, "total_tokens": 168},
        )()

    def model_dump(self):
        return {"choices": [{"message": {"content": self.choices[0].message.content}}]}


class _FakeChatCompletions:
    def create(self, **kwargs):
        return _FakeResponse(
            _FakeMessage(
                content="Assess pressure, preserve flexibility, then choose monitor.",
                tool_calls=[
                    _FakeToolCall(
                        '{"action_type":"monitor","rationale":"Gather more information before escalating."}'
                    )
                ],
            )
        )


class _FakeChat:
    def __init__(self):
        self.completions = _FakeChatCompletions()


class _FakeOpenAIClient:
    def __init__(self, *args, **kwargs):
        self.chat = _FakeChat()


class _FallbackToolChoiceCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if "tool_choice" in kwargs:
            raise Exception(
                "Error code: 404 - No endpoints found that support the provided 'tool_choice' value"
            )
        return _FakeResponse(
            _FakeMessage(
                content="Keep options open and monitor the situation.",
                tool_calls=[
                    _FakeToolCall(
                        '{"action_type":"monitor","rationale":"Compatibility fallback via auto tools."}'
                    )
                ],
            )
        )


class _FallbackToolChoiceClient:
    def __init__(self, *args, **kwargs):
        self.chat = type("Chat", (), {"completions": _FallbackToolChoiceCompletions()})()


class _JsonFallbackCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) < 3:
            return _FakeResponse(
                _FakeMessage(content=None, tool_calls=None),
                finish_reason="length",
            )
        return _FakeResponse(
            _FakeMessage(
                content='{"action_type":"monitor","intensity":"medium","rationale":"Return compact JSON only."}',
                tool_calls=None,
            ),
            finish_reason="stop",
        )


class _JsonFallbackClient:
    def __init__(self, *args, **kwargs):
        self.chat = type("Chat", (), {"completions": _JsonFallbackCompletions()})()


class _CaptureTemperatureCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(
            _FakeMessage(
                content="Choose monitor and preserve flexibility.",
                tool_calls=[
                    _FakeToolCall(
                        '{"action_type":"monitor","rationale":"Temperature wiring test."}'
                    )
                ],
            )
        )


class _CaptureTemperatureClient:
    def __init__(self, *args, **kwargs):
        self.chat = type("Chat", (), {"completions": _CaptureTemperatureCompletions()})()


class _FakeProvider(LLMProvider):
    @property
    def model_id(self) -> str:
        return "openai/gpt-4o"

    @property
    def provider_name(self) -> str:
        return "openrouter"

    def call(self, system_prompt: str, user_message: str, action_tool_schema):
        return ProviderCallResult(
            reasoning_trace="Monitor while collecting additional information.",
            action_dict={
                "action_type": "monitor",
                "rationale": "Gather more information before escalating.",
            },
            raw_response='{"mock": true}',
            usage={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
        )


class ProviderIntegrationTests(unittest.TestCase):
    def test_openrouter_provider_parses_function_call(self):
        os.environ["OPENROUTER_API_KEY"] = "test-key"
        with patch("providers.openrouter_provider.openai.OpenAI", _FakeOpenAIClient):
            provider = OpenRouterProvider(model="openai/gpt-4o")
            result = provider.call(
                system_prompt="system",
                user_message="user",
                action_tool_schema=ACTION_TOOL_SCHEMA,
            )

        self.assertEqual(provider.provider_name, "openrouter")
        self.assertEqual(provider.model_id, "openai/gpt-4o")
        self.assertEqual(result.action_dict["action_type"], "monitor")
        self.assertIn("Assess pressure", result.reasoning_trace)
        self.assertEqual(result.usage["total_tokens"], 168)

    def test_simulation_logs_provider_metadata(self):
        scenario = TaiwanStraitScenario(seed=7)
        state = scenario.initialize()
        provider = _FakeProvider()
        actors = {
            name: LLMDecisionActor(
                actor=actor,
                doctrine_condition="baseline",
                run_id="provider_meta_test",
                provider=provider,
            )
            for name, actor in state.actors.items()
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            engine = SimulationEngine(
                state=state,
                actors=actors,
                doctrine_condition="baseline",
                run_id="provider_meta_test",
                run_number=1,
                seed=7,
                provider_name=provider.provider_name,
                model_id=provider.model_id,
                log_dir=tmpdir,
                verbose=False,
                scenario=scenario,
            )
            final_state, outcome = engine.run(max_turns=1)
            self.assertEqual(len(final_state.turn_logs), 1)
            self.assertIn(outcome, {"frozen_conflict", "deterrence_success", "defense_success"})

            db_path = Path(tmpdir) / "provider_meta_test.db"
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT provider_name, model_id FROM runs")
            self.assertEqual(cur.fetchone(), ("openrouter", "openai/gpt-4o"))
            cur.execute(
                "SELECT DISTINCT provider_name, model_id FROM decisions ORDER BY provider_name, model_id"
            )
            self.assertEqual(cur.fetchall(), [("openrouter", "openai/gpt-4o")])
            conn.close()

    def test_experiment_runner_accepts_openrouter_provider(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("experiments.runner.build_provider", return_value=_FakeProvider()):
                db_path = run_single(
                    scenario_name="taiwan_strait",
                    doctrine="baseline",
                    run_number=1,
                    max_turns=1,
                    log_dir=tmpdir,
                    experiment_id="exp_provider_test",
                    base_seed=0,
                    provider_name="openrouter",
                    model="openai/gpt-4o",
                )
            self.assertIsNotNone(db_path)
            self.assertTrue(Path(db_path).exists())

    def test_openrouter_provider_retries_without_tool_choice(self):
        os.environ["OPENROUTER_API_KEY"] = "test-key"
        with patch("providers.openrouter_provider.openai.OpenAI", _FallbackToolChoiceClient):
            provider = OpenRouterProvider(model="qwen/qwen3-235b-a22b")
            result = provider.call(
                system_prompt="system",
                user_message="user",
                action_tool_schema=ACTION_TOOL_SCHEMA,
            )

        self.assertEqual(result.action_dict["action_type"], "monitor")
        # qwen3-235b-a22b is in MODEL_CAPABILITY_MAP as "json" —
        # it now skips tool-call attempts and goes straight to json_content.
        self.assertEqual(result.usage["compatibility_strategy"], "json_content")

    def test_openrouter_provider_falls_back_to_json_content(self):
        os.environ["OPENROUTER_API_KEY"] = "test-key"
        with patch("providers.openrouter_provider.openai.OpenAI", _JsonFallbackClient):
            provider = OpenRouterProvider(model="google/gemini-3.1-pro-preview")
            result = provider.call(
                system_prompt="system",
                user_message="user",
                action_tool_schema=ACTION_TOOL_SCHEMA,
            )

        self.assertEqual(result.action_dict["action_type"], "monitor")
        self.assertEqual(result.action_dict["intensity"], "medium")
        self.assertEqual(result.usage["compatibility_strategy"], "json_content")

    def test_openrouter_provider_uses_env_temperature(self):
        with patch.dict(
            os.environ,
            {"OPENROUTER_API_KEY": "test-key", "OSE_DEFAULT_TEMPERATURE": "0.35"},
            clear=False,
        ):
            with patch("providers.openrouter_provider.openai.OpenAI", _CaptureTemperatureClient):
                provider = OpenRouterProvider(model="openai/gpt-4o")
                provider.call(
                    system_prompt="system",
                    user_message="user",
                    action_tool_schema=ACTION_TOOL_SCHEMA,
                )

        first_call = provider._client.chat.completions.calls[0]
        self.assertEqual(first_call["temperature"], 0.35)


if __name__ == "__main__":
    unittest.main()
