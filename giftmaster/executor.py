"""Orchestrate deterministic Gift Skills through a user-selected API."""

from __future__ import annotations

import json
import math
import re
from typing import Any, Dict, Optional, Sequence, Tuple

from .api import APIClient, APIConfig, GenerationSettings
from .errors import GiftMasterError, ValidationError
from .h3 import ValidationResult, clean_h3_prompt, validate_h3_prompt
from .images import encode_image_data_urls
from .skills import load_skill, route_skill
from .tasks import parse_task_spec, validate_image_count, validate_task_spec


def _estimate_tokens(system_prompt: str, task: str, image_count: int, image_detail: str = "auto") -> int:
    combined = system_prompt + task
    cjk = len(re.findall(r"[\u3400-\u9fff\uf900-\ufaff]", combined))
    other = max(0, len(combined) - cjk)
    text_estimate = cjk + (other + 2) // 3
    image_tokens = {"low": 400, "auto": 1200, "high": 2000}.get(image_detail, 1200)
    return math.ceil(text_estimate * 1.25) + image_count * image_tokens + 512


def _merge_usage(total: Dict[str, Any], current: Any) -> Dict[str, Any]:
    merged = dict(total)
    if not isinstance(current, dict):
        return merged
    for key, value in current.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            merged[key] = merged.get(key, 0) + value if isinstance(merged.get(key, 0), (int, float)) else value
        elif key not in merged:
            merged[key] = value
    return merged


def _extract_artifact(raw: str, mode: str) -> Tuple[str, str]:
    cleaned = clean_h3_prompt(raw)
    first_field = "subject_definitions" if mode == "Ref2VA" else "integrated_multimodal_description"
    match = re.search(rf"(?m)^\s*{re.escape(first_field)}\s*:", cleaned)
    if match and match.start() > 0:
        prefix = cleaned[: match.start()].strip()
        if len(prefix) <= 500 and not re.search(r"(?m)^\s*(?:subject_definitions|integrated_multimodal_description)\s*:", prefix):
            if mode in {"I2VA", "FL2VA", "L2VA"}:
                lines = [line.strip() for line in prefix.splitlines() if line.strip()]
                for index, line in enumerate(lines):
                    if re.search(r"(?i)(?:<\s*)?Picture\s*1(?:\s*>)?", line) and re.search(
                        r"(?i)(align|target\s+video|0\.0|second|frame|对齐|首帧|尾帧|秒)", line
                    ):
                        notice = "\n".join(lines[:index]).strip()
                        artifact = "\n".join(lines[index:]) + "\n" + cleaned[match.start() :].strip()
                        return artifact.strip(), notice
                return cleaned, ""
            return cleaned[match.start() :].strip(), prefix
    return cleaned, ""


def _validate(prompt: str, task: str, image_count: int) -> ValidationResult:
    spec = parse_task_spec(task)
    validate_task_spec(spec)
    return validate_h3_prompt(
        prompt,
        mode=spec.mode,
        profile=spec.profile,
        gift_price=spec.gift_price,
        aspect_ratio=spec.aspect_ratio,
        image_count=image_count,
        duration=spec.duration,
    )


def run_skill_api(
    config: APIConfig,
    skill_selection: str,
    task: str,
    reference_policy: str = "auto",
    missing_information_policy: str = "reasonable_defaults",
    auto_validate: bool = True,
    repair_attempts: int = 1,
    settings: Optional[GenerationSettings] = None,
    image_inputs: Sequence[Any] = (),
    client: Optional[APIClient] = None,
) -> Tuple[str, str]:
    if not (task or "").strip():
        raise GiftMasterError("任务不能为空。")
    if "GMC_INPUT_ERROR" in task or "QWEN_TE_INPUT_ERROR" in task:
        raise GiftMasterError("上游任务构建器报告输入不完整，请先修正任务。")
    if missing_information_policy not in {"reasonable_defaults", "error", "合理默认", "缺失即报错"}:
        raise GiftMasterError("缺失信息策略无效。")
    if not 0 <= int(repair_attempts) <= 2:
        raise GiftMasterError("自动修复次数必须在 0–2 之间。")
    spec = parse_task_spec(task)
    validate_task_spec(spec)
    if missing_information_policy in {"error", "缺失即报错"} and spec.profile == "GENERIC":
        raise GiftMasterError("缺失即报错模式要求使用礼物任务构建器生成完整任务标记。")
    skill_id = route_skill(task, skill_selection)
    skill = load_skill(skill_id, reference_policy, spec.mode)
    if spec.profile not in {"GENERIC", skill.profile}:
        raise GiftMasterError(f"任务 profile {spec.profile} 与 Skill profile {skill.profile} 冲突。")
    selected_settings = settings or GenerationSettings()
    image_urls = encode_image_data_urls(
        image_inputs,
        max_edge=selected_settings.image_max_edge,
        jpeg_quality=selected_settings.jpeg_quality,
    )
    validate_image_count(spec.mode, len(image_urls))
    system_prompt = skill.system_prompt(selected_settings.extra_system_prompt)
    estimate = _estimate_tokens(system_prompt, task, len(image_urls), selected_settings.image_detail) + int(
        selected_settings.max_output_tokens
    )
    if estimate > int(config.context_window):
        raise GiftMasterError(
            f"预计上下文约 {estimate} tokens，超过配置的 {config.context_window}；请减少参考资料/图片或提高上下文配置。"
        )
    api = client or APIClient(config)
    raw, api_info = api.complete(system_prompt, task, image_urls, selected_settings)
    output, price_notice = _extract_artifact(raw, spec.mode)
    validation = _validate(output, task, len(image_urls)) if auto_validate else ValidationResult(output)
    repairs = 0
    total_requests = int(api_info.get("requests", 1))
    total_usage = _merge_usage({}, api_info.get("usage", {}))
    while auto_validate and not validation.valid and repairs < int(repair_attempts):
        repairs += 1
        repair_task = (
            "修复下面的 H3 提示词。保持创意语义，只修复列出的格式或硬约束错误；只返回完整修复结果。\n\n"
            + "错误：\n- "
            + "\n- ".join(validation.errors)
            + "\n\n原任务：\n"
            + task
            + "\n\n待修复提示词：\n"
            + output
        )
        repair_estimate = _estimate_tokens(system_prompt, repair_task, len(image_urls), selected_settings.image_detail) + int(
            selected_settings.max_output_tokens
        )
        if repair_estimate > int(config.context_window):
            break
        raw, repair_info = api.complete(system_prompt, repair_task, image_urls, selected_settings)
        total_requests += int(repair_info.get("requests", 1))
        output, extra_notice = _extract_artifact(raw, spec.mode)
        price_notice = price_notice or extra_notice
        validation = _validate(output, task, len(image_urls))
        total_usage = _merge_usage(total_usage, repair_info.get("usage", {}))
    if auto_validate and not validation.valid:
        raise ValidationError("H3 提示词校验失败：\n- " + "\n- ".join(validation.errors))
    report: Dict[str, Any] = {
        "skill_id": skill_id,
        "profile": spec.profile,
        "mode": spec.mode,
        "protocol": config.protocol,
        "model": api_info.get("model") or config.model or config.azure_deployment,
        "requests": total_requests,
        "repair_attempts": repairs,
        "validation_passed": validation.valid if auto_validate else None,
        "warnings": validation.warnings,
        "usage": total_usage,
    }
    if price_notice:
        report["price_effect_notice"] = price_notice
    return output, json.dumps(report, ensure_ascii=False, indent=2)


__all__ = ["run_skill_api"]
