"""Gift task builders and versioned task-marker parsing."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Dict, Optional, Tuple

from .errors import GiftMasterError


MODES = ("T2VA", "I2VA", "FL2VA", "L2VA", "Ref2VA")
LOW_SKILL_ID = "h3-low-coin-gift-director"
HIGH_SKILL_ID = "h3-live-gift-director"
_MARKER_RE = re.compile(r"^\[(?:GMC|GIFTMASTER|QWEN_TE)_([A-Z0-9_]+)=([^\]\r\n]+)\]$", re.MULTILINE | re.I)


@dataclass(frozen=True)
class GiftTaskSpec:
    schema: int = 1
    profile: str = "GENERIC"
    skill_id: str = ""
    mode: str = "T2VA"
    duration: float = 5.0
    gift_price: Optional[int] = None
    aspect_ratio: str = "1:1"
    frames: Optional[int] = None


def align_h3_frames(seconds: float) -> Tuple[int, float]:
    """Round upward to H3's 5+17n frame sequence at 24 fps."""
    if not 0.1 <= float(seconds) <= 149.0:
        raise GiftMasterError("目标时长必须在 0.1–149 秒之间。")
    requested = math.ceil(float(seconds) * 24.0 - 1e-9)
    n = max(0, math.ceil((requested - 5) / 17.0))
    frames = 5 + 17 * n
    return frames, frames / 24.0


def validate_image_count(mode: str, count: int) -> None:
    if mode not in MODES:
        raise GiftMasterError(f"未知 H3 模式：{mode}")
    expected = {
        "T2VA": (0, 0),
        "I2VA": (1, 1),
        "FL2VA": (2, 2),
        "L2VA": (1, 1),
        "Ref2VA": (1, 9),
    }[mode]
    if not expected[0] <= count <= expected[1]:
        wanted = str(expected[0]) if expected[0] == expected[1] else f"{expected[0]}–{expected[1]}"
        raise GiftMasterError(f"{mode} 需要 {wanted} 张图片，当前收到 {count} 张。")


def _mode_from_reference(reference_mode: str) -> str:
    aliases = {
        "无参考图（T2VA）": "T2VA",
        "普通参考图（Ref2VA）": "Ref2VA",
        "精确首帧（I2VA）": "I2VA",
        "精确首尾帧（FL2VA）": "FL2VA",
        "精确尾帧（L2VA）": "L2VA",
    }
    value = aliases.get(reference_mode, reference_mode)
    if value not in MODES:
        raise GiftMasterError(f"不支持的参考图用途：{reference_mode}")
    return value


def _markers(spec: GiftTaskSpec) -> str:
    values = [
        ("TASK_SCHEMA", str(spec.schema)),
        ("PROFILE", spec.profile),
        ("SKILL_ID", spec.skill_id),
        ("H3_MODE", spec.mode),
        ("H3_DURATION", f"{spec.duration:.6f}".rstrip("0").rstrip(".")),
        ("ASPECT", spec.aspect_ratio),
    ]
    if spec.gift_price is not None:
        values.append(("GIFT_PRICE", str(spec.gift_price)))
    if spec.frames is not None:
        values.append(("H3_FRAMES", str(spec.frames)))
    return "\n".join(f"[GMC_{key}={value}]" for key, value in values)


