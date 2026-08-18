"""ComfyUI node adapters for GiftMasterCreator."""

from __future__ import annotations

import json
from typing import Any, Dict, Tuple

from .giftmaster.api import (
    APIConfig,
    GenerationSettings,
    clear_session_key_slot,
    is_session_key_slot_configured,
    store_session_key_slot,
    validate_api_url,
)
from .giftmaster.errors import ValidationError
from .giftmaster.executor import run_skill_api
from .giftmaster.h3 import validate_h3_prompt
from .giftmaster.skills import available_skill_choices
from .giftmaster.tasks import build_high_coin_task, build_low_coin_task, build_universal_gift_task, parse_task_spec


_MODES = ["T2VA", "Ref2VA", "I2VA", "FL2VA", "L2VA"]


class GiftMasterAPIConfigNode:
    # Versioned bridge used by trusted companion extensions. Keeping the
    # bridge on the active ComfyUI node class avoids importing a second copy
    # of giftmaster.api (and therefore a second in-memory credential vault).
    GIFTMASTER_RUNTIME_API = {
        "abi_version": 2,
        "APIConfig": APIConfig,
        "store_session_key_slot": store_session_key_slot,
        "clear_session_key_slot": clear_session_key_slot,
        "is_session_key_slot_configured": is_session_key_slot_configured,
    }

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "protocol": (
                    ["openai_chat", "openai_responses", "azure_openai_chat"],
                    {"default": "openai_chat", "tooltip": "选择服务商使用的 API 协议。"},
                ),
                "base_url": (
                    "STRING",
                    {"default": "https://api.openai.com/v1", "tooltip": "填写 API 基础地址，也可填写完整的接口地址。"},
                ),
                "model": ("STRING", {"default": "", "tooltip": "填写服务商提供的模型 ID；Azure 可与部署名称相同。"}),
                "api_key_env": (
                    "STRING",
                    {"default": "GIFTMASTER_API_KEY", "tooltip": "这里只填写环境变量名称，不要直接粘贴密钥。变量名必须以 GIFTMASTER_ 开头。"},
                ),
                "no_auth": (
                    "BOOLEAN",
                    {"default": False, "label_on": "无需鉴权", "label_off": "需要鉴权", "tooltip": "仅无密钥的本地或可信服务开启。"},
                ),
                "timeout_seconds": (
                    "INT",
                    {"default": 120, "min": 10, "max": 600, "tooltip": "单次 API 请求最多等待的秒数。"},
                ),
                "retries": (
                    "INT",
                    {"default": 0, "min": 0, "max": 3, "tooltip": "只重试 429 限流和明确发生在连接前的失败；超时与 5xx 不会重放。"},
                ),
                "allow_insecure_http": (
                    "BOOLEAN",
                    {"default": False, "label_on": "允许", "label_off": "禁止", "tooltip": "只适用于无鉴权的局域网 HTTP 服务；带密钥的远程请求始终要求 HTTPS。"},
                ),
                "azure_deployment": ("STRING", {"default": "", "tooltip": "Azure 或兼容网关的部署名称；留空时回退使用模型名称。"}),
                "api_version": ("STRING", {"default": "2024-10-21", "tooltip": "Azure 接口的 api-version；非 Azure 协议会忽略。"}),
                "azure_auth": (
                    ["api_key", "bearer", "bytedance_compat"],
                    {"default": "api_key", "tooltip": "选择 Azure 鉴权头；字节兼容模式会同时发送 api-key、Bearer 和 X-TT-LOGID。"},
                ),
                "context_window": (
                    "INT",
                    {"default": 128000, "min": 8192, "max": 2000000, "tooltip": "用于发送前的上下文预算检查，不会修改远程模型的真实上限。"},
                ),
                "supports_images": (
                    "BOOLEAN",
                    {"default": True, "label_on": "支持图片", "label_off": "仅文本", "tooltip": "关闭后，包含参考图的任务会在请求前报错。"},
                ),
            }
        }

    RETURN_TYPES = ("GIFTMASTER_API_CONFIG",)
    RETURN_NAMES = ("API配置",)
    FUNCTION = "build"
    CATEGORY = "GiftMasterCreator/API"
    DESCRIPTION = "配置 GiftMasterCreator 使用的远程大模型 API。密钥通过受 origin 约束的环境变量读取。"
    OUTPUT_TOOLTIPS = ("可连接到“API 礼物导演”的安全 API 配置。",)

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
                "max_output_tokens": ("INT", {"default": 4096, "min": 256, "max": 65536, "tooltip": "允许模型返回的最大 Token 数。"}),
                "token_parameter": (
                    ["auto", "max_tokens", "max_completion_tokens"],
                    {"default": "auto", "tooltip": "自动选择通常最稳；特殊兼容接口可明确指定 Token 参数名。"},
                ),
                "enable_sampling": (
                    "BOOLEAN",
                    {"default": False, "label_on": "发送采样参数", "label_off": "使用服务默认值", "tooltip": "开启后才会发送 temperature 和 top_p。"},
                ),
                "temperature": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 2.0, "step": 0.05, "tooltip": "采样温度；只有开启采样参数时才发送。"}),
                "top_p": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "核采样范围；只有开启采样参数时才发送。"}),
                "image_detail": (["auto", "high", "low"], {"default": "auto", "tooltip": "参考图发送给多模态模型时使用的细节等级。"}),
                "image_max_edge": ("INT", {"default": 1024, "min": 256, "max": 4096, "tooltip": "发送前将参考图最长边限制到该像素值。"}),
                "jpeg_quality": ("INT", {"default": 90, "min": 40, "max": 100, "tooltip": "参考图转为 JPEG 时的质量。"}),
                "extra_system_prompt": ("STRING", {"default": "", "multiline": True, "tooltip": "附加到 Skill 系统指令末尾的自定义要求；通常留空。"}),
            }
        }

    RETURN_TYPES = ("GIFTMASTER_GENERATION_SETTINGS",)
    RETURN_NAMES = ("生成设置",)
    FUNCTION = "build"
    CATEGORY = "GiftMasterCreator/API"
    DESCRIPTION = "设置 API 输出长度、可选采样参数和参考图压缩方式。"
    OUTPUT_TOOLTIPS = ("可选连接到“API 礼物导演”的生成设置。",)

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
        return {"required": {"skill": (choices, {"default": "auto", "tooltip": "自动模式会读取任务中的价格和 Skill 标记，不会额外调用分类 API。"})}}

    RETURN_TYPES = ("GIFTMASTER_SKILL_SELECTION",)
    RETURN_NAMES = ("Skill选择",)
    FUNCTION = "load"
    CATEGORY = "GiftMasterCreator/Skill"
    DESCRIPTION = "手动选择礼物 Skill，或让任务价格与标记自动决定。通用任务构建器可直接输出 Skill 路由，无需此节点。"
    OUTPUT_TOOLTIPS = ("连接到“API 礼物导演”的 Skill 选择输入。",)

    def load(self, skill: str) -> Tuple[str]:
        return (skill,)


