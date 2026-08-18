# ComfyUI-GiftMasterCreator

GiftMasterCreator 是一套轻量的 ComfyUI 直播礼物创作组件：把礼物名称、价格、创意要求和参考图组织成可执行的 MiniMax H3 导演提示词。

它只走你自己配置的 API，不加载本地大语言模型，不需要 GGUF、mmproj、`llama.cpp`、CUDA 专用轮子或额外 Python 包。可以和原来的本地模型插件同时安装，节点 ID 不冲突。

## 能做什么

- 99–999 抖币：单次播放、3–4 秒产品档、单镜头、静音；99–499 抖币保持上游选定的纯色背景不变。
- 1000–3000 抖币：可设置时长、画幅、1–3 镜头和声音设计。
- 支持 T2VA、I2VA、FL2VA、L2VA、Ref2VA。
- 支持 OpenAI-compatible Chat Completions、OpenAI Responses API、Azure OpenAI Chat。
- 内置高低价两套礼物 Skill，按任务标记确定性路由，不多花一次 API 分类请求。
- 自动检查图片数量、H3 顶层字段、镜头切点、参考图编号和低价礼物硬规则；最多自动修复两次。

## 安装

进入 ComfyUI 的 `custom_nodes` 文件夹，执行：

```powershell
git clone https://github.com/lingziwyh/ComfyUI-GiftMasterCreator.git
```

然后重启 ComfyUI。项目没有额外依赖，通常不需要执行 `pip install`。

也可以把下载后的 `ComfyUI-GiftMasterCreator` 文件夹直接放进：

```text
ComfyUI/custom_nodes/ComfyUI-GiftMasterCreator
```

## 在 ComfyUI 中使用

右键画布，在 `GiftMasterCreator` 分类中添加以下节点：

1. `GiftMaster · API 配置`
2. `GiftMaster · 生成设置`（可选）
3. `GiftMaster · 礼物 Skill`
4. `GiftMaster · 低价礼物任务（99–999）` 或 `GiftMaster · 高价礼物任务（1000–3000）`
5. `GiftMaster · API 礼物导演`

连接方式：

```text
API 配置 ───────────────┐
礼物 Skill（auto）──────┼─→ API 礼物导演 ─→ H3提示词
礼物任务.任务 ──────────┤
生成设置（可选）────────┤
Load Image（按模式）────┘

礼物任务.H3帧数 ─────────→ 下游 H3 节点的 length
API 礼物导演.H3提示词 ───→ 下游 H3 节点的 prompt
```

参考图数量必须与模式一致：

| 模式 | 图片数 | 用途 |
|---|---:|---|
| T2VA | 0 | 纯文字生成 |
| I2VA | 1 | 精确首帧 |
| FL2VA | 2 | 图片1首帧、图片2尾帧 |
| L2VA | 1 | 精确尾帧 |
| Ref2VA | 1–9 | 普通参考图，按端口和批次顺序 |

可直接导入 [`examples/workflows/low-coin-t2va-api.json`](examples/workflows/low-coin-t2va-api.json) 查看最小工作流；高价参考图版本见 [`examples/workflows/high-coin-ref2va-api.json`](examples/workflows/high-coin-ref2va-api.json)。导入后填写自己的 API 地址与模型，并按下文设置专用环境变量密钥。高价示例中的 `example.png` 只是占位名，请在 `Load Image` 节点重新选择自己的图片。

## API 配置

### OpenAI-compatible Chat

- `protocol`: `openai_chat`
- `base_url`: 服务商的基础地址或完整 `/chat/completions` 地址
- `model`: 服务商提供的模型 ID
- `api_key_env`: 建议保留为 `GIFTMASTER_API_KEY`；只允许读取 `GIFTMASTER_` 开头的专用变量

### OpenAI Responses

- `protocol`: `openai_responses`
- 地址可以是基础地址或完整 `/responses` 地址

### Azure OpenAI Chat

