# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Nothing yet.

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
