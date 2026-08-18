"""Small, independently written H3 prompt normalizer and validator."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Dict, Iterable, List, Optional, Tuple


BASE_FIELDS = (
    "integrated_multimodal_description",
    "overall_soundscape",
    "non_diegetic_music",
)
REF_FIELDS = (
    "subject_definitions",
    "summary",
    "retention_analysis",
    "detailed_description",
    "overall_soundscape",
    "non_diegetic_music",
)
REF_TASK_TYPES = {
    "keyframe completion",
    "reference generation",
    "video editing",
    "video continuation",
    "audio reuse",
    "audio reference",
}


@dataclass
class ValidationResult:
    cleaned: str
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    detected_mode: str = ""

    @property
    def valid(self) -> bool:
        return not self.errors

    def __iter__(self) -> Iterable[object]:
        yield self.cleaned
        yield self.errors
        yield self.warnings


def clean_h3_prompt(text: str) -> str:
    value = (text or "").replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n").strip()
    value = re.sub(r"(?is)<think>.*?</think>", "", value).strip()
    fence = re.fullmatch(r"```(?:text|markdown|md)?\s*\n?(.*?)\n?```", value, flags=re.I | re.S)
    if fence:
        value = fence.group(1).strip()
    value = re.sub(r"(?m)^\s*(?:[-*]\s*)?\*\*([a-z_]+)\*\*\s*:", r"\1:", value)
    value = re.sub(r"(?m)^\s*#{1,6}\s*([a-z_]+)\s*:?　?", r"\1: ", value)
    value = re.sub(r"(?m)^\s*(?:DONE|SUCCESS|完成)\s*$", "", value, flags=re.I)
    return value.strip()


def _field_positions(text: str, fields: Tuple[str, ...]) -> Dict[str, List[re.Match[str]]]:
    result: Dict[str, List[re.Match[str]]] = {}
    for name in fields:
        result[name] = list(re.finditer(rf"(?m)^\s*{re.escape(name)}\s*:\s*(.*)$", text))
    return result


def _field_value(text: str, name: str, all_names: Tuple[str, ...]) -> str:
    match = re.search(rf"(?m)^\s*{re.escape(name)}\s*:\s*(.*)$", text)
    if not match:
        return ""
    next_positions = []
    for candidate in all_names:
        if candidate == name:
            continue
        nxt = re.search(rf"(?m)^\s*{re.escape(candidate)}\s*:", text[match.end() :])
        if nxt:
            next_positions.append(match.end() + nxt.start())
    end = min(next_positions) if next_positions else len(text)
    return (match.group(1) + text[match.end() : end]).strip()


def detect_h3_mode(text: str) -> str:
    if re.search(r"(?m)^\s*subject_definitions\s*:", text):
        return "Ref2VA"
    first = text.splitlines()[0].strip() if text.splitlines() else ""
    if re.search(r"(?i)(?:<\s*)?picture\s*2(?:\s*>)?", first):
        return "FL2VA"
    if re.search(r"(?i)(?:<\s*)?picture\s*1(?:\s*>)?", first):
        if re.search(r"(?<!\d)0(?:\.0+)?(?:[- ]second|\s*秒)?", first, flags=re.I):
            return "I2VA"
        if re.search(r"(?i)(align|target\s+video|second|frame|尾帧|终点|秒)", first):
            return "L2VA"
    if re.search(r"(?i)(first\s*frame|首帧).*(last\s*frame|尾帧)", first):
        return "FL2VA"
    if re.search(r"(?i)(last\s*frame|尾帧)", first):
        return "L2VA"
    if re.search(r"(?i)(first\s*frame|首帧)", first):
        return "I2VA"
    return "T2VA"


def _validate_fields(text: str, fields: Tuple[str, ...], errors: List[str]) -> None:
    positions = _field_positions(text, fields)
    starts = []
    for name in fields:
        matches = positions[name]
        if not matches:
            errors.append(f"缺少字段 {name}。")
            continue
        if len(matches) > 1:
            errors.append(f"字段 {name} 重复出现。")
        starts.append((matches[0].start(), name))
        if not _field_value(text, name, fields):
            errors.append(f"字段 {name} 不能为空。")
    actual = [name for _, name in sorted(starts)]
    expected = [name for name in fields if positions[name]]
    if actual != expected:
        errors.append("顶层字段顺序不正确。")


def _validate_shots(text: str, duration: Optional[float], errors: List[str]) -> List[int]:
    matches = list(re.finditer(r"(?i)\[shot\s+(\d+)\]", text))
    if not matches:
        errors.append("缺少 [Shot 1]。")
        return []
    numbers = [int(m.group(1)) for m in matches]
    if numbers != list(range(1, len(numbers) + 1)):
        errors.append("镜头编号必须从 1 开始连续递增，且不得重复。")
    previous = 0.0
    for index, match in enumerate(matches):
        before = text[max(0, match.start() - 40) : match.start()]
        after = text[match.end() : match.end() + 40]
        before_time = re.search(r"(?i)at\s+(\d{2}):(\d{2}(?:\.\d{1,3})?)\s*[-—:]?\s*$", before)
        after_time = re.match(r"(?i)\s*[-—:]?\s*at\s+(\d{2}):(\d{2}(?:\.\d{1,3})?)", after)
        timing = before_time or after_time
        if index == 0:
            if timing is not None:
                errors.append("[Shot 1] 不能带切点。")
            continue
        if timing is None:
            errors.append(f"[Shot {index + 1}] 必须带 At MM:SS.mmm 切点。")
            continue
        seconds = int(timing.group(1)) * 60 + float(timing.group(2))
        if seconds <= previous:
            errors.append("镜头切点必须严格递增。")
        if duration is not None and seconds >= float(duration):
            errors.append("镜头切点必须早于视频终点。")
        previous = seconds
    return numbers


def _validate_reference_labels(text: str, image_count: Optional[int], errors: List[str], warnings: List[str]) -> None:
    definitions = _field_value(text, "subject_definitions", REF_FIELDS)
    label_pattern = r"<(?:Picture|Subject|Video|Audio)\s+-?\d+>"
    occurrences: Dict[int, str] = {}
    for pattern in (rf"(?im)^\s*({label_pattern})(?=\s|[:：])", rf"(?i)({label_pattern})\s*[:：]"):
        for match in re.finditer(pattern, definitions):
            occurrences[match.start(1)] = match.group(1)
    normalized_labels = [re.sub(r"\s+", " ", occurrences[position]) for position in sorted(occurrences)]
    defined_labels = set(normalized_labels)
    if not defined_labels:
        errors.append("subject_definitions 中没有可识别的引用标签。")
    duplicates = sorted(label for label in defined_labels if normalized_labels.count(label) > 1)
    if duplicates:
        errors.append("subject_definitions 中存在重复定义：" + "、".join(duplicates))
    invalid = sorted(
        {
            label
            for label in re.findall(label_pattern, text, flags=re.I)
            if int(re.search(r"-?\d+", label).group()) < 1
        }
    )
    if invalid:
        errors.append("引用标签编号必须从 1 开始：" + "、".join(invalid))
    without_definitions = text.replace(definitions, "", 1)
    used_labels = {re.sub(r"\s+", " ", label) for label in re.findall(label_pattern, without_definitions, flags=re.I)}
    unresolved = sorted(used_labels - defined_labels)
    if unresolved:
        errors.append("正文引用了未定义标签：" + "、".join(unresolved))
    unsupported = sorted(label for label in defined_labels if label.lower().startswith(("<video", "<audio")))
    if unsupported:
        errors.append("当前执行器只接收图片，不能定义 Video 或 Audio 资产：" + "、".join(unsupported))
    defined = {
        int(number)
        for label in defined_labels
        if (match := re.fullmatch(r"(?i)<Picture\s+(\d+)>", label))
        for number in (match.group(1),)
    }
    if image_count is not None:
        expected = set(range(1, image_count + 1))
        if defined - expected:
            errors.append("subject_definitions 引用了不存在的输入图片。")
        if expected - defined:
            errors.append("subject_definitions 未定义全部输入图片。")
    retention = _field_value(text, "retention_analysis", REF_FIELDS)
    allowed_relationships = {"fully_preserved", "partially_preserved", "attribute_transfer", "weak_reference"}
    for label in sorted(defined_labels):
        relationships = re.findall(rf"(?im)^\s*{re.escape(label)}(?:\s*\([^\n]*\))?\s*[:：]\s*([a-z_]+)\b", retention)
        if len(relationships) != 1:
            errors.append(f"retention_analysis 必须为 {label} 提供且只提供一条关系。")
        elif relationships[0] not in allowed_relationships:
            errors.append(f"{label} 使用了无效保留关系 {relationships[0]}。")
    summary = _field_value(text, "summary", REF_FIELDS)
    prefix = re.match(r"^\[([^\]]+)\]", summary)
    if not prefix:
        errors.append("summary 必须以方括号任务类型开头。")
    else:
        types = {item.strip().lower() for item in prefix.group(1).split("+")}
        unknown = sorted(types - REF_TASK_TYPES)
        if unknown:
            errors.append("summary 包含无效任务类型：" + "、".join(unknown))


def _validate_endpoint_header(
    text: str,
    mode: str,
    fields: Tuple[str, ...],
    duration: Optional[float],
    errors: List[str],
    warnings: List[str],
) -> None:
    positions = [matches[0].start() for name in fields if (matches := _field_positions(text, (name,))[name])]
    header = text[: min(positions)].strip() if positions else ""
    if mode == "T2VA":
        if header:
            errors.append("T2VA 必须直接从 integrated_multimodal_description 开始。")
        return
    if mode == "Ref2VA":
        if header:
            if re.search(r"(?i)(align|0\.00|first frame|last frame|首帧|尾帧)", header):
                errors.append("Ref2VA 不能包含精确首尾帧对齐首行。")
            else:
                warnings.append("Ref2VA 在 subject_definitions 前包含额外前言。")
        return
    if not header:
        errors.append(f"{mode} 缺少参考图片与目标视频的对齐首行。")
        return
    if not re.search(r"(?i)(?:<\s*)?Picture\s*1(?:\s*>)?", header):
        errors.append(f"{mode} 对齐首行必须引用 Picture 1。")
    if mode in {"I2VA", "FL2VA"} and not re.search(r"(?<!\d)0(?:\.0+)?(?:[- ]second|\s*秒)?", header, flags=re.I):
        errors.append(f"{mode} 对齐首行必须把 Picture 1 指定到 0.00 秒。")
    if mode == "FL2VA" and not re.search(r"(?i)(?:<\s*)?Picture\s*2(?:\s*>)?", header):
        errors.append("FL2VA 对齐首行必须引用 Picture 2。")
    if mode in {"FL2VA", "L2VA"}:
        if duration is None or duration <= 0:
            errors.append(f"{mode} 校验需要有效视频时长。")
        else:
            duration_tokens = {
                f"{float(duration):.2f}",
                f"{float(duration):.3f}",
                f"{float(duration):.6f}".rstrip("0").rstrip("."),
            }
            if not any(token in header for token in duration_tokens):
                errors.append(f"{mode} 对齐首行必须明确有效时长终点 {float(duration):.2f} 秒。")


def _validate_dialogue(text: str, errors: List[str]) -> None:
    opens = len(re.findall(r"<d(?:\s[^>]*)?>", text, flags=re.I))
    closes = len(re.findall(r"</d>", text, flags=re.I))
    if opens != closes:
        errors.append("<d> 对话标签未成对闭合。")
    for content in re.findall(r"<d(?:\s[^>]*)?>(.*?)</d>", text, flags=re.I | re.S):
        if not re.match(r"\s*\[[^\]]+\]", content):
            errors.append("对话内容必须以 [Language] 标记开头。")


def _validate_low_coin(
    text: str,
    price: Optional[int],
    aspect_ratio: str,
    shot_numbers: List[int],
    errors: List[str],
) -> None:
    if shot_numbers != [1]:
        errors.append("低价礼物必须是单镜头，[Shot 1] 必须恰好出现一次。")
    if re.search(r"(?i)(cut(?:s|ting)?\s+to|smash\s+cut|match\s+cut|hard\s+cut|transition|切镜|切换镜头|转场|镜头二|第二镜头)", text):
        errors.append("低价礼物禁止切镜或转场语言。")
    fields = BASE_FIELDS if not re.search(r"(?m)^\s*subject_definitions\s*:", text) else REF_FIELDS
    if _field_value(text, "overall_soundscape", fields).strip() != "N/A":
        errors.append("低价礼物 overall_soundscape 必须严格为 N/A。")
    if _field_value(text, "non_diegetic_music", fields).strip() != "N/A":
        errors.append("低价礼物 non_diegetic_music 必须严格为 N/A。")
    if re.search(r"(?i)<d(?:\s|>)|<Audio\s+\d+>|\(S\d+\)", text):
        errors.append("低价礼物必须静音，不能包含对话、音频或说话人标签。")
    if aspect_ratio and aspect_ratio not in text:
        errors.append(f"低价礼物提示词必须明确画幅 {aspect_ratio}。")
    if price is not None and price <= 499:
        solid = re.search(r"(均匀)?纯色背景|uniform\s+solid(?:-color)?\s+background", text, flags=re.I)
        stable = re.search(r"(全程|始终).{0,20}(保持不变|不变化|稳定)|remain(?:s|ing)?\s+unchanged", text, flags=re.I)
        if not solid:
            errors.append("99–499 抖币礼物必须明确使用均匀纯色背景。")
        if not stable:
            errors.append("99–499 抖币礼物必须明确纯色背景全程保持不变。")


def validate_h3_prompt(
    prompt: str,
    mode: str = "auto",
    profile: str = "GENERIC",
    gift_price: Optional[int] = None,
    aspect_ratio: str = "",
    image_count: Optional[int] = None,
    duration: Optional[float] = None,
) -> ValidationResult:
    cleaned = clean_h3_prompt(prompt)
    errors: List[str] = []
    warnings: List[str] = []
    detected = detect_h3_mode(cleaned)
    selected = detected if mode in ("", "auto", "AUTO") else mode
    if selected not in {"T2VA", "I2VA", "FL2VA", "L2VA", "Ref2VA"}:
        errors.append(f"未知 H3 模式：{selected}")
        return ValidationResult(cleaned, errors, warnings, detected)
    if not cleaned:
        errors.append("API 返回了空提示词。")
        return ValidationResult(cleaned, errors, warnings, detected)
    if "--wm false" in cleaned.lower():
        errors.append("提示词不能包含 --wm false。")
    if selected != detected and not (selected in ("I2VA", "FL2VA", "L2VA") and detected == "T2VA"):
        errors.append(f"输出格式看起来是 {detected}，但任务要求 {selected}。")
    fields = REF_FIELDS if selected == "Ref2VA" else BASE_FIELDS
    other_fields = BASE_FIELDS if fields == REF_FIELDS else REF_FIELDS
    _validate_fields(cleaned, fields, errors)
    _validate_endpoint_header(cleaned, selected, fields, duration, errors, warnings)
    for extra in other_fields:
        if extra not in fields and re.search(rf"(?m)^\s*{re.escape(extra)}\s*:", cleaned):
            errors.append(f"当前模式不应包含字段 {extra}。")
    shot_numbers = _validate_shots(cleaned, duration, errors)
    _validate_dialogue(cleaned, errors)
    if selected == "Ref2VA":
        _validate_reference_labels(cleaned, image_count, errors, warnings)
    if profile.upper() == "LOW_COIN_GIFT":
        _validate_low_coin(cleaned, gift_price, aspect_ratio, shot_numbers, errors)
    return ValidationResult(cleaned, errors, warnings, detected)