class GiftMasterLowCoinGiftTaskBuilderNode:
    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "gift_name": ("STRING", {"default": "", "multiline": False, "tooltip": "直播礼物名称，不能为空。"}),
                "gift_price": ("INT", {"default": 499, "min": 99, "max": 999, "tooltip": "99–299 抖币使用 73 帧；300–999 抖币使用 90 帧。"}),
                "creative_brief": ("STRING", {"default": "", "multiline": True, "tooltip": "描述主体、动作、风格、颜色与希望呈现的记忆点。"}),
                "reference_mode": (_MODES, {"default": "Ref2VA", "tooltip": "选择 H3 如何使用参考图；不同模式要求的图片数量不同。"}),
                "aspect_ratio": (["1:1", "4:3"], {"default": "1:1", "tooltip": "低价礼物只允许 1:1 或 4:3。"}),
                "extra_constraints": ("STRING", {"default": "", "multiline": True, "tooltip": "填写必须满足的额外限制；没有则留空。"}),
            }
        }

    RETURN_TYPES = ("STRING", "INT", "FLOAT")
    RETURN_NAMES = ("任务", "H3帧数", "实际时长")
    FUNCTION = "build"
    CATEGORY = "GiftMasterCreator/礼物任务"
    DESCRIPTION = "构建 99–999 抖币低价礼物任务：固定单镜头、静音和 3–4 秒价格档规则。"
    OUTPUT_TOOLTIPS = ("包含低价规则和 Skill 标记的完整任务。", "H3 对齐帧数。", "帧数对应的实际秒数。")

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
                "gift_name": ("STRING", {"default": "", "multiline": False, "tooltip": "直播礼物名称，不能为空。"}),
                "gift_price": ("INT", {"default": 2000, "min": 1000, "max": 3000, "tooltip": "价格用于约束视觉复杂度与自动镜头建议。"}),
                "creative_brief": ("STRING", {"default": "", "multiline": True, "tooltip": "描述主体、情节、视觉升级、高潮和结尾记忆点。"}),
                "reference_mode": (_MODES, {"default": "Ref2VA", "tooltip": "选择 H3 如何使用参考图；不同模式要求的图片数量不同。"}),
                "target_duration": ("FLOAT", {"default": 5.0, "min": 0.1, "max": 149.0, "step": 0.1, "tooltip": "期望秒数会向上对齐到 H3 的 5+17n 帧序列。"}),
                "aspect_ratio": (["1:1", "9:16", "16:9", "4:3", "3:4"], {"default": "1:1", "tooltip": "选择最终视频画幅。"}),
                "shot_structure": (["自动", "单镜头", "双镜头", "三镜头"], {"default": "自动", "tooltip": "自动模式会按价格档给出镜头规模建议。"}),
                "sound_design": ("STRING", {"default": "", "multiline": True, "tooltip": "填写环境音、音效与音乐要求；留空时两个音频字段均使用 N/A。"}),
                "extra_constraints": ("STRING", {"default": "", "multiline": True, "tooltip": "填写必须满足的额外限制；没有则留空。"}),
            }
        }

    RETURN_TYPES = ("STRING", "INT", "FLOAT")
    RETURN_NAMES = ("任务", "H3帧数", "实际时长")
    FUNCTION = "build"
    CATEGORY = "GiftMasterCreator/礼物任务"
    DESCRIPTION = "构建 1000–3000 抖币高价礼物任务，可设置时长、画幅、镜头结构与声音。"
    OUTPUT_TOOLTIPS = ("包含高价规则和 Skill 标记的完整任务。", "H3 对齐帧数。", "帧数对应的实际秒数。")

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


