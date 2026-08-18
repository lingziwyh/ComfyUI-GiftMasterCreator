# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Nothing yet.

## [1.1.0] - 2026-08-18

### Added

- Added the Chinese `GiftMaster · 通用礼物任务（99–3000）` node. It routes
  99–999-coin tasks to the low-price Skill and 1000–3000-coin tasks to the
  high-price Skill without an extra classifier request.
- Added separate `任务` and `Skill路由` outputs from the universal builder for
  direct connection to the corresponding API gift-director inputs, alongside
  the existing H3 frame-count and effective-duration outputs.
- Added progressive Chinese reference-image ports on the API gift director.
  The UI starts with `参考图 1` and reveals the next port as images are
  connected, up to `参考图 9`.
- Added `examples/workflows/universal-auto-t2va-api.json` for the recommended
  v1.1.0 workflow.

### Changed

- Localized GiftMaster node labels, inputs, outputs, choices, descriptions, and
  tooltips for a Chinese-first ComfyUI experience while retaining stable
  internal identifiers.
- Enforced the built-in low/high Skill boundary even when an imported generic
  task contains conflicting price and Skill markers.
- Kept the separate low-price builder, high-price builder, and Skill-loader
  nodes registered so existing workflows continue to load without migration.

## [1.0.1] - 2026-08-18

### Added

- Added the opt-in `bytedance_compat` Azure authentication mode for gateways
  that require `api-key`, Bearer authorization, and an `X-TT-LOGID` request ID
  together. No provider endpoint, deployment name, or credential is bundled.

## [1.0.0] - 2026-08-18

### Added

- First public release of the independently implemented API-only ComfyUI node
  package.
- User-configured OpenAI-compatible Chat Completions and Responses API access.
- Skill discovery, deterministic Skill selection, and single-run execution.
- Low-price and high-price live-gift task builders with fixed price, duration,
  aspect-ratio, shot, sound, and background contracts.
- Up to nine connected reference images for supported generation modes.
- H3-compatible prompt validation and zero-to-two-pass repair support.
- Origin-bound GiftMaster environment credentials and redacted error handling.
- Independently authored live-gift Skill profiles, tests, and example workflows.

### Security

- Excluded hard-coded credentials, private provider endpoints, and
  account-specific deployment identifiers.
- Excluded local Qwen, GGUF, llama.cpp, CUDA-wheel, and model-weight
  dependencies.

### Licensing

- Licensed original GiftMasterCreator code and documentation under MIT.
- Excluded source code from `comfyUI-llama-TE` and official MiniMax H3 Skill,
  guide, example, and model materials.
