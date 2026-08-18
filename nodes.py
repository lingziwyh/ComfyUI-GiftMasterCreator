"""ComfyUI node adapters for GiftMasterCreator."""

from __future__ import annotations

import json
from typing import Any, Dict, Tuple

from .giftmaster.api import APIConfig, GenerationSettings, validate_api_url
from .giftmaster.errors import ValidationError
from .giftmaster.executor import run_skill_api
from .giftmaster.h3 import validate_h3_prompt
from .giftmaster.skills import available_skill_choices
from .giftmaster.tasks import build_high_coin_task, build_low_coin_task, parse_task_spec


_MODES = ["T2VA", "Ref2VA", "I2VA", "FL2VA", "L2VA"]


class GiftMasterAPIConfigNode:
    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "protocol": (["openai_chat", "openai_responses", "azure_openai_chat"], {"default": "openai_chat"}),
                "base_url": ("STRING", {"default": "https://api.openai.com/v1"}),
                "model": ("STRING", {"default": ""}),
                "api_key_env": ("STRING", {"default": "GIFTMASTER_API_KEY"}),
                "no_auth": ("BOOLEAN", {"default": False}),
                "timeout_seconds": ("INT", {"default": 120, "min": 10, "max": 600}),
                "retries": ("INT", {"default": 0, "min": 0, "max": 3}),
                "allow_insecure_http": ("BOOLEAN", {"default": False}),
                "azure_deployment": ("STRING", {"default": ""}),
                "api_version": ("STRING", {"default": "2024-10-21"}),
                "azure_auth": (["api_key", "bearer", "bytedance_compat"], {"default": "api_key"}),
                "context_window": ("INT", {"default": 128000, "min": 8192, "max": 2000000}),
                "supports_images": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("GIFTMASTER_API_CONFIG",)
    RETURN_NAMES = ("API配置",)
    FUNCTION = "build"
    CATEGORY = "GiftMasterCreator/API"

    def build(
        self,
        protocol: str,
        base_url: str,
        model: str,
        api_key_env: str,
        no_auth: bool,
        timeout_seconds: int,
        retries: int,
        allow_insecure_http: bool,
        azure_deployment: str,
        api_version: str,
        azure_auth: str,
        context_window: int,
        supports_images: bool,
    ) -> Tuple[APIConfig]:
        validate_api_url(base_url, allow_insecure_http)
        return (
            APIConfig(
                protocol=protocol,
                base_url=base_url,
                model=model,
                api_key_env=api_key_env,
                no_auth=no_auth,
                timeout_seconds=timeout_seconds,
                retries=retries,
                allow_insecure_http=allow_insecure_http,
                azure_deployment=azure_deployment,
                api_version=api_version,
                azure_auth=azure_auth,
                context_window=context_window,
                supports_images=supports_images,
            ),
        )


class GiftMasterGenerationSettingsNode:
    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "max_output_tokens": ("INT", {"default": 4096, "min": 256, "max": 65536}),
                "token_parameter": (["auto", "max_tokens", "max_completion_tokens"], {"default": "auto"}),
                "enable_sampling": ("BOOLEAN", {"default": False}),
                "temperature": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 2.0, "step": 0.05}),
                "top_p": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05}),
                "image_detail": (["auto", "high", "low"], {"default": "auto"}),
                "image_max_edge": ("INT", {"default": 1024, "min": 256, "max": 4096}),
                "jpeg_quality": ("INT", {"default": 90, "min": 40, "max": 100}),
                "extra_system_prompt": ("STRING", {"default": "", "multiline": True}),
            }
        }

    RETURN_TYPES = ("GIFTMASTER_GENERATION_SETTINGS",)
    RETURN_NAMES = ("生成设置",)
    FUNCTION = "build"
    CATEGORY = "GiftMasterCreator/API"

    def build(
        self,
        max_output_tokens: int,
        token_parameter: str,
        enable_sampling: bool,
        temperature: float,
        top_p: float,
        image_detail: str,
        image_max_edge: int,
        jpeg_quality: int,
        extra_system_prompt: str,
    ) -> Tuple[GenerationSettings]:
        return (
            GenerationSettings(
                max_output_tokens=max_output_tokens,
                token_parameter=token_parameter,
                temperature=temperature if enable_sampling else None,
                top_p=top_p if enable_sampling else None,
                image_detail=image_detail,
                image_max_edge=image_max_edge,
                jpeg_quality=jpeg_quality,
                extra_system_prompt=extra_system_prompt,
            ),
        )


