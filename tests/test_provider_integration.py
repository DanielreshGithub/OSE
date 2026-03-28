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
    def __init__(self, message):
        self.message = message


class _FakeResponse:
    def __init__(self, message):
        self.choices = [_FakeChoice(message)]
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


if __name__ == "__main__":
    unittest.main()
