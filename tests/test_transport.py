from __future__ import annotations

import json
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest
from urllib import error

from giftmaster.api import APIClient, APIConfig, GenerationSettings
from giftmaster.errors import APIError


class _Handler(BaseHTTPRequestHandler):
    calls = []
    statuses = []
    protocol_kind = "chat"
    response_payload = None

    def log_message(self, *_args):
        return

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        type(self).calls.append((self.path, dict(self.headers), body))
        status = type(self).statuses.pop(0) if type(self).statuses else 200
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        if status == 429:
            self.send_header("Retry-After", "0")
        self.end_headers()
        if type(self).response_payload is not None:
            payload = type(self).response_payload
        elif status == 200 and type(self).protocol_kind == "responses":
            payload = {"status": "completed", "output_text": "responses result", "usage": {"total_tokens": 7}}
        elif status == 200:
            payload = {"choices": [{"message": {"content": "chat result"}, "finish_reason": "stop"}]}
        else:
            payload = {"error": {"message": "try later"}}
        self.wfile.write(json.dumps(payload).encode("utf-8"))


class LocalServerTests(unittest.TestCase):
    def setUp(self):
        _Handler.calls = []
        _Handler.statuses = []
        _Handler.protocol_kind = "chat"
        _Handler.response_payload = None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}/v1"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_chat_payload_and_no_auth_localhost(self):
        client = APIClient(APIConfig(base_url=self.base, model="chat-model", no_auth=True, retries=0))
        text, info = client.complete("system", "task", settings=GenerationSettings(max_output_tokens=321))
        self.assertEqual("chat result", text)
        path, headers, body = _Handler.calls[0]
        self.assertEqual("/v1/chat/completions", path)
        self.assertNotIn("Authorization", headers)
        self.assertEqual(321, body["max_tokens"])
        self.assertEqual("system", body["messages"][0]["content"])
        self.assertEqual(1, info["requests"])

    def test_non_azure_protocol_ignores_azure_compatibility_setting(self):
        client = APIClient(
            APIConfig(
                protocol="openai_chat",
                base_url=self.base,
                model="gpt-5-unit",
                azure_auth="bytedance_compat",
                no_auth=True,
                retries=0,
            )
        )
        client.complete("system", "task")
        _path, headers, body = _Handler.calls[0]
        self.assertEqual(4096, body["max_completion_tokens"])
        self.assertNotIn("max_tokens", body)
        self.assertNotIn("X-TT-LOGID", headers)

    def test_responses_payload_keeps_image_order(self):
        _Handler.protocol_kind = "responses"
        client = APIClient(
            APIConfig(protocol="openai_responses", base_url=self.base, model="response-model", no_auth=True, retries=0)
        )
        images = ["data:image/jpeg;base64,AA==", "data:image/jpeg;base64,BB=="]
        text, _info = client.complete("system", "task", images, GenerationSettings(max_output_tokens=123))
        self.assertEqual("responses result", text)
        _path, _headers, body = _Handler.calls[0]
        self.assertEqual(123, body["max_output_tokens"])
        content = body["input"][0]["content"]
        self.assertEqual(images, [item["image_url"] for item in content if item["type"] == "input_image"])

    def test_retryable_status_is_retried_once(self):
        _Handler.statuses = [429, 200]
        client = APIClient(APIConfig(base_url=self.base, model="chat-model", no_auth=True, retries=1))
        text, info = client.complete("system", "task")
        self.assertEqual("chat result", text)
        self.assertEqual(2, info["requests"])
        self.assertEqual(2, len(_Handler.calls))

    def test_5xx_is_not_retried_even_when_retry_budget_exists(self):
        _Handler.statuses = [500, 200]
        client = APIClient(APIConfig(base_url=self.base, model="chat-model", no_auth=True, retries=3))
        with self.assertRaises(APIError):
            client.complete("system", "task")
        self.assertEqual(1, len(_Handler.calls))

    def test_origin_bound_environment_key_and_provider_error_redaction(self):
        name = "GIFTMASTER_UNIT_API_KEY"
        secret = "unit-provider-secret-value"
        os.environ[name] = secret
        os.environ[name + "_ORIGIN"] = f"http://127.0.0.1:{self.server.server_port}"
        self.addCleanup(os.environ.pop, name, None)
        self.addCleanup(os.environ.pop, name + "_ORIGIN", None)
        _Handler.response_payload = {"error": {"message": f"provider echoed {secret}"}}
        client = APIClient(APIConfig(base_url=self.base, model="chat-model", api_key_env=name, retries=0))
        with self.assertRaises(APIError) as captured:
            client.complete("system", "task")
        self.assertNotIn(secret, str(captured.exception))
        self.assertEqual(f"Bearer {secret}", _Handler.calls[0][1]["Authorization"])

    def test_environment_key_cannot_be_redirected_to_another_origin(self):
        name = "GIFTMASTER_UNIT_SCOPED_KEY"
        os.environ[name] = "unit-secret"
        os.environ[name + "_ORIGIN"] = "https://api.example.invalid"
        self.addCleanup(os.environ.pop, name, None)
        self.addCleanup(os.environ.pop, name + "_ORIGIN", None)
        client = APIClient(APIConfig(base_url=self.base, model="chat-model", api_key_env=name, retries=0))
        with self.assertRaisesRegex(Exception, "未授权"):
            client.complete("system", "task")
        self.assertEqual([], _Handler.calls)

    def test_workflow_cannot_read_non_giftmaster_environment_variables(self):
        os.environ["UNIT_UNRELATED_SECRET"] = "must-not-leave-process"
        self.addCleanup(os.environ.pop, "UNIT_UNRELATED_SECRET", None)
        client = APIClient(
            APIConfig(base_url=self.base, model="chat-model", api_key_env="UNIT_UNRELATED_SECRET", retries=0)
        )
        with self.assertRaisesRegex(Exception, "GIFTMASTER_"):
            client.complete("system", "task")
        self.assertEqual([], _Handler.calls)

    def test_azure_deployment_works_without_model_and_uses_api_key_header(self):
        name = "GIFTMASTER_AZURE_UNIT_KEY"
        os.environ[name] = "azure-unit-secret"
        os.environ[name + "_ORIGIN"] = f"http://127.0.0.1:{self.server.server_port}"
        self.addCleanup(os.environ.pop, name, None)
        self.addCleanup(os.environ.pop, name + "_ORIGIN", None)
        config = APIConfig(
            protocol="azure_openai_chat",
            base_url=f"http://127.0.0.1:{self.server.server_port}",
            model="",
            azure_deployment="gift deployment",
            api_version="2025-01-01-preview",
            api_key_env=name,
            retries=0,
        )
        text, info = APIClient(config).complete("system", "task")
        self.assertEqual("chat result", text)
        path, headers, body = _Handler.calls[0]
        self.assertEqual(
            "/openai/deployments/gift%20deployment/chat/completions?api-version=2025-01-01-preview",
            path,
        )
        normalized_headers = {key.lower(): value for key, value in headers.items()}
        self.assertEqual("azure-unit-secret", normalized_headers["api-key"])
        self.assertNotIn("authorization", normalized_headers)
        self.assertNotIn("x-tt-logid", normalized_headers)
        self.assertNotIn("model", body)
        self.assertEqual("gift deployment", info["model"])

    def test_bytedance_compat_sends_dual_auth_and_stable_log_id(self):
        name = "GIFTMASTER_BYTEDANCE_COMPAT_UNIT_KEY"
        secret = "bytedance-unit-secret"
        os.environ[name] = secret
        os.environ[name + "_ORIGIN"] = f"http://127.0.0.1:{self.server.server_port}"
        self.addCleanup(os.environ.pop, name, None)
        self.addCleanup(os.environ.pop, name + "_ORIGIN", None)
        _Handler.statuses = [429, 200]
        config = APIConfig(
            protocol="azure_openai_chat",
            base_url=f"http://127.0.0.1:{self.server.server_port}/gateway",
            model="gpt-unit",
            azure_deployment="gpt-unit",
            api_version="2024-02-01",
            azure_auth="bytedance_compat",
            api_key_env=name,
            retries=1,
        )
        text, _info = APIClient(config).complete("system", "task")
        self.assertEqual("chat result", text)
        path, headers, body = _Handler.calls[0]
        normalized_headers = {key.lower(): value for key, value in headers.items()}
        self.assertEqual(
            "/gateway/openai/deployments/gpt-unit/chat/completions?api-version=2024-02-01",
            path,
        )
        self.assertEqual(secret, normalized_headers["api-key"])
        self.assertEqual(f"Bearer {secret}", normalized_headers["authorization"])
        self.assertRegex(normalized_headers["x-tt-logid"], r"^[0-9a-f]{32}$")
        self.assertEqual("gpt-unit", body["model"])
        self.assertEqual(4096, body["max_tokens"])
        self.assertNotIn("max_completion_tokens", body)
        retry_headers = {key.lower(): value for key, value in _Handler.calls[1][1].items()}
        self.assertEqual(normalized_headers["x-tt-logid"], retry_headers["x-tt-logid"])


