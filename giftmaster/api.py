"""Dependency-free clients for user-configured OpenAI-compatible APIs."""

from __future__ import annotations

from dataclasses import dataclass
import json
import errno
import http.client
import os
import random
import re
import secrets
import socket
import threading
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib import error, parse, request

from .errors import APIError, ConfigurationError


PROTOCOLS = ("openai_chat", "openai_responses", "azure_openai_chat")
_KEY_VAULT: Dict[str, Tuple[str, str, float]] = {}
_KEY_LOCK = threading.Lock()
_SENSITIVE_QUERY = re.compile(r"(?:api[-_]?key|token|secret|auth|signature|credential|password)", re.I)
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RETRY_CODES = {429}


@dataclass(frozen=True)
class APIConfig:
    protocol: str = "openai_chat"
    base_url: str = "https://api.openai.com/v1"
    model: str = ""
    api_key_env: str = "GIFTMASTER_API_KEY"
    api_key_ref: str = ""
    no_auth: bool = False
    timeout_seconds: int = 120
    retries: int = 0
    allow_insecure_http: bool = False
    azure_deployment: str = ""
    api_version: str = "2024-10-21"
    azure_auth: str = "api_key"
    context_window: int = 128000
    supports_images: bool = True


@dataclass(frozen=True)
class GenerationSettings:
    max_output_tokens: int = 4096
    token_parameter: str = "auto"
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    seed: Optional[int] = None
    image_detail: str = "auto"
    image_max_edge: int = 1024
    jpeg_quality: int = 90
    extra_system_prompt: str = ""


def _origin(url: str, require_root: bool = False) -> str:
    parts = parse.urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ConfigurationError("凭据 origin 必须是有效的 http(s) 地址。")
    if parts.username is not None or parts.password is not None:
        raise ConfigurationError("凭据 origin 不能包含用户名或密码。")
    if require_root and (parts.query or parts.fragment):
        raise ConfigurationError("凭据 origin 不能包含查询参数或 fragment。")
    if require_root and parts.path not in {"", "/"}:
        raise ConfigurationError("凭据 origin 只能包含协议、主机和可选端口，不能包含路径。")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise ConfigurationError("API origin 的端口无效。") from exc
    host = parts.hostname.lower()
    display_host = f"[{host}]" if ":" in host else host
    return f"{parts.scheme}://{display_host}:{port}"


def store_session_key(value: str, origin_scope: str = "") -> str:
    value = (value or "").strip()
    if not value:
        return ""
    ref = secrets.token_urlsafe(18)
    with _KEY_LOCK:
        now = time.time()
        expired = [key for key, (_value, _host, created) in _KEY_VAULT.items() if now - created > 12 * 60 * 60]
        for key in expired:
            _KEY_VAULT.pop(key, None)
        while len(_KEY_VAULT) >= 64:
            _KEY_VAULT.pop(next(iter(_KEY_VAULT)))
        scope = _origin(origin_scope, require_root=True) if origin_scope else ""
        _KEY_VAULT[ref] = (value, scope, now)
    return ref


def clear_session_keys() -> None:
    with _KEY_LOCK:
        _KEY_VAULT.clear()


def _resolve_key(config: APIConfig, endpoint: str) -> str:
    if config.no_auth:
        return ""
    endpoint_parts = parse.urlsplit(endpoint)
    if endpoint_parts.scheme == "http" and not _is_loopback(endpoint_parts.hostname):
        raise ConfigurationError("带密钥的远程 API 必须使用 HTTPS；远程 HTTP 只允许显式无鉴权模式。")
    direct = ""
    direct_origin = ""
    if config.api_key_ref:
        with _KEY_LOCK:
            stored = _KEY_VAULT.get(config.api_key_ref)
            if stored and time.time() - stored[2] <= 12 * 60 * 60:
                direct, direct_origin, _created = stored
            elif stored:
                _KEY_VAULT.pop(config.api_key_ref, None)
    if direct:
        endpoint_origin = _origin(endpoint)
        if direct_origin and direct_origin != endpoint_origin:
            raise ConfigurationError("本次会话密钥已绑定到另一个 API origin，请重新配置密钥。")
        return direct
    if config.api_key_env:
        if not _ENV_NAME.fullmatch(config.api_key_env):
            raise ConfigurationError("API 密钥环境变量名格式无效。")
        if not config.api_key_env.startswith("GIFTMASTER_"):
            raise ConfigurationError("为防止恶意工作流读取其他凭据，环境变量名必须以 GIFTMASTER_ 开头。")
        value = os.environ.get(config.api_key_env, "").strip()
        if value:
            endpoint_origin = _origin(endpoint)
            raw_origins = [
                item.strip() for item in os.environ.get(config.api_key_env + "_ORIGIN", "").split(",") if item.strip()
            ]
            allowed_origins = {_origin(item, require_root=True) for item in raw_origins}
            if endpoint_origin not in allowed_origins:
                raise ConfigurationError(
                    f"环境变量密钥未授权给 origin {endpoint_origin}；请在 {config.api_key_env}_ORIGIN 中明确填写。"
                )
            return value
    raise ConfigurationError("未找到 API 密钥；请设置环境变量，或在本次 ComfyUI 会话中录入密钥。")


