import time
from pathlib import Path

from honeyos.study.repository import StudyRepository
from honeyos.study.review import StudyReview
from honeyos.study.service import StudyService
from honeyos.study.textbook import (
    SectionCache,
    TextbookService,
    locate_sections,
    parse_outline_from_text,
    parse_outline_from_ui_dump,
    parse_toc_from_ui_dump,
)
from honeyos.study.textbook.collector import SectionCollector, merge_screens
from honeyos.study.textbook.ocr import StaticOcr

TOC_DUMP = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node text="" bounds="[0,0][1080,1920]">
    <node text="第三章 循环系统疾病" bounds="[0,100][1080,150]" />
    <node text="第三节 周围血管及淋巴疾病" bounds="[0,200][1080,250]" />
    <node text="第四节 心力衰竭" bounds="[0,300][1080,350]" />
    <node text="第四章 呼吸系统疾病" bounds="[0,400][1080,450]" />
    <node text="第一节 肺炎" bounds="[0,500][1080,550]" />
  </node>
</hierarchy>
"""

PAGE_ONE = (
    "第三节 周围血管及淋巴疾病\n"
    "一、动脉疾病\n"
    "1.概述\n"
    "下肢动脉硬化性闭塞症多见于中老年人。"
)
PAGE_TWO = (
    "1.概述\n"
    "下肢动脉硬化性闭塞症多见于中老年人。\n"
    "2.诊断\n"
    "间歇性跛行是典型症状。"
)
PAGE_BOUNDARY = "第四章 呼吸系统疾病\n第一节 肺炎\n肺炎链球菌是常见病原体。"

UI_DUMP = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node text="icon第三节　周围血管及淋巴疾病" bounds="[40,100][1000,150]" />
  <node text="一、动脉疾病" bounds="[40,160][1000,200]" />
  <node text="（一）下肢动脉硬化性闭塞症" bounds="[40,210][1000,250]" />
  <node text="下肢动脉硬化性闭塞症多见于中老年人。" bounds="[40,260][1000,300]" />
  <node text="2.诊断" bounds="[40,310][1000,350]" />
  <node text="间歇性跛行是典型症状。" bounds="[40,360][1000,400]" />
  <node text="第四节 心力衰竭" bounds="[40,410][1000,450]" />
  <node text="心力衰竭是多数心血管病的终末阶段。" bounds="[40,460][1000,500]" />
  <node text="目录" bounds="[0,1800][1080,1900]" />
</hierarchy>
"""


class FakeBridge:
    def __init__(self):
        self.taps = []
        self.swipes = 0

    def dump_ui(self):
        return TOC_DUMP

    def tap(self, x, y):
        self.taps.append((x, y))

    def swipe(self, x1, y1, x2, y2, duration_ms=320):
        self.swipes += 1

    def screen_size(self):
        return (1080, 1920)

    def screencap(self, destination):
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        Path(destination).write_bytes(b"fake-png")
        return Path(destination)


def test_outline_parsing_locate_and_neighbours():
    outline = parse_outline_from_ui_dump(TOC_DUMP, book_id="neike", title="内科学")
    assert [item.title for item in outline.sections] == [
        "第三节 周围血管及淋巴疾病",
        "第四节 心力衰竭",
        "第一节 肺炎",
    ]
    assert outline.sections[0].chapter == "第三章 循环系统疾病"
    assert outline.sections[0].tap == (540, 225)

    hits = locate_sections("周围血管", outline)
    assert hits and hits[0][0].title == "第三节 周围血管及淋巴疾病"
    assert locate_sections("肺炎", outline)[0][0].title == "第一节 肺炎"
    assert locate_sections("糖尿病足", outline) == []

    stops = outline.next_titles(outline.sections[0].section_id)
    assert "第四节 心力衰竭" in stops and "第三章 循环系统疾病" in stops


def test_outline_from_text_requires_section_headings():
    outline = parse_outline_from_text("第一章 绪论\n第一节 概述\n第二节 检查", book_id="book")
    assert len(outline.sections) == 2
    assert outline.sections[1].sequence == 2


def test_merge_screens_drops_overlapping_lines():
    merged, overlap = merge_screens(["a", "b", "c"], ["b", "c", "d"], min_overlap=2)
    assert merged == ["d"] and overlap == 2
    merged, overlap = merge_screens(["a"], ["x", "y"], min_overlap=2)
    assert merged == ["x", "y"] and overlap == 0


