from __future__ import annotations

import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from giftmaster.api import (
    APIConfig,
    _resolve_key,
    build_endpoint,
    clear_session_key_slot,
    clear_session_keys,
    is_session_key_slot_configured,
    parse_api_response,
    redact_text,
    store_session_key,
    store_session_key_slot,
    validate_api_url,
)
from giftmaster.errors import APIError, ConfigurationError


class APIURLTests(unittest.TestCase):
    def test_chat_and_responses_paths_are_appended_once(self):
        chat = build_endpoint(APIConfig(protocol="openai_chat", base_url="https://example.com/v1", model="model"))
        self.assertEqual("https://example.com/v1/chat/completions", chat)

        complete_chat = build_endpoint(
            APIConfig(
                protocol="openai_chat",
                base_url="https://example.com/v1/chat/completions/?region=cn",
                model="model",
            )
        )
        self.assertEqual("https://example.com/v1/chat/completions?region=cn", complete_chat)

        responses = build_endpoint(
            APIConfig(protocol="openai_responses", base_url="https://example.com/v1", model="model")
        )
        self.assertEqual("https://example.com/v1/responses", responses)

    def test_generic_azure_requires_user_supplied_deployment(self):
        config = APIConfig(
            protocol="azure_openai_chat",
            base_url="https://example.openai.azure.com",
            model="",
            azure_deployment="gift-model",
            api_version="2025-01-01-preview",
        )
        endpoint = build_endpoint(config)
        self.assertEqual(
            "https://example.openai.azure.com/openai/deployments/gift-model/chat/completions?api-version=2025-01-01-preview",
            endpoint,
        )

    def test_remote_http_requires_explicit_opt_in(self):
        with self.assertRaisesRegex(ConfigurationError, "HTTPS"):
            validate_api_url("http://example.com/v1")
        self.assertEqual(
            "http://example.com/v1",
            validate_api_url("http://example.com/v1", allow_insecure_http=True),
        )

    def test_loopback_http_is_allowed(self):
        for url in ("http://localhost:8188/v1", "http://127.0.0.1:8080/v1", "http://[::1]:8000/v1"):
            with self.subTest(url=url):
                self.assertEqual(url, validate_api_url(url))

    def test_credentials_fragment_and_sensitive_query_are_rejected(self):
        unsafe = (
            "https://user:password@example.com/v1",
            "https://example.com/v1#private",
            "https://example.com/v1?api_key=forbidden",
            "https://example.com/v1?access_token=forbidden",
            "https://example.com/v1?signature=forbidden",
        )
        for url in unsafe:
            with self.subTest(url=url), self.assertRaises(ConfigurationError):
                validate_api_url(url)

    def test_invalid_ports_are_reported_as_configuration_errors(self):
        for url in ("https://example.com:bad/v1", "https://example.com:99999/v1"):
            with self.subTest(url=url), self.assertRaisesRegex(ConfigurationError, "端口"):
                validate_api_url(url)

    def test_unknown_protocol_is_rejected(self):
        with self.assertRaisesRegex(ConfigurationError, "协议"):
            build_endpoint(APIConfig(protocol="unknown", base_url="https://example.com/v1", model="model"))


