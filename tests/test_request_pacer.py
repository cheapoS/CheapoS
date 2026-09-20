import os
import time
import threading
import unittest
from unittest.mock import Mock, patch

from cheapos.request_pacer import (
    RequestPacer,
    provider_identity,
    pacing_interval,
    PROVIDER_PACING_SECONDS,
    DEFAULT_FREE_PACING_SECONDS,
)
from cheapos.providers import validate_provider


class TestRequestPacer(unittest.TestCase):
    def setUp(self):
        self.pacer = RequestPacer()

    def test_provider_identity_detection(self):
        # Local and fixture
        self.assertEqual(provider_identity({"local": True}), "local")
        self.assertEqual(provider_identity({"base_url": "http://127.0.0.1:11434/v1"}), "local")
        self.assertEqual(provider_identity({"base_url": "http://localhost:5000/v1"}), "local")
        self.assertEqual(provider_identity({"model": "fixture"}), "fixture")
        self.assertEqual(provider_identity({"model": "fixture-worker"}), "fixture")

        # Explicit provider tag
        self.assertEqual(provider_identity({"provider": "Nvidia", "model": "any"}), "nvidia")
        self.assertEqual(provider_identity({"provider": "OpenCode-Zen"}), "opencode")
        self.assertEqual(provider_identity({"provider": "oc"}), "opencode")
        self.assertEqual(provider_identity({"provider": "Google"}), "antigravity")

        # Model prefix and naming heuristics
        self.assertEqual(provider_identity({"model": "nvidia/nemotron-3-super-120b-a12b"}), "nvidia")
        self.assertEqual(provider_identity({"model": "groq/openai/gpt-oss-120b"}), "groq")
        self.assertEqual(provider_identity({"model": "groq/qwen/qwen3.8-27b"}), "groq")
        self.assertEqual(provider_identity({"model": "openrouter/deepseek/deepseek-r1:free"}), "openrouter")
        self.assertEqual(provider_identity({"model": "cohere/north-mini-code:free"}), "openrouter")
        self.assertEqual(provider_identity({"model": "meta-llama/llama-3.3-70b-instruct:free"}), "openrouter")
        self.assertEqual(provider_identity({"model": "ling-3.0-flash-fin-free"}), "opencode")
        self.assertEqual(provider_identity({"model": "nemotron-3.5-lightning-free"}), "opencode")
        self.assertEqual(provider_identity({"model": "antigravity/gemini-2.5-pro"}), "antigravity")
        self.assertEqual(provider_identity({"model": "kiro/claude-sonnet-4.5"}), "kiro")

    def test_pacing_interval_defaults_and_overrides(self):
        # Known free providers
        self.assertEqual(pacing_interval({"model": "nvidia/nemotron-3-super-120b-a12b"}), 4.0)
        self.assertEqual(pacing_interval({"model": "groq/openai/gpt-oss-120b"}), 2.0)
        self.assertEqual(pacing_interval({"model": "cohere/north-mini-code:free"}), 5.0)
        self.assertEqual(pacing_interval({"model": "ling-3.0-flash-fin-free"}), 4.0)
        self.assertEqual(pacing_interval({"model": "antigravity/gemini-2.5-pro"}), 4.0)

        # Payload-aware token scaling
        self.assertEqual(pacing_interval({"model": "cohere/north-mini-code:free"}, payload_bytes=5_000), 5.0)
        self.assertEqual(pacing_interval({"model": "cohere/north-mini-code:free"}, payload_bytes=80_000), 7.0)
        self.assertEqual(pacing_interval({"model": "cohere/north-mini-code:free"}, payload_bytes=200_000), 9.0)

        self.assertEqual(pacing_interval({"model": "groq/qwen/planner"}, payload_bytes=80_000), 4.0)
        self.assertEqual(pacing_interval({"model": "groq/qwen/planner"}, payload_bytes=200_000), 6.0)

        # Local, fixture, and paid models
        self.assertEqual(pacing_interval({"local": True}), 0.0)
        self.assertEqual(pacing_interval({"model": "fixture"}), 0.0)
        self.assertEqual(pacing_interval({"model": "nvidia/nemotron", "input_rate": 1.0, "output_rate": 2.0}), 0.0)

        # Included access is treated as free even if rates are zeroed
        self.assertEqual(pacing_interval({"model": "nvidia/nemotron", "input_rate": 0.0, "output_rate": 0.0, "access": "included"}), 4.0)

        # Explicit pacing interval override
        self.assertEqual(pacing_interval({"model": "nvidia/nemotron", "pacing_interval": 0.75}), 0.75)
        self.assertEqual(pacing_interval({"model": "nvidia/nemotron", "pacing": False}), 0.0)

        # Environment variable override
        os.environ["CHEAPOS_DISABLE_PACING"] = "1"
        try:
            self.assertEqual(pacing_interval({"model": "nvidia/nemotron-3-super-120b-a12b"}), 0.0)
        finally:
            del os.environ["CHEAPOS_DISABLE_PACING"]

    def test_throttle_delays_consecutive_requests(self):
        # Measure the requested delay, independent of CI scheduling jitter.
        provider = "test_provider"
        interval = 0.15
        clock=[100.0]
        def advance(seconds): clock[0]+=seconds
        with patch('cheapos.request_pacer.time.monotonic',side_effect=lambda:clock[0]), patch('cheapos.request_pacer.time.sleep',side_effect=advance) as sleep:
            with self.pacer.throttle(provider, interval): pass
            sleep.assert_not_called()
            # Time already spent outside a request counts toward the cooldown.
            clock[0]+=0.04
            timing={}
            with self.pacer.throttle(provider, interval,timing=timing): pass
            self.assertAlmostEqual(clock[0],100.15)
            self.assertAlmostEqual(timing['pacing_seconds'],0.11)
            self.assertTrue(sleep.called)
            self.assertAlmostEqual(sum(args[0] for args,kwargs in sleep.call_args_list),0.11)
            clock[0]+=interval
            sleep.reset_mock()
            with self.pacer.throttle(provider, interval): pass
            sleep.assert_not_called()

        stats = self.pacer.stats()
        self.assertEqual(stats["delays_count"].get(provider), 1)
        self.assertAlmostEqual(stats['total_delayed_seconds'][provider],0.11)

    def test_throttle_does_not_delay_different_providers(self):
        # Delays for provider A should not delay provider B when no shared gateway
        interval = 0.2
        with self.pacer.throttle("provider_a", interval):
            pass

        start = time.monotonic()
        with self.pacer.throttle("provider_b", interval):
            pass
        duration = time.monotonic() - start
        self.assertLess(duration, 0.05)

    def test_gateway_does_not_share_upstream_cooldowns(self):
        from cheapos.request_pacer import gateway_identity
        self.assertEqual(gateway_identity({"gateway": "omniroute"}), "omniroute")
        self.assertEqual(gateway_identity({"base_url": "http://127.0.0.1:20128/v1"}), "omniroute")

        clock=[100.0]
        def advance(seconds): clock[0]+=seconds
        with patch('cheapos.request_pacer.time.monotonic',side_effect=lambda:clock[0]), patch('cheapos.request_pacer.time.sleep',side_effect=advance):
            with self.pacer.throttle('nvidia',4,gateway='omniroute'): pass
            with self.pacer.throttle('openrouter',5,gateway='omniroute'): pass
            self.assertEqual(clock[0],100)
            timing={}
            with self.pacer.throttle('openrouter',5,gateway='omniroute',timing=timing): pass
            self.assertEqual(clock[0],105)
            self.assertEqual(timing['pacing_seconds'],5)

    def test_slow_provider_does_not_hold_another_providers_slot(self):
        completed=threading.Event();errors=[]
        def other():
            try:
                with self.pacer.throttle('openrouter',5,gateway='omniroute'): completed.set()
            except Exception as error: errors.append(error)
        with self.pacer.throttle('nvidia',4,gateway='omniroute'):
            thread=threading.Thread(target=other);thread.start()
            finished=completed.wait(1)
        thread.join(1)
        self.assertTrue(finished);self.assertFalse(errors);self.assertFalse(thread.is_alive())

    def test_cancelled_queue_does_not_dispatch_or_renew_cooldown(self):
        self.pacer._last_completed['openrouter']=10
        stopped=Mock(side_effect=[False,True])
        with patch('cheapos.request_pacer.time.monotonic',return_value=20):
            with self.assertRaises(InterruptedError):
                with self.pacer.throttle('openrouter',5,stopped=stopped): self.fail('Dispatched after stop')
        self.assertEqual(self.pacer._last_completed['openrouter'],10)

    def test_throttle_interruption(self):
        stopped = False
        def is_stopped():
            return stopped

        # Run first request to set last_completed
        with self.pacer.throttle("provider_stop", 0.5):
            pass

        stopped = True
        with self.assertRaises(InterruptedError):
            with self.pacer.throttle("provider_stop", 0.5, stopped=is_stopped):
                pass

    def test_throttle_zero_interval(self):
        start = time.monotonic()
        with self.pacer.throttle("local", 0.0):
            pass
        with self.pacer.throttle("local", 0.0):
            pass
        self.assertLess(time.monotonic() - start, 0.05)

    def test_validate_provider_preserves_pacing_metadata(self):
        cfg = {
            "base_url": "http://127.0.0.1:20128/v1",
            "model": "groq/openai/gpt-oss-120b",
            "input_rate": 0,
            "output_rate": 0,
            "gateway": "omniroute",
            "provider": "groq",
            "pacing": True,
            "pacing_interval": 1.2,
        }
        validated = validate_provider(cfg, "worker")
        self.assertEqual(validated["provider"], "groq")
        self.assertEqual(validated["pacing"], True)
        self.assertEqual(validated["pacing_interval"], 1.2)


if __name__ == "__main__":
    unittest.main()