class _TimeoutOpener:
    def __init__(self):
        self.calls = 0

    def open(self, *_args, **_kwargs):
        self.calls += 1
        raise error.URLError(socket.timeout("unit timeout"))


class TimeoutTests(unittest.TestCase):
    def test_timeout_is_not_retried(self):
        opener = _TimeoutOpener()
        client = APIClient(
            APIConfig(base_url="http://127.0.0.1:9/v1", model="unit", no_auth=True, retries=3),
            opener=opener,
        )
        with self.assertRaisesRegex(APIError, "不自动重试"):
            client.complete("system", "task")
        self.assertEqual(1, opener.calls)

    def test_authenticated_remote_http_is_never_allowed(self):
        name = "GIFTMASTER_REMOTE_HTTP_TEST_KEY"
        os.environ[name] = "unit-secret"
        os.environ[name + "_ORIGIN"] = "http://192.0.2.1"
        self.addCleanup(os.environ.pop, name, None)
        self.addCleanup(os.environ.pop, name + "_ORIGIN", None)
        opener = _TimeoutOpener()
        client = APIClient(
            APIConfig(
                base_url="http://192.0.2.1/v1",
                model="unit",
                api_key_env=name,
                allow_insecure_http=True,
            ),
            opener=opener,
        )
        with self.assertRaisesRegex(Exception, "HTTPS"):
            client.complete("system", "task")
        self.assertEqual(0, opener.calls)


if __name__ == "__main__":
    unittest.main()