def test_collector_stops_at_boundary_and_removes_screenshots(tmp_path):
    temp = tmp_path / "temp"
    outline = parse_outline_from_ui_dump(TOC_DUMP, book_id="neike")
    section = outline.sections[0]
    bridge = FakeBridge()
    collector = SectionCollector(
        bridge, StaticOcr([PAGE_ONE, PAGE_TWO, PAGE_BOUNDARY]), temp, settle_seconds=0, max_screens=10
    )
    result = collector.collect(outline, section)

    assert result.stop_reason == "boundary"
    assert result.text.count("1.概述") == 1
    assert "下肢动脉硬化性闭塞症多见于中老年人。" in result.text
    assert "间歇性跛行是典型症状。" in result.text
    assert "第四章 呼吸系统疾病" not in result.text
    assert result.screens == 3
    assert list(temp.glob("*.png")) == []
    assert bridge.taps == [(540, 225)]


def test_collector_reads_ui_text_without_screenshots(tmp_path):
    outline = parse_outline_from_ui_dump(TOC_DUMP, book_id="neike")
    section = outline.sections[0]

    class UiBridge(FakeBridge):
        def dump_ui(self):
            return UI_DUMP

    collector = SectionCollector(
        UiBridge(), StaticOcr([]), tmp_path / "temp", settle_seconds=0, max_screens=3
    )
    result = collector.collect(outline, section)

    assert result.mode == "ui_text" and result.anchored is True
    assert "下肢动脉硬化性闭塞症多见于中老年人。" in result.text
    assert "间歇性跛行是典型症状。" in result.text
    assert "心力衰竭是多数心血管病的终末阶段。" not in result.text
    assert list((tmp_path / "temp").glob("*")) == []


def _book_service(tmp_path, pages):
    study = StudyService(repository=StudyRepository(tmp_path / "home"))
    service = TextbookService(
        study,
        root=tmp_path / "textbook",
        bridge=FakeBridge(),
        ocr=StaticOcr(pages),
    )
    service.sync_outline_from_dump("neike", TOC_DUMP, title="内科学")
    return study, service


def test_collect_caches_once_and_indexes_resource(tmp_path):
    study, service = _book_service(tmp_path, [PAGE_ONE, PAGE_TWO, PAGE_BOUNDARY])
    outline = service.get_outline("neike")
    section = outline.sections[0]

    first = service.collect_section("neike", section.section_id)
    assert first["cached"] is False
    assert first["resource_id"].startswith("resource_")
    assert service.cache.has("neike", section.section_id)

    calls = service._collector  # noqa: SLF001 - ensure second call never re-opens the app
    second = service.collect_section("neike", section.section_id)
    assert second["cached"] is True
    assert second["text"] == first["text"]
    assert calls is not None

    content = study.get_resource_content(first["resource_id"])["extracted_text"]
    assert "间歇性跛行是典型症状。" in content
    assert study.repository.list_resources(resource_type="textbook")
    assert service.stats()["temp_bytes"] == 0


TOC_DRAWER = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node text="目录" bounds="[60,60][160,120]" />
  <node text="书签" bounds="[220,60][320,120]" />
  <node text="笔记" bounds="[400,60][500,120]" />
  <node text="第二部分 循环系统疾病" bounds="[63,300][480,352]" />
  <node text="第四章 循环系统疾病的体格检查" bounds="[63,360][480,412]" />
  <node text="第十七章 血管及淋巴系统疾病" bounds="[63,420][480,472]" />