class GiftMasterSkillLoaderNode:
    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        try:
            choices = available_skill_choices()
        except Exception:
            choices = ["auto", "h3-low-coin-gift-director", "h3-live-gift-director"]
        return {"required": {"skill": (choices, {"default": "auto"})}}

    RETURN_TYPES = ("GIFTMASTER_SKILL_SELECTION",)
    RETURN_NAMES = ("Skill选择",)
    FUNCTION = "load"
    CATEGORY = "GiftMasterCreator/Skill"

    def load(self, skill: str) -> Tuple[str]:
        return (skill,)


class GiftMasterLowCoinGiftTaskBuilderNode:
    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "gift_name": ("STRING", {"default": "", "multiline": False}),
                "gift_price": ("INT", {"default": 499, "min": 99, "max": 999}),
                "creative_brief": ("STRING", {"default": "", "multiline": True}),
                "reference_mode": (_MODES, {"default": "Ref2VA"}),
                "aspect_ratio": (["1:1", "4:3"], {"default": "1:1"}),
                "extra_constraints": ("STRING", {"default": "", "multiline": True}),
            }
        }

    RETURN_TYPES = ("STRING", "INT", "FLOAT")
    RETURN_NAMES = ("任务", "H3帧数", "实际时长")
    FUNCTION = "build"
    CATEGORY = "GiftMasterCreator/礼物任务"

    def build(
        self,
        gift_name: str,
        gift_price: int,
        creative_brief: str,
        reference_mode: str,
        aspect_ratio: str,
        extra_constraints: str,
    ) -> Tuple[str, int, float]:
        return build_low_coin_task(gift_name, gift_price, creative_brief, reference_mode, aspect_ratio, extra_constraints)


class GiftMasterHighCoinGiftTaskBuilderNode:
    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "gift_name": ("STRING", {"default": "", "multiline": False}),
                "gift_price": ("INT", {"default": 2000, "min": 1000, "max": 3000}),
                "creative_brief": ("STRING", {"default": "", "multiline": True}),
                "reference_mode": (_MODES, {"default": "Ref2VA"}),
                "target_duration": ("FLOAT", {"default": 5.0, "min": 0.1, "max": 149.0, "step": 0.1}),
                "aspect_ratio": (["1:1", "9:16", "16:9", "4:3", "3:4"], {"default": "1:1"}),
                "shot_structure": (["自动", "单镜头", "双镜头", "三镜头"], {"default": "自动"}),
                "sound_design": ("STRING", {"default": "", "multiline": True}),
                "extra_constraints": ("STRING", {"default": "", "multiline": True}),
            }
        }

    RETURN_TYPES = ("STRING", "INT", "FLOAT")
    RETURN_NAMES = ("任务", "H3帧数", "实际时长")
    FUNCTION = "build"
    CATEGORY = "GiftMasterCreator/礼物任务"

    def build(
        self,
        gift_name: str,
        gift_price: int,
        creative_brief: str,
        reference_mode: str,
        target_duration: float,
        aspect_ratio: str,
        shot_structure: str,
        sound_design: str,
        extra_constraints: str,
    ) -> Tuple[str, int, float]:
        return build_high_coin_task(
            gift_name,
            gift_price,
            creative_brief,
            reference_mode,
            target_duration,
            aspect_ratio,
            shot_structure,
            sound_design,
            extra_constraints,
        )