class GiftMasterGiftTaskBuilderNode:
    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "gift_name": ("STRING", {"default": "", "multiline": False, "tooltip": "直播礼物名称，不能为空。"}),
                "gift_price": (
                    "INT",
                    {
                        "default": 499,
                        "min": 99,
                        "max": 3000,
                        "tooltip": "按价格自动路由：99–999 使用低价 Skill，1000–3000 使用高价 Skill。",
                    },
                ),
                "creative_brief": (
                    "STRING",
                    {"default": "", "multiline": True, "tooltip": "描述主体、动作、风格、颜色、视觉升级和结尾记忆点。"},
                ),
                "reference_mode": (_MODES, {"default": "Ref2VA", "tooltip": "选择 H3 如何使用参考图；不同模式要求的图片数量不同。"}),
                "aspect_ratio": (
                    ["1:1", "4:3", "9:16", "16:9", "3:4"],
                    {"default": "1:1", "tooltip": "99–999 抖币只允许 1:1 或 4:3；1000–3000 抖币支持全部列出画幅。"},
                ),
                "target_duration": (
                    "FLOAT",
                    {
                        "default": 5.0,
                        "min": 0.1,
                        "max": 149.0,
                        "step": 0.1,
                        "tooltip": "仅 1000–3000 抖币任务使用；低价任务按价格固定为 73 或 90 帧。",
                    },
                ),
                "shot_structure": (
                    ["自动", "单镜头", "双镜头", "三镜头"],
                    {"default": "自动", "tooltip": "仅 1000–3000 抖币任务使用；低价任务始终为单镜头。"},
                ),
                "sound_design": (
                    "STRING",
                    {"default": "", "multiline": True, "tooltip": "仅 1000–3000 抖币任务使用；低价任务始终静音。"},
                ),
                "extra_constraints": (
                    "STRING",
                    {"default": "", "multiline": True, "tooltip": "填写必须满足的额外限制；没有则留空。"},
                ),
            }
        }

    RETURN_TYPES = ("STRING", "INT", "FLOAT", "GIFTMASTER_SKILL_SELECTION")
    RETURN_NAMES = ("任务", "H3帧数", "实际时长", "Skill路由")
    FUNCTION = "build"
    CATEGORY = "GiftMasterCreator/礼物任务"
    DESCRIPTION = "推荐使用的通用礼物任务构建器。根据 99–3000 抖币价格自动选择低价或高价 Skill，无需额外的 Skill 节点。"
    OUTPUT_TOOLTIPS = (
        "包含价格档规则与 Skill 标记的完整任务。",
        "H3 对齐帧数。",
        "帧数对应的实际秒数。",
        "已按价格确定的 Skill，可直接连接到“API 礼物导演”。",
    )

    def build(
        self,
        gift_name: str,
        gift_price: int,
        creative_brief: str,
        reference_mode: str,
        aspect_ratio: str,
        target_duration: float,
        shot_structure: str,
        sound_design: str,
        extra_constraints: str,
    ) -> Tuple[str, int, float, str]:
        return build_universal_gift_task(
            gift_name=gift_name,
            gift_price=gift_price,
            creative_brief=creative_brief,
            reference_mode=reference_mode,
            aspect_ratio=aspect_ratio,
            target_duration=target_duration,
            shot_structure=shot_structure,
            sound_design=sound_design,
            extra_constraints=extra_constraints,
        )


