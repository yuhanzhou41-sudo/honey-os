import json

import pytest

from honeyos.study import chat_reading


def test_large_documents_ask_for_scope_and_never_drop_unselected_sources(monkeypatch):
    monkeypatch.setattr(chat_reading, "DIRECT_CHAR_LIMIT", 12)
    one = ("first", "第一份", "choice1\nchoice2\nother")
    with pytest.raises(chat_reading.DocumentScopeRequired):
        chat_reading.prepare_chat_documents([one], "帮我找依据")
    assert "choice2" in chat_reading.prepare_chat_documents([one], "第2行")
    with pytest.raises(chat_reading.DocumentScopeRequired):
        chat_reading.prepare_chat_documents([one], "不要回复「不清楚，自动分批读取」")


def test_explicit_auto_reads_all_batches_including_last(monkeypatch):
    monkeypatch.setattr(chat_reading, "BATCH_CHARS", 8)
    seen = []

    def summarize(_, payload):
        text = json.loads(payload)["segments"][0]["text"]
        seen.append(text)
        return json.dumps({"summary": "detail", "evidence_ids": [1]})

    monkeypatch.setattr(chat_reading, "summarize_document_batch", summarize)
    result = chat_reading.prepare_chat_documents(
        [("a", "Doc A", "abcdefghijkl"), ("b", "Doc B", "source B")],
        "请提取关键点\n不清楚，自动分批读取",
    )
    assert seen == ["abcdefgh", "ijkl", "source B"]
    assert "Doc B" in result and "原文摘录：ijkl" in result
