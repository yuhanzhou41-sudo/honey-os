"""Pluggable OCR backends used by the targeted textbook collector.

Screenshots never leave the machine: they are read, transcribed and deleted by
the collector immediately afterwards.
"""

from __future__ import annotations

import base64
import shutil
from pathlib import Path
from typing import Any, Protocol

TRANSCRIBE_PROMPT = (
    "逐行转录图片中的中文正文，保持原有段落与标点。"
    "不要总结、不要翻译、不要补充图片没有的字。"
    "忽略页码、页眉页脚、水印、按钮文案（例如“下拉加载上一页”“上拉加载下一页”）。"
    "看不清的字用 [无法识别] 标记。只输出转录正文。"
)


class OcrUnavailable(RuntimeError):
    pass


class OcrEngine(Protocol):
    def recognize(self, image_path: Path) -> str: ...


def _mime_for(path: Path) -> str:
    suffix = path.suffix.lower()
    return {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(
        suffix, "image/png"
    )


class TesseractOcr:
    """Local OCR; only used when both pytesseract and the tesseract binary exist."""

    def __init__(self, lang: str = "chi_sim+eng"):
        self.lang = lang

    @staticmethod
    def available() -> bool:
        if shutil.which("tesseract") is None:
            return False
        try:
            import pytesseract  # noqa: F401
        except ImportError:
            return False
        return True

    def recognize(self, image_path: Path) -> str:
        try:
            import pytesseract
            from PIL import Image
        except ImportError as exc:
            raise OcrUnavailable("本机没有可用的 Tesseract OCR，请配置视觉模型或安装 tesseract。") from exc
        with Image.open(image_path) as image:
            return pytesseract.image_to_string(image, lang=self.lang)


class VisionOcr:
    """Transcribe a screenshot with the configured vision model."""

    def __init__(self, reply=None):
        self._reply = reply or _vision_reply

    def recognize(self, image_path: Path) -> str:
        data = Path(image_path).read_bytes()
        if not data:
            raise OcrUnavailable("截图内容为空，无法识别。")
        encoded = base64.b64encode(data).decode("ascii")
        content: list[dict[str, Any]] = [
            {"type": "text", "text": "请转录这一页教材正文。"},
            {"type": "image_url", "image_url": {"url": f"data:{_mime_for(Path(image_path))};base64,{encoded}"}},
        ]
        return str(self._reply(TRANSCRIBE_PROMPT, content) or "")


class NullOcr:
    def recognize(self, image_path: Path) -> str:
        raise OcrUnavailable("未配置 OCR 后端，无法把教材截图转成文本。")


def _vision_reply(system: str, content: list[dict[str, Any]]) -> str:
    from honeyos.agent.auxiliary_client import call_llm

    response = call_llm(
        task="vision",
        timeout=120,
        max_tokens=4000,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": content}],
    )
    return response.choices[0].message.content


def make_default_ocr() -> OcrEngine:
    if TesseractOcr.available():
        return TesseractOcr()
    try:
        from honeyos.agent.auxiliary_client import call_llm  # noqa: F401
    except Exception:
        return NullOcr()
    return VisionOcr()


class StaticOcr:
    """Deterministic OCR for tests and replays."""

    def __init__(self, pages: list[str]):
        self.pages = list(pages)
        self.calls = 0

    def recognize(self, image_path: Path) -> str:
        index = min(self.calls, len(self.pages) - 1) if self.pages else 0
        self.calls += 1
        if not self.pages:
            return ""
        return self.pages[index]
