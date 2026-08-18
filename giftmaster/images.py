"""Convert ComfyUI IMAGE tensors to privacy-transparent JPEG data URLs."""

from __future__ import annotations

import base64
from io import BytesIO
from typing import Any, Iterable, List, Sequence

from .errors import GiftMasterError


def _iter_batch(value: Any) -> Iterable[Any]:
    if value is None:
        return
    if isinstance(value, str):
        raise GiftMasterError("图片端口只接受 ComfyUI IMAGE，不能传入外部 data URL 字符串。")
    shape = getattr(value, "shape", None)
    if shape is not None and len(shape) == 4:
        for index in range(int(shape[0])):
            yield value[index]
    else:
        yield value


def flatten_image_inputs(inputs: Sequence[Any]) -> List[Any]:
    flattened: List[Any] = []
    for value in inputs:
        flattened.extend(_iter_batch(value))
    if len(flattened) > 9:
        raise GiftMasterError("最多只能向一个 GiftMaster 请求发送 9 张图片。")
    return flattened


def _to_pil(value: Any) -> Any:
    from PIL import Image
    import numpy as np

    if isinstance(value, Image.Image):
        image = value.copy()
    else:
        if hasattr(value, "detach"):
            value = value.detach().cpu().numpy()
        array = np.asarray(value)
        if array.ndim != 3 or array.shape[-1] not in (1, 3, 4):
            raise GiftMasterError("IMAGE 必须是 H×W×C 或 B×H×W×C。")
        if array.dtype != np.uint8:
            array = np.clip(array.astype(np.float32), 0.0, 1.0)
            array = (array * 255.0 + 0.5).astype(np.uint8)
        if array.shape[-1] == 1:
            array = array[:, :, 0]
        image = Image.fromarray(array)
    if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        background.alpha_composite(rgba)
        image = background.convert("RGB")
    else:
        image = image.convert("RGB")
    return image


def encode_image_data_urls(
    inputs: Sequence[Any],
    max_edge: int = 1024,
    jpeg_quality: int = 90,
) -> List[str]:
    if not 256 <= int(max_edge) <= 4096:
        raise GiftMasterError("图片最长边必须在 256–4096 像素之间。")
    if not 40 <= int(jpeg_quality) <= 100:
        raise GiftMasterError("JPEG 质量必须在 40–100 之间。")
    result: List[str] = []
    total_bytes = 0
    for value in flatten_image_inputs(inputs):
        image = _to_pil(value)
        if max(image.size) > max_edge:
            scale = max_edge / max(image.size)
            from PIL import Image

            image = image.resize(
                (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                Image.Resampling.LANCZOS,
            )
        output = BytesIO()
        image.save(output, format="JPEG", quality=int(jpeg_quality), optimize=True)
        encoded = base64.b64encode(output.getvalue()).decode("ascii")
        if len(encoded) > 12 * 1024 * 1024:
            raise GiftMasterError("单张编码图片超过 12 MiB 安全上限，请降低最长边或 JPEG 质量。")
        total_bytes += len(encoded)
        if total_bytes > 48 * 1024 * 1024:
            raise GiftMasterError("本次请求的图片总量超过 48 MiB 安全上限。")
        result.append("data:image/jpeg;base64," + encoded)
    return result


__all__ = ["encode_image_data_urls", "flatten_image_inputs"]
