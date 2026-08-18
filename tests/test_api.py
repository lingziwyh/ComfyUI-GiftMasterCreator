from __future__ import annotations

import json
from pathlib import Path
import unittest

from giftmaster.api import (
    APIConfig,
    build_endpoint,
    clear_session_keys,
    parse_api_response,
    redact_text,
    store_session_key,
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

    def test_redacts_explicit_and_structured_secrets(self):
        secret = "unit-test-secret-value"
        redacted = redact_text(
            f"Authorization: Bearer {secret}; api_key={secret}; upstream said {secret}",
            (secret,),
        )
        self.assertNotIn(secret, redacted)
        self.assertIn("[REDACTED]", redacted)

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