def _is_loopback(hostname: Optional[str]) -> bool:
    host = (hostname or "").strip("[]").lower()
    return host in {"localhost", "127.0.0.1", "::1"} or host.startswith("127.")


def validate_api_url(url: str, allow_insecure_http: bool = False) -> str:
    value = (url or "").strip()
    if not value:
        raise ConfigurationError("API 地址不能为空。")
    parts = parse.urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ConfigurationError("API 地址必须是有效的 http(s) URL。")
    if parts.username is not None or parts.password is not None:
        raise ConfigurationError("API 地址不能包含用户名或密码。")
    if parts.fragment:
        raise ConfigurationError("API 地址不能包含 fragment。")
    try:
        _ = parts.port
    except ValueError as exc:
        raise ConfigurationError("API 地址端口无效。") from exc
    for key, _ in parse.parse_qsl(parts.query, keep_blank_values=True):
        if _SENSITIVE_QUERY.search(key):
            raise ConfigurationError("API 地址查询参数中不能携带密钥、令牌或签名。")
    if parts.scheme == "http" and not (_is_loopback(parts.hostname) or allow_insecure_http):
        raise ConfigurationError("公网 API 必须使用 HTTPS；局域网 HTTP 需要显式开启不安全地址选项。")
    return parse.urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), parts.query, ""))


def _append_path(parts: parse.SplitResult, suffix: str) -> parse.SplitResult:
    path = parts.path.rstrip("/")
    if not path.lower().endswith(suffix.lower()):
        path += suffix if suffix.startswith("/") else "/" + suffix
    return parts._replace(path=path)


def build_endpoint(config: APIConfig) -> str:
    if config.protocol not in PROTOCOLS:
        raise ConfigurationError(f"不支持的 API 协议：{config.protocol}")
    base = validate_api_url(config.base_url, config.allow_insecure_http)
    parts = parse.urlsplit(base)
    if config.protocol == "openai_responses":
        parts = _append_path(parts, "/responses")
    elif config.protocol == "openai_chat":
        parts = _append_path(parts, "/chat/completions")
    else:
        if not parts.path.lower().endswith("/chat/completions"):
            deployment = (config.azure_deployment or config.model).strip()
            if not deployment:
                raise ConfigurationError("Azure OpenAI 需要 deployment 名称。")
            suffix = f"/openai/deployments/{parse.quote(deployment, safe='')}/chat/completions"
            parts = _append_path(parts, suffix)
        query = parse.parse_qsl(parts.query, keep_blank_values=True)
        if not any(key.lower() == "api-version" for key, _ in query):
            if not config.api_version.strip():
                raise ConfigurationError("Azure OpenAI 需要 api-version。")
            query.append(("api-version", config.api_version.strip()))
        parts = parts._replace(query=parse.urlencode(query))
    return parse.urlunsplit(parts)


build_request_url = build_endpoint