- `protocol`: `azure_openai_chat`
- 填写自己的 Azure endpoint、deployment 和 API version
- 默认用 `api-key` 请求头，也可选择 Bearer
- 若兼容网关明确要求同时发送 `api-key`、Bearer 和 `X-TT-LOGID`，将
  `azure_auth` 设为 `bytedance_compat`。此模式不会内置服务地址、模型名称或密钥。
  当 `token_parameter` 为 `auto` 时，该兼容模式固定使用 `max_tokens`。

### 本地或局域网兼容服务

- `localhost` / `127.0.0.1` 可以直接使用 HTTP。
- 其他 HTTP 地址必须主动开启 `allow_insecure_http`，并且只能用于显式 `no_auth` 的服务。
- 任何带密钥的远程请求都强制 HTTPS；无鉴权的本地或可信局域网服务可开启 `no_auth`。

## 密钥与隐私

最安全的方式是用专用、origin 绑定的环境变量提供 API key。密钥变量必须以 `GIFTMASTER_` 开头，并同时设置同名的 `_ORIGIN` 变量。Windows PowerShell 示例：

```powershell
$env:GIFTMASTER_API_KEY="你的密钥"
$env:GIFTMASTER_API_KEY_ORIGIN="https://api.openai.com"
```

这种 `$env:` 写法只对当前 PowerShell 及其启动的程序生效；设置后要从同一个窗口启动 ComfyUI。若平时双击整合包启动器，可改为写入 Windows 当前用户环境变量：

```powershell
[Environment]::SetEnvironmentVariable("GIFTMASTER_API_KEY", "你的密钥", "User")
[Environment]::SetEnvironmentVariable("GIFTMASTER_API_KEY_ORIGIN", "https://api.openai.com", "User")
```

写入后完全退出并重新启动 ComfyUI（已有终端窗口也要重开）。

如果同一个密钥明确允许多个 origin，`_ORIGIN` 可以使用英文逗号分隔。origin 必须包含协议和主机，可带端口，但不能带路径或通配符。这个绑定不会写入工作流，可防止导入的工作流把环境变量密钥改发到另一台服务器、端口或明文协议。

公开节点刻意不提供“直接填写密钥”输入框，因为这类值会以明文进入 ComfyUI 工作流、历史记录和截图。请使用上面的专用环境变量；工作流 JSON 中只保存变量名，不保存密钥。

执行时，任务文本、Skill 指令、选定的 reference 和参考图片会发送到你填写的第三方 API。GiftMasterCreator 不包含遥测，也不把这些内容发送到其他地址。更多说明见 [SECURITY.md](SECURITY.md)。

网络重试默认关闭。若手动设置重试次数，组件只会自动重试明确的 429 限流和确定发生在连接建立前的失败；超时、408 和 5xx 不会自动重放，以避免重复生成或重复计费。

## H3 校验

API 礼物导演默认在返回前自动校验，并可修复一次。`GiftMaster · H3 提示词校验` 可以单独检查已有提示词；将礼物任务同时接入它，可以启用价格、画幅、时长等上下文规则。

低价礼物的稳定规则包括：

- 99–299 抖币：73 帧，约 3.04 秒。
- 300–999 抖币：90 帧，3.75 秒。
- 恰好一个连续镜头、全程静音、只允许 1:1 或 4:3。
- 99–499 抖币使用均匀纯色背景；颜色由上游选择，GiftMasterCreator 只要求背景全程保持不变。

## 自定义 Skill

额外 Skill 根目录可通过 `GIFTMASTER_SKILLS_PATHS` 设置，多个目录使用系统路径分隔符。每个 Skill 必须包含 `SKILL.md` 和 `giftmaster.json`。运行时只读取 manifest 明确列出的 UTF-8 文本 reference，不执行 Skill 目录中的脚本，也不允许路径越界。

## 开发与测试

```powershell
python -m unittest discover -s tests -v
```

测试不访问真实 API，不需要 GPU，也不需要安装 ComfyUI。项目的 ComfyUI Registry 元数据已写入 `pyproject.toml`；GitHub 发布和 Registry 发布是两个独立步骤。

## 许可与来源边界

本仓库采用 MIT 许可证。它是独立实现，不包含原本地模型插件的 Python 源码、模型文件、私有服务预设，也不分发第三方官方 H3 指南原文。ComfyUI 是外部依赖，不随本项目分发。详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
