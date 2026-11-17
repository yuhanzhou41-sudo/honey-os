"""Structured, loopback-only generation for lightweight Study features."""

import json
from threading import BoundedSemaphore
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from honeyos.routing.local_qwen import configured_qwen_endpoint


class LocalStudyModelUnavailable(ValueError):
    """The user can retry after starting the local model."""


class LocalStudyModelNotConfigured(LocalStudyModelUnavailable):
    """The endpoint needs setup before any local request can run."""


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_SLOT = BoundedSemaphore(1)


def generate_flashcard_candidates(system: str, content: str) -> str:
    return _generate(system, content, task="闪卡", max_tokens=500)


def generate_question_candidates(system: str, content: str) -> str:
    return _generate(system, content, task="模拟题", max_tokens=1800)


def generate_shadow_appraisal(system: str, content: str, *, schema: dict | None = None) -> str:
    return _generate(system, content, task="状态评估草稿", max_tokens=280, schema=schema)


def summarize_document_batch(system: str, content: str) -> str:
    return _generate(system, content, task="文档分批摘要", max_tokens=500)


def _generate(system: str, content: str, *, task: str, max_tokens: int, schema: dict | None = None) -> str:
    from honeyos.gateway.run import _load_gateway_config

    endpoint = configured_qwen_endpoint(_load_gateway_config())
    if not endpoint:
        raise LocalStudyModelNotConfigured(f"请先在模型设置里配置本机 Qwen，再生成{task}。")
    if not _SLOT.acquire(blocking=False):
        raise LocalStudyModelUnavailable("本机 Qwen 正在处理请求，请稍后重试。")
    url, model = endpoint
    try:
        # Prevent environment proxies or HTTP redirects from sending Study material off device.
        opener = build_opener(ProxyHandler({}), _NoRedirects())
        response_format = {"type": "json_object"}
        if schema is not None:
            response_format = {"type": "json_schema", "json_schema": {
                "name": "honey_turn_appraisal", "strict": True, "schema": schema,
            }}
        request = Request(url, headers={"Content-Type": "application/json"}, data=json.dumps({
            "model": model, "temperature": 0, "max_tokens": max_tokens, "stream": False,
            "response_format": response_format,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
        }, ensure_ascii=False).encode())
        with opener.open(request, timeout=100) as response:
            payload = json.loads(response.read(200000))
        result = payload["choices"][0]["message"]["content"]
        if not isinstance(result, str) or not result.strip():
            raise ValueError("empty Qwen output")
        return result
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, IndexError, KeyError, TypeError) as exc:
        raise LocalStudyModelUnavailable(f"本机 Qwen 暂时无法生成{task}，请确认 Launcher 中本地模型已就绪后重试。") from exc
    finally:
        _SLOT.release()