class GiftMasterAPISkillExecutorNode:
    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        optional = {"generation_settings": ("GIFTMASTER_GENERATION_SETTINGS",)}
        for index in range(1, 10):
            optional[f"image_{index}"] = ("IMAGE",)
        return {
            "required": {
                "api_config": ("GIFTMASTER_API_CONFIG",),
                "skill_selection": ("GIFTMASTER_SKILL_SELECTION",),
                "task": ("STRING", {"default": "", "multiline": True, "forceInput": True}),
                "reference_policy": (["auto", "all", "none"], {"default": "auto"}),
                "missing_information_policy": (["reasonable_defaults", "error"], {"default": "reasonable_defaults"}),
                "auto_validate": ("BOOLEAN", {"default": True}),
                "repair_attempts": ("INT", {"default": 1, "min": 0, "max": 2}),
            },
            "optional": optional,
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("H3提示词", "运行信息")
    FUNCTION = "run"
    CATEGORY = "GiftMasterCreator/Skill"
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(cls, **kwargs: Any) -> float:
        return float("nan")

    def run(
        self,
        api_config: APIConfig,
        skill_selection: str,
        task: str,
        reference_policy: str,
        missing_information_policy: str,
        auto_validate: bool,
        repair_attempts: int,
        generation_settings: GenerationSettings = None,
        image_1: Any = None,
        image_2: Any = None,
        image_3: Any = None,
        image_4: Any = None,
        image_5: Any = None,
        image_6: Any = None,
        image_7: Any = None,
        image_8: Any = None,
        image_9: Any = None,
    ) -> Tuple[str, str]:
        images = [value for value in (image_1, image_2, image_3, image_4, image_5, image_6, image_7, image_8, image_9) if value is not None]
        return run_skill_api(
            config=api_config,
            skill_selection=skill_selection,
            task=task,
            reference_policy=reference_policy,
            missing_information_policy=missing_information_policy,
            auto_validate=auto_validate,
            repair_attempts=repair_attempts,
            settings=generation_settings,
            image_inputs=images,
        )


class GiftMasterH3PromptValidatorNode:
    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "prompt": ("STRING", {"default": "", "multiline": True}),
                "mode": (["auto", *_MODES], {"default": "auto"}),
                "profile": (["GENERIC", "LOW_COIN_GIFT", "LIVE_GIFT"], {"default": "GENERIC"}),
                "gift_price": ("INT", {"default": 499, "min": 0, "max": 3000}),
                "aspect_ratio": (["", "1:1", "4:3", "9:16", "16:9", "3:4"], {"default": ""}),
                "image_count": ("INT", {"default": 0, "min": 0, "max": 9}),
                "duration": ("FLOAT", {"default": 5.0, "min": 0.1, "max": 149.0}),
                "fail_on_error": ("BOOLEAN", {"default": False}),
            },
            "optional": {"task": ("STRING", {"default": "", "multiline": True, "forceInput": True})},
        }

    RETURN_TYPES = ("STRING", "STRING", "BOOLEAN")
    RETURN_NAMES = ("规范化提示词", "校验报告", "是否通过")
    FUNCTION = "validate"
    CATEGORY = "GiftMasterCreator/校验"

    def validate(
        self,
        prompt: str,
        mode: str,
        profile: str,
        gift_price: int,
        aspect_ratio: str,
        image_count: int,
        duration: float,
        fail_on_error: bool,
        task: str = "",
    ) -> Tuple[str, str, bool]:
        if task.strip():
            spec = parse_task_spec(task)
            mode = spec.mode
            profile = spec.profile
            gift_price = spec.gift_price if spec.gift_price is not None else gift_price
            aspect_ratio = spec.aspect_ratio
            duration = spec.duration
        result = validate_h3_prompt(
            prompt,
            mode=mode,
            profile=profile,
            gift_price=gift_price,
            aspect_ratio=aspect_ratio,
            image_count=image_count,
            duration=duration,
        )
        report = json.dumps(
            {"valid": result.valid, "detected_mode": result.detected_mode, "errors": result.errors, "warnings": result.warnings},
            ensure_ascii=False,
            indent=2,
        )
        if fail_on_error and not result.valid:
            raise ValidationError("H3 提示词校验失败：\n- " + "\n- ".join(result.errors))
        return result.cleaned, report, result.valid


NODE_CLASS_MAPPINGS = {
    "GiftMaster_APIConfig": GiftMasterAPIConfigNode,
    "GiftMaster_GenerationSettings": GiftMasterGenerationSettingsNode,
    "GiftMaster_SkillLoader": GiftMasterSkillLoaderNode,
    "GiftMaster_LowCoinGiftTaskBuilder": GiftMasterLowCoinGiftTaskBuilderNode,
    "GiftMaster_HighCoinGiftTaskBuilder": GiftMasterHighCoinGiftTaskBuilderNode,
    "GiftMaster_APISkillExecutor": GiftMasterAPISkillExecutorNode,
    "GiftMaster_H3PromptValidator": GiftMasterH3PromptValidatorNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GiftMaster_APIConfig": "GiftMaster · API 配置",
    "GiftMaster_GenerationSettings": "GiftMaster · 生成设置",
    "GiftMaster_SkillLoader": "GiftMaster · 礼物 Skill",
    "GiftMaster_LowCoinGiftTaskBuilder": "GiftMaster · 低价礼物任务（99–999）",
    "GiftMaster_HighCoinGiftTaskBuilder": "GiftMaster · 高价礼物任务（1000–3000）",
    "GiftMaster_APISkillExecutor": "GiftMaster · API 礼物导演",
    "GiftMaster_H3PromptValidator": "GiftMaster · H3 提示词校验",
}