class GiftMasterAPISkillExecutorNode:
    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        optional = {
            "generation_settings": (
                "GIFTMASTER_GENERATION_SETTINGS",
                {"tooltip": "可选。连接“生成设置”节点；不连接时使用安全默认值。"},
            )
        }
        for index in range(1, 10):
            optional[f"image_{index}"] = (
                "IMAGE",
                {"tooltip": f"参考图 {index}。连接后会自动显示下一张图片接口，最多 9 张。"},
            )
        return {
            "required": {
                "api_config": ("GIFTMASTER_API_CONFIG", {"tooltip": "连接“API 配置”节点。"}),
                "skill_selection": (
                    "GIFTMASTER_SKILL_SELECTION",
                    {"tooltip": "连接通用任务构建器的“Skill路由”，或连接“礼物 Skill”节点。"},
                ),
                "task": (
                    "STRING",
                    {"default": "", "multiline": True, "forceInput": True, "tooltip": "连接礼物任务构建器输出的“任务”。"},
                ),
                "reference_policy": (
                    ["auto", "all", "none"],
                    {
                        "default": "auto",
                        "tooltip": "控制是否把 Skill 清单中的运行时文本资料加入系统提示词，不控制已连接图片；参考图始终按任务的 H3 模式处理。",
                    },
                ),
                "missing_information_policy": (
                    ["reasonable_defaults", "error"],
                    {"default": "reasonable_defaults", "tooltip": "信息不足时采用合理默认值，或直接停止并报错。"},
                ),
                "auto_validate": (
                    "BOOLEAN",
                    {"default": True, "label_on": "自动校验", "label_off": "不校验", "tooltip": "生成后自动检查 H3 格式和礼物规则。"},
                ),
                "repair_attempts": (
                    "INT",
                    {"default": 1, "min": 0, "max": 2, "tooltip": "校验失败后允许模型自动修复的次数；每次都会产生一次新 API 请求。"},
                ),
            },
            "optional": optional,
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("H3提示词", "运行信息")
    FUNCTION = "run"
    CATEGORY = "GiftMasterCreator/Skill"
    OUTPUT_NODE = True
    DESCRIPTION = "读取礼物 Skill、任务和参考图，通过远程多模态 API 生成并校验 MiniMax H3 导演提示词。参考图接口会从 1 个开始按连接自动增加，最多 9 个。"
    OUTPUT_TOOLTIPS = ("可直接用于 MiniMax H3 的最终导演提示词。", "包含路由、校验、修复与 Token 用量等运行信息。")

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
                "prompt": ("STRING", {"default": "", "multiline": True, "tooltip": "需要检查的 MiniMax H3 提示词。"}),
                "mode": (["auto", *_MODES], {"default": "auto", "tooltip": "自动识别，或明确指定 H3 的文字/参考图模式。"}),
                "profile": (
                    ["GENERIC", "LOW_COIN_GIFT", "LIVE_GIFT"],
                    {"default": "GENERIC", "tooltip": "选择通用 H3、99–999 抖币低价礼物或 1000–3000 抖币高价礼物规则。"},
                ),
                "gift_price": ("INT", {"default": 499, "min": 0, "max": 3000, "tooltip": "未连接任务时，用于选择对应价格档规则。"}),
                "aspect_ratio": (
                    ["", "1:1", "4:3", "9:16", "16:9", "3:4"],
                    {"default": "", "tooltip": "留空表示不额外检查画幅；连接任务时由任务标记覆盖。"},
                ),
                "image_count": ("INT", {"default": 0, "min": 0, "max": 9, "tooltip": "实际发送给视频模型的参考图数量。"}),
                "duration": ("FLOAT", {"default": 5.0, "min": 0.1, "max": 149.0, "tooltip": "未连接任务时，用于检查提示词中的有效时长。"}),
                "fail_on_error": (
                    "BOOLEAN",
                    {"default": False, "label_on": "失败即报错", "label_off": "仅输出报告", "tooltip": "开启后，校验不通过会中止工作流。"},
                ),
            },
            "optional": {
                "task": (
                    "STRING",
                    {"default": "", "multiline": True, "forceInput": True, "tooltip": "可选。连接任务后自动读取模式、价格、画幅和时长标记。"},
                )
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "BOOLEAN")
    RETURN_NAMES = ("规范化提示词", "校验报告", "是否通过")
    FUNCTION = "validate"
    CATEGORY = "GiftMasterCreator/校验"
    DESCRIPTION = "独立检查并规范化 MiniMax H3 提示词，可自动采用礼物任务中的规则标记。"
    OUTPUT_TOOLTIPS = ("清理后的 H3 提示词。", "包含错误与警告的 JSON 校验报告。", "全部硬性校验是否通过。")

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
    "GiftMaster_GiftTaskBuilder": GiftMasterGiftTaskBuilderNode,
    "GiftMaster_APISkillExecutor": GiftMasterAPISkillExecutorNode,
    "GiftMaster_H3PromptValidator": GiftMasterH3PromptValidatorNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GiftMaster_APIConfig": "GiftMaster · API 配置",
    "GiftMaster_GenerationSettings": "GiftMaster · 生成设置",
    "GiftMaster_SkillLoader": "GiftMaster · 礼物 Skill",
    "GiftMaster_LowCoinGiftTaskBuilder": "GiftMaster · 低价礼物任务（99–999）",
    "GiftMaster_HighCoinGiftTaskBuilder": "GiftMaster · 高价礼物任务（1000–3000）",
    "GiftMaster_GiftTaskBuilder": "GiftMaster · 通用礼物任务（99–3000）",
    "GiftMaster_APISkillExecutor": "GiftMaster · API 礼物导演",
    "GiftMaster_H3PromptValidator": "GiftMaster · H3 提示词校验",
}