class APIResponseTests(unittest.TestCase):
    def test_parses_chat_text_and_usage(self):
        text, usage = parse_api_response(
            {
                "choices": [{"message": {"content": "final prompt"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            },
            "openai_chat",
        )
        self.assertEqual("final prompt", text)
        self.assertEqual(120, usage["total_tokens"])

    def test_parses_chat_content_blocks(self):
        text, _usage = parse_api_response(
            {
                "choices": [
                    {
                        "message": {
                            "content": [
                                {"type": "text", "text": "first "},
                                {"type": "output_text", "text": "second"},
                            ]
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
            "openai_chat",
        )
        self.assertEqual("first second", text)

    def test_parses_responses_top_level_and_nested_output(self):
        text, _ = parse_api_response(
            {"status": "completed", "output_text": "top-level"},
            "openai_responses",
        )
        self.assertEqual("top-level", text)

        text, _ = parse_api_response(
            {
                "status": "completed",
                "output": [{"content": [{"type": "output_text", "text": "nested"}]}],
            },
            "openai_responses",
        )
        self.assertEqual("nested", text)

    def test_truncation_refusal_failure_and_empty_text_are_errors(self):
        failures = (
            ({"choices": [{"message": {"content": "partial"}, "finish_reason": "length"}]}, "openai_chat"),
            ({"choices": [{"message": {"content": "", "refusal": "no"}}]}, "openai_chat"),
            (
                {"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}},
                "openai_responses",
            ),
            ({"status": "failed", "output": []}, "openai_responses"),
            ({"status": "completed", "output_text": ""}, "openai_responses"),
        )
        for payload, protocol in failures:
            with self.subTest(payload=payload, protocol=protocol), self.assertRaises(APIError):
                parse_api_response(payload, protocol)

    def test_non_object_and_provider_error_are_rejected(self):
        with self.assertRaisesRegex(APIError, "顶层"):
            parse_api_response(["not", "an", "object"], "openai_chat")  # type: ignore[arg-type]
        with self.assertRaisesRegex(APIError, "bad request"):
            parse_api_response({"error": {"message": "bad request"}}, "openai_chat")


class APISecretSafetyTests(unittest.TestCase):
    def tearDown(self):
        clear_session_keys()

    def test_session_key_reference_does_not_contain_secret(self):
        secret = "unit-test-direct-secret-value"
        reference = store_session_key(secret)
        self.assertTrue(reference)
        self.assertNotIn(secret, reference)
        serialized = json.dumps(APIConfig(api_key_ref=reference).__dict__, ensure_ascii=False)
        self.assertNotIn(secret, serialized)

    def test_session_key_reference_is_excluded_from_config_repr(self):
        secret = "unit-test-direct-secret-value"
        reference = store_session_key(secret)
        rendered = repr(APIConfig(api_key_ref=reference))
        self.assertNotIn(reference, rendered)
        self.assertNotIn(secret, rendered)

    def test_fixed_session_slot_is_runtime_only_and_bound_to_exact_config(self):
        slot = "GIFTMASTER_TEST_SLOT"
        secret = "unit-test-slot-secret"
        config = APIConfig(
            protocol="openai_chat",
            base_url="https://example.com/v1",
            model="bound-model",
            api_key_env="",
            api_key_slot=slot,
        )
        store_session_key_slot(slot, secret, config)
        self.assertTrue(is_session_key_slot_configured(slot))
        self.assertEqual(secret, _resolve_key(config, build_endpoint(config)))

        changed = APIConfig(
            protocol="openai_chat",
            base_url="https://example.com/v1",
            model="different-model",
            api_key_env="",
            api_key_slot=slot,
        )
        with self.assertRaisesRegex(ConfigurationError, "不匹配"):
            _resolve_key(changed, build_endpoint(changed))

        self.assertTrue(clear_session_key_slot(slot))
        self.assertFalse(is_session_key_slot_configured(slot))

    def test_invalid_slot_replacement_preserves_existing_secret(self):
        slot = "GIFTMASTER_TEST_SLOT"
        config = APIConfig(
            protocol="openai_chat",
            base_url="https://example.com/v1",
            model="bound-model",
            api_key_env="",
            api_key_slot=slot,
        )
        store_session_key_slot(slot, "existing-secret", config)
        with self.assertRaises(ConfigurationError):
            store_session_key_slot(slot, "bad\nsecret", config)
        self.assertEqual("existing-secret", _resolve_key(config, build_endpoint(config)))

    def test_session_slot_cannot_be_combined_with_other_key_sources(self):
        config = APIConfig(
            protocol="openai_chat",
            base_url="https://example.com/v1",
            model="bound-model",
            api_key_env="GIFTMASTER_OTHER_KEY",
            api_key_ref="another-source",
            api_key_slot="GIFTMASTER_TEST_SLOT",
        )
        with self.assertRaisesRegex(ConfigurationError, "不能与其他"):
            _resolve_key(config, build_endpoint(config))

    def test_redacts_explicit_and_structured_secrets(self):
        secret = "unit-test-secret-value"
        redacted = redact_text(
            f"Authorization: Bearer {secret}; api_key={secret}; upstream said {secret}",
            (secret,),
        )
        self.assertNotIn(secret, redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_windows_user_environment_fallback_handles_recently_set_key(self):
        env_name = "GIFTMASTER_TEST_RECENT_KEY"
        registry_values = {
            env_name: "registry-secret",
            env_name + "_ORIGIN": "https://example.com",
        }
        config = APIConfig(api_key_env=env_name, model="model")
        with patch.dict(os.environ, {}, clear=True), patch(
            "giftmaster.api._read_windows_user_environment",
            side_effect=lambda name: registry_values.get(name, ""),
        ):
            self.assertEqual(
                "registry-secret",
                _resolve_key(config, "https://example.com/v1/chat/completions"),
            )

    def test_process_environment_takes_precedence_over_windows_fallback(self):
        env_name = "GIFTMASTER_TEST_EXISTING_KEY"
        config = APIConfig(api_key_env=env_name, model="model")
        with patch.dict(
            os.environ,
            {
                env_name: "process-secret",
                env_name + "_ORIGIN": "https://example.com",
            },
            clear=True,
        ), patch(
            "giftmaster.api._read_windows_user_environment",
            return_value="registry-secret",
        ) as registry_read:
            self.assertEqual(
                "process-secret",
                _resolve_key(config, "https://example.com/v1/chat/completions"),
            )
            registry_read.assert_not_called()

    def test_process_key_without_process_origin_never_mixes_registry_origin(self):
        env_name = "GIFTMASTER_TEST_PROCESS_ONLY_KEY"
        config = APIConfig(api_key_env=env_name, model="model")
        with patch.dict(os.environ, {env_name: "process-secret"}, clear=True), patch(
            "giftmaster.api._read_windows_user_environment",
            return_value="https://example.com",
        ) as registry_read, self.assertRaises(ConfigurationError):
            _resolve_key(config, "https://example.com/v1/chat/completions")
        registry_read.assert_not_called()

    def test_empty_process_key_explicitly_blocks_registry_fallback(self):
        env_name = "GIFTMASTER_TEST_DISABLED_KEY"
        config = APIConfig(api_key_env=env_name, model="model")
        with patch.dict(os.environ, {env_name: ""}, clear=True), patch(
            "giftmaster.api._read_windows_user_environment",
            return_value="registry-secret",
        ) as registry_read, self.assertRaises(ConfigurationError):
            _resolve_key(config, "https://example.com/v1/chat/completions")
        registry_read.assert_not_called()

    def test_registry_key_without_registry_origin_is_rejected(self):
        env_name = "GIFTMASTER_TEST_REGISTRY_KEY_ONLY"
        config = APIConfig(api_key_env=env_name, model="model")
        with patch.dict(os.environ, {}, clear=True), patch(
            "giftmaster.api._read_windows_user_environment",
            side_effect=lambda name: "registry-secret" if name == env_name else "",
        ), self.assertRaises(ConfigurationError):
            _resolve_key(config, "https://example.com/v1/chat/completions")

    def test_invalid_environment_name_never_reads_registry(self):
        config = APIConfig(api_key_env="OTHER_PROVIDER_KEY", model="model")
        with patch.dict(os.environ, {}, clear=True), patch(
            "giftmaster.api._read_windows_user_environment",
            return_value="registry-secret",
        ) as registry_read, self.assertRaises(ConfigurationError):
            _resolve_key(config, "https://example.com/v1/chat/completions")
        registry_read.assert_not_called()

    def test_public_runtime_contains_no_private_provider_defaults(self):
        root = Path(__file__).resolve().parents[1]
        production_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((root / "giftmaster").glob("*.py"))
        ).lower()
        forbidden = (
            "private-provider.example.invalid",
            "private_provider_api_key",
            "x-private-provider-trace",
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, production_text)


if __name__ == "__main__":
    unittest.main()