def redact_text(value: Any, secrets_to_hide: Sequence[str] = ()) -> str:
    text = str(value)
    for secret in secrets_to_hide:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+\-/=]+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)((?:api[-_]?key|token|secret|password)[\"']?\s*[:=]\s*[\"']?)[^\s\"'&,}]+", r"\1[REDACTED]", text)
    return text[:2000]


def _usage(data: Mapping[str, Any]) -> Dict[str, Any]:
    value = data.get("usage")
    return dict(value) if isinstance(value, Mapping) else {}


def parse_api_response(data: Mapping[str, Any], protocol: str) -> Tuple[str, Dict[str, Any]]:
    if not isinstance(data, Mapping):
        raise APIError("API 返回的 JSON 顶层不是对象。")
    if "error" in data and data["error"]:
        err = data["error"]
        message = err.get("message") if isinstance(err, Mapping) else str(err)
        raise APIError(f"API 返回错误：{redact_text(message)}")
    if protocol in ("openai_chat", "azure_openai_chat"):
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise APIError("Chat API 没有返回 choices。")
        first = choices[0] if isinstance(choices[0], Mapping) else {}
        finish = str(first.get("finish_reason") or "")
        if finish in {"length", "content_filter"}:
            raise APIError(f"Chat API 输出未完整完成：{finish}。")
        message = first.get("message") if isinstance(first.get("message"), Mapping) else {}
        if message.get("refusal"):
            raise APIError("Chat API 拒绝了该请求。")
        content = message.get("content", "")
        if isinstance(content, list):
            content = "".join(
                str(item.get("text", "")) for item in content if isinstance(item, Mapping) and item.get("type") in {"text", "output_text"}
            )
        text = str(content or "").strip()
    elif protocol == "openai_responses":
        status = str(data.get("status") or "completed")
        if status not in {"completed", "success", "succeeded"}:
            details = data.get("incomplete_details") or data.get("error") or status
            raise APIError(f"Responses API 未完整完成：{redact_text(details)}")
        if data.get("refusal"):
            raise APIError("Responses API 拒绝了该请求。")
        text = str(data.get("output_text") or "").strip()
        if not text:
            chunks: List[str] = []
            for output in data.get("output", []) if isinstance(data.get("output"), list) else []:
                if not isinstance(output, Mapping):
                    continue
                for item in output.get("content", []) if isinstance(output.get("content"), list) else []:
                    if not isinstance(item, Mapping):
                        continue
                    if item.get("type") == "refusal" or item.get("refusal"):
                        raise APIError("Responses API 拒绝了该请求。")
                    if item.get("type") in {"output_text", "text"}:
                        chunks.append(str(item.get("text") or ""))
            text = "".join(chunks).strip()
    else:
        raise ConfigurationError(f"不支持的 API 协议：{protocol}")
    if not text:
        raise APIError("API 返回了空文本。")
    return text, _usage(data)


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req: request.Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def _retry_delay(headers: Mapping[str, str], attempt: int) -> float:
    retry_after = headers.get("Retry-After", "") if headers else ""
    try:
        value = float(retry_after)
        return min(8.0, max(0.0, value))
    except (TypeError, ValueError):
        return min(8.0, (0.5 * (2**attempt)) + random.random() * 0.25)


def _can_retry_connection_failure(reason: Any) -> bool:
    if isinstance(reason, socket.gaierror):
        return True
    if isinstance(reason, ConnectionRefusedError):
        return True
    if isinstance(reason, OSError):
        return reason.errno in {errno.ECONNREFUSED, errno.EHOSTUNREACH, errno.ENETUNREACH}
    return False


class APIClient:
    def __init__(self, config: APIConfig, opener: Optional[Any] = None):
        self.config = config
        self.opener = opener or request.build_opener(_NoRedirect())

    def _headers(self, key: str) -> Dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "GiftMasterCreator/1.0.0"}
        if not self.config.no_auth:
            if self.config.protocol == "azure_openai_chat" and self.config.azure_auth == "api_key":
                headers["api-key"] = key
            else:
                headers["Authorization"] = f"Bearer {key}"
        return headers

    def _payload(
        self,
        system_prompt: str,
        user_prompt: str,
        image_data_urls: Sequence[str],
        settings: GenerationSettings,
    ) -> Dict[str, Any]:
        if image_data_urls and not self.config.supports_images:
            raise ConfigurationError("当前 API 配置已关闭图片能力，但任务包含参考图。")
        if not 1 <= int(settings.max_output_tokens) <= 65536:
            raise ConfigurationError("最大输出 token 必须在 1–65536 之间。")
        if self.config.protocol == "openai_responses":
            content: List[Dict[str, Any]] = [{"type": "input_text", "text": user_prompt}]
            content.extend({"type": "input_image", "image_url": url, "detail": settings.image_detail} for url in image_data_urls)
            payload: Dict[str, Any] = {
                "model": self.config.model,
                "instructions": system_prompt,
                "input": [{"role": "user", "content": content}],
                "max_output_tokens": int(settings.max_output_tokens),
            }
        else:
            user_content: Any = user_prompt
            if image_data_urls:
                user_content = [{"type": "text", "text": user_prompt}]
                user_content.extend(
                    {"type": "image_url", "image_url": {"url": url, "detail": settings.image_detail}} for url in image_data_urls
                )
            payload = {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
            }
            if self.config.protocol != "azure_openai_chat" or self.config.model.strip():
                payload["model"] = self.config.model.strip()
            token_name = settings.token_parameter
            if token_name == "auto":
                model = self.config.model.lower()
                token_name = "max_completion_tokens" if (model.startswith("gpt-5") or re.match(r"o\d", model)) else "max_tokens"
            if token_name not in {"max_tokens", "max_completion_tokens"}:
                raise ConfigurationError("token 参数只允许 auto、max_tokens 或 max_completion_tokens。")
            payload[token_name] = int(settings.max_output_tokens)
        for name in ("temperature", "top_p", "frequency_penalty", "presence_penalty", "seed"):
            value = getattr(settings, name)
            if value is not None:
                payload[name] = value
        return payload

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        image_data_urls: Sequence[str] = (),
        settings: Optional[GenerationSettings] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        cfg = self.config
        if not 10 <= int(cfg.timeout_seconds) <= 600:
            raise ConfigurationError("超时时间必须在 10–600 秒之间。")
        if not 0 <= int(cfg.retries) <= 3:
            raise ConfigurationError("重试次数必须在 0–3 之间。")
        effective_model = cfg.model.strip() or (cfg.azure_deployment.strip() if cfg.protocol == "azure_openai_chat" else "")
        if not effective_model:
            raise ConfigurationError("模型名称不能为空。")
        if cfg.protocol == "azure_openai_chat" and cfg.azure_auth not in {"api_key", "bearer"}:
            raise ConfigurationError("Azure 鉴权方式只允许 api_key 或 bearer。")
        endpoint = build_endpoint(cfg)
        key = _resolve_key(cfg, endpoint)
        if key and ("\r" in key or "\n" in key or len(key) > 8192):
            raise ConfigurationError("API 密钥格式无效。")
        chosen = settings or GenerationSettings()
        body = json.dumps(self._payload(system_prompt, user_prompt, image_data_urls, chosen), ensure_ascii=False).encode("utf-8")
        attempts = 0
        while True:
            attempts += 1
            req = request.Request(endpoint, data=body, headers=self._headers(key), method="POST")
            try:
                with self.opener.open(req, timeout=int(cfg.timeout_seconds)) as response:
                    raw = response.read(16 * 1024 * 1024 + 1)
                if len(raw) > 16 * 1024 * 1024:
                    raise APIError("API 响应超过 16 MiB 安全上限。")
                try:
                    data = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise APIError("API 返回的内容不是有效 JSON。") from exc
                try:
                    text, usage = parse_api_response(data, cfg.protocol)
                except APIError as exc:
                    raise APIError(redact_text(str(exc), (key,))) from None
                return text, {"protocol": cfg.protocol, "model": effective_model, "requests": attempts, "usage": usage}
            except error.HTTPError as exc:
                try:
                    detail = exc.read(4096).decode("utf-8", errors="replace")
                except Exception:
                    detail = str(exc.reason)
                headers = exc.headers
                exc.close()
                if exc.code in _RETRY_CODES and attempts <= cfg.retries:
                    time.sleep(_retry_delay(headers, attempts - 1))
                    continue
                raise APIError(f"API HTTP {exc.code}：{redact_text(detail, (key,))}") from exc
            except (socket.timeout, TimeoutError) as exc:
                raise APIError("API 请求超时；为避免重复计费，本次不自动重试。") from exc
            except error.URLError as exc:
                reason = exc.reason
                if isinstance(reason, (socket.timeout, TimeoutError)):
                    raise APIError("API 请求超时；为避免重复计费，本次不自动重试。") from exc
                if attempts <= cfg.retries and _can_retry_connection_failure(reason):
                    time.sleep(_retry_delay({}, attempts - 1))
                    continue
                raise APIError(f"无法连接 API：{redact_text(reason, (key,))}") from exc
            except (ConnectionError, OSError, http.client.HTTPException) as exc:
                if isinstance(exc, (socket.timeout, TimeoutError)):
                    raise APIError("API 请求超时；为避免重复计费，本次不自动重试。") from exc
                if attempts <= cfg.retries and _can_retry_connection_failure(exc):
                    time.sleep(_retry_delay({}, attempts - 1))
                    continue
                raise APIError(f"API 连接异常：{redact_text(exc, (key,))}") from exc


__all__ = [
    "APIClient",
    "APIConfig",
    "GenerationSettings",
    "build_endpoint",
    "build_request_url",
    "clear_session_keys",
    "parse_api_response",
    "redact_text",
    "store_session_key",
    "validate_api_url",
]