def build_low_coin_task(
    gift_name: str,
    gift_price: int = 499,
    creative_brief: str = "",
    reference_mode: str = "Ref2VA",
    aspect_ratio: str = "1:1",
    extra_constraints: str = "",
) -> Tuple[str, int, float]:
    if not (gift_name or "").strip():
        raise GiftMasterError("礼物名称不能为空。")
    price = int(gift_price)
    if not 99 <= price <= 999:
        raise GiftMasterError("低价礼物价格必须在 99–999 抖币之间。")
    if aspect_ratio not in ("1:1", "4:3"):
        raise GiftMasterError("低价礼物画幅只允许 1:1 或 4:3。")
    mode = _mode_from_reference(reference_mode)
    frames = 73 if price <= 299 else 90
    duration = frames / 24.0
    spec = GiftTaskSpec(
        profile="LOW_COIN_GIFT",
        skill_id=LOW_SKILL_ID,
        mode=mode,
        duration=duration,
        gift_price=price,
        aspect_ratio=aspect_ratio,
        frames=frames,
    )
    if price <= 499 and mode == "T2VA":
        background = "使用均匀纯色背景，但不规定具体颜色或色值；颜色一旦选定，背景颜色、亮度和覆盖范围全程保持不变。"
    elif price <= 499:
        background = "保持上游参考图已选定的均匀纯色背景全程不变；不指定、不替换其颜色或色值。"
    else:
        background = "背景可采用简洁小场景或均匀纯色背景，但必须服务于主体识别。"
    endpoint_note = {
        "T2VA": "无参考图，直接从文字创作。",
        "I2VA": "图片1是必须精确匹配的视频首帧。",
        "FL2VA": "图片1是精确首帧，图片2是精确尾帧，顺序不可交换。",
        "L2VA": "图片1是必须在有效时长终点精确匹配的尾帧。",
        "Ref2VA": "按输入顺序使用1–9张普通参考图，清楚定义每张图的保留要素。",
    }[mode]
    body = f"""{_markers(spec)}
请为单次播放的抖音直播礼物编写可直接使用的英文 MiniMax H3 导演提示词；保留用户提供的可见文字原语言。
礼物名称：{gift_name.strip()}
礼物价格：{price} 抖币
创作要求：{creative_brief.strip() or '围绕礼物名称设计清晰、完整、可执行的动效。'}
硬约束：有效时长 {duration:.6f} 秒（{frames} 帧/24fps）；{aspect_ratio}；恰好一个连续镜头；全程静音；单次播放，不设计连击或循环。
动作结构：在一个镜头内完成进入、核心展示或动作、退场；精确首尾帧要求优先于通用进退场建议。
背景要求：{background}
参考模式：{endpoint_note}
额外约束：{extra_constraints.strip() or '无'}
输出只包含最终 H3 提示词，不解释过程。"""
    return body, frames, duration


def build_high_coin_task(
    gift_name: str,
    gift_price: int = 2000,
    creative_brief: str = "",
    reference_mode: str = "Ref2VA",
    target_duration: float = 5.0,
    aspect_ratio: str = "1:1",
    shot_structure: str = "自动",
    sound_design: str = "",
    extra_constraints: str = "",
) -> Tuple[str, int, float]:
    if not (gift_name or "").strip():
        raise GiftMasterError("礼物名称不能为空。")
    price = int(gift_price)
    if not 1000 <= price <= 3000:
        raise GiftMasterError("高价礼物价格必须在 1000–3000 抖币之间。")
    if aspect_ratio not in ("1:1", "9:16", "16:9", "4:3", "3:4"):
        raise GiftMasterError("高价礼物画幅不受支持。")
    mode = _mode_from_reference(reference_mode)
    frames, duration = align_h3_frames(float(target_duration))
    shot_aliases = {
        "auto": "自动",
        "single": "单镜头",
        "double": "双镜头",
        "triple": "三镜头",
        "1": "单镜头",
        "2": "双镜头",
        "3": "三镜头",
    }
    shots = shot_aliases.get(str(shot_structure).strip().lower(), shot_structure)
    if shots not in ("自动", "单镜头", "双镜头", "三镜头"):
        raise GiftMasterError("镜头结构只允许自动、单镜头、双镜头或三镜头。")
    if shots == "自动":
        shots = "单镜头" if price <= 1499 else ("一至双镜头" if price <= 2199 else "双镜头，必要时三镜头")
    spec = GiftTaskSpec(
        profile="LIVE_GIFT",
        skill_id=HIGH_SKILL_ID,
        mode=mode,
        duration=duration,
        gift_price=price,
        aspect_ratio=aspect_ratio,
        frames=frames,
    )
    audio = sound_design.strip() or "N/A；两个音频字段都写 N/A"
    body = f"""{_markers(spec)}
请为单次播放的抖音直播礼物编写可直接使用的英文 MiniMax H3 导演提示词；保留用户提供的对白、歌词和可见文字原语言。
礼物名称：{gift_name.strip()}
礼物价格：{price} 抖币
创作要求：{creative_brief.strip() or '建立清晰的视觉升级、高潮和收束。'}
有效时长：{duration:.6f} 秒（{frames} 帧/24fps）；目标画幅：{aspect_ratio}。
镜头结构：{shots}。多镜头时保持主体和物理过程连续，并让镜头信息有推进。
参考模式：{mode}；T2VA使用0图，I2VA/L2VA使用1图，FL2VA按首帧、尾帧使用2图，Ref2VA使用1–9图。
声音：{audio}
额外约束：{extra_constraints.strip() or '无'}
输出只包含最终 H3 提示词，不解释过程。"""
    return body, frames, duration