</hierarchy>
"""


def test_parse_toc_drawer_records_chapters_without_sections():
    outline = parse_toc_from_ui_dump(TOC_DRAWER, book_id="renwei", title="循环系统疾病（第2版）")
    chapters = [item["title"] for item in outline.source["chapters"]]
    assert "第四章 循环系统疾病的体格检查" in chapters
    assert outline.sections == ()


def test_sync_outline_from_device_keeps_existing_sections(tmp_path):
    study = StudyService(repository=StudyRepository(tmp_path / "home"))
    service = TextbookService(study, root=tmp_path / "tb", bridge=FakeBridge(), ocr=StaticOcr([]))
    service.sync_outline_from_dump("neike", TOC_DUMP, title="循环系统疾病（第2版）")
    before = service.get_outline("neike")
    assert len(before.sections) == 3

    class TocBridge(FakeBridge):
        def open_toc(self):
            return TOC_DRAWER

    outline = service.sync_outline_from_device("neike", title="循环系统疾病（第2版）", bridge=TocBridge())
    assert len(outline.sections) == 3
    assert outline.source["chapters"]
    assert outline.sections[0].title == before.sections[0].title


def test_collect_opens_book_from_study_centre(tmp_path):
    study = StudyService(repository=StudyRepository(tmp_path / "home"))
    study_dump = (
        "<hierarchy><node text=\"学习中心\" bounds=\"[0,40][1080,120]\" />"
        "<node text=\"循环系统疾病（第2版）\" bounds=\"[100,900][900,980]\" /></hierarchy>"
    )

    class SequenceBridge(FakeBridge):
        def __init__(self):
            super().__init__()
            self.dumps = [study_dump, UI_DUMP, UI_DUMP]

        def dump_ui(self):
            return self.dumps.pop(0) if len(self.dumps) > 1 else self.dumps[0]

    service = TextbookService(study, root=tmp_path / "tb", bridge=SequenceBridge(), ocr=StaticOcr([]))
    service.sync_outline_from_dump("neike", TOC_DUMP, title="循环系统疾病（第2版）")
    section = service.get_outline("neike").sections[0]
    payload = service.collect_section("neike", section.section_id)

    assert payload["mode"] == "ui_text" and payload["anchored"] is True
    assert "间歇性跛行是典型症状。" in payload["text"]


def test_collect_by_title_registers_section_without_toc(tmp_path):
    study = StudyService(repository=StudyRepository(tmp_path / "home"))

    class UiBridge(FakeBridge):
        def dump_ui(self):
            return UI_DUMP

    service = TextbookService(study, root=tmp_path / "tb", bridge=UiBridge(), ocr=StaticOcr([]))
    payload = service.collect_by_title("renwei", "第三节 周围血管及淋巴疾病", chapter="第十七章 周围血管疾病")
    assert payload["mode"] == "ui_text"
    outline = service.get_outline("renwei")
    assert outline.sections[0].title == "第三节 周围血管及淋巴疾病"
    assert outline.sections[0].chapter == "第十七章 周围血管疾病"
    assert service.cache.has("renwei", outline.sections[0].section_id)


def test_cache_prune_respects_byte_budget(tmp_path):
    cache = SectionCache(tmp_path / "root", max_bytes=10000)
    body = "甲" * 40
    for index in range(3):
        cache.write(book_id="b", section_id=f"sec{index}", title=f"节{index}", path=[], text=body)
        time.sleep(0.01)
    cache.read("b", "sec2")

    result = cache.prune(max_bytes=len(body.encode("utf-8")) * 2 + 10)
    assert result["removed_sections"] == 1
    assert result["stats"]["sections"] == 2
    assert cache.has("b", "sec2") and not cache.has("b", "sec0")


def test_purge_temp_older_than_cutoff(tmp_path):
    cache = SectionCache(tmp_path / "root")
    cache.temp_dir.mkdir(parents=True)
    fresh = cache.temp_dir / "fresh.png"
    old = cache.temp_dir / "old.png"
    fresh.write_bytes(b"x")
    old.write_bytes(b"y")
    past = time.time() - 7200
    import os

    os.utime(old, (past, past))
    result = cache.purge_temp(older_than_seconds=3600)
    assert result["removed_files"] == 1
    assert fresh.exists() and not old.exists()


def test_release_after_review_removes_text_and_derivatives(tmp_path):
    study, service = _book_service(tmp_path, [PAGE_ONE, PAGE_TWO, PAGE_BOUNDARY])
    outline = service.get_outline("neike")
    section = outline.sections[0]
    payload = service.collect_section("neike", section.section_id)
    resource_id = payload["resource_id"]

    review = StudyReview(study)
    question_id = review.create_question({
        "resource_id": resource_id,
        "prompt": "下肢动脉硬化性闭塞症的典型症状是？",
        "options": ["间歇性跛行", "发热", "咳嗽"],
        "correct": 0,
        "explanation": "动脉供血不足导致行走后疼痛。",
        "excerpt": "间歇性跛行是典型症状。",
    })
    review.save_cards(resource_id, None, [{
        "front": "间歇性跛行的含义",
        "back": "行走后下肢疼痛，休息后缓解。",
        "excerpt": "间歇性跛行是典型症状。",
    }])
    assert review.list_questions() and review.list_cards() and question_id

    report = service.release_after_review("neike", [section.section_id])
    assert report["sections"] == 1
    assert report["resources"] == 1
    assert report["review"]["questions"] == 1
    assert not service.cache.has("neike", section.section_id)
    assert review.list_questions() == []
    assert review.list_cards() == []
    try:
        study.get_resource(resource_id)
    except KeyError:
        pass
    else:
        raise AssertionError("resource should be deleted after review release")