def parse_task_markers(task: str) -> Dict[str, str]:
    found: Dict[str, str] = {}
    for key, value in _MARKER_RE.findall(task or ""):
        key = key.upper()
        canonical = {
            "GIFT_PROFILE": "PROFILE",
            "PROFILE": "PROFILE",
            "MODE": "H3_MODE",
            "DURATION": "H3_DURATION",
            "PRICE": "GIFT_PRICE",
        }.get(key, key)
        value = value.strip()
        if canonical in found and found[canonical] != value:
            raise GiftMasterError(f"任务中存在冲突标记：{canonical}")
        found[canonical] = value
    return found


def parse_task_spec(task: str) -> GiftTaskSpec:
    m = parse_task_markers(task)
    try:
        mode = m.get("H3_MODE", "T2VA")
        if mode not in MODES:
            raise ValueError("mode")
        return GiftTaskSpec(
            schema=int(m.get("TASK_SCHEMA", "1")),
            profile=m.get("PROFILE", "GENERIC"),
            skill_id=m.get("SKILL_ID", ""),
            mode=mode,
            duration=float(m.get("H3_DURATION", "5")),
            gift_price=int(m["GIFT_PRICE"]) if "GIFT_PRICE" in m else None,
            aspect_ratio=m.get("ASPECT", "1:1"),
            frames=int(m["H3_FRAMES"]) if "H3_FRAMES" in m else None,
        )
    except (TypeError, ValueError) as exc:
        raise GiftMasterError("任务标记格式无效。") from exc


def validate_task_spec(spec: GiftTaskSpec) -> None:
    if spec.mode not in MODES:
        raise GiftMasterError(f"未知 H3 模式：{spec.mode}")
    if not 0.1 <= float(spec.duration) <= 149.0:
        raise GiftMasterError("任务中的有效时长必须在 0.1–149 秒之间。")
    if spec.profile == "LOW_COIN_GIFT":
        if spec.gift_price is None or not 99 <= spec.gift_price <= 999:
            raise GiftMasterError("LOW_COIN_GIFT 任务必须包含 99–999 抖币价格。")
        if spec.aspect_ratio not in {"1:1", "4:3"}:
            raise GiftMasterError("LOW_COIN_GIFT 任务画幅只允许 1:1 或 4:3。")
        expected_frames = 73 if spec.gift_price <= 299 else 90
        if spec.frames is not None and spec.frames != expected_frames:
            raise GiftMasterError(f"低价任务帧数应为 {expected_frames}，但标记为 {spec.frames}。")
        if abs(spec.duration - expected_frames / 24.0) > 0.001:
            raise GiftMasterError("低价任务的有效时长与价格档不一致。")
    elif spec.profile == "LIVE_GIFT":
        if spec.gift_price is None or not 1000 <= spec.gift_price <= 3000:
            raise GiftMasterError("LIVE_GIFT 任务必须包含 1000–3000 抖币价格。")
        if spec.aspect_ratio not in {"1:1", "9:16", "16:9", "4:3", "3:4"}:
            raise GiftMasterError("LIVE_GIFT 任务画幅不受支持。")


check_image_count = validate_image_count
