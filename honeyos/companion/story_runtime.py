"""Isolated, local-first Story Mode runtime for HoneyOS."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _clean(value: object, *, limit: int = 2000) -> str:
    return " ".join(str(value or "").replace("\x00", "").split()).strip()[:limit]


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _identifier(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _json_object(raw: str) -> dict[str, Any]:
    cleaned = str(raw or "").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("story_generation_invalid")
    payload = json.loads(cleaned[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("story_generation_invalid")
    return payload


def _story_from_payload(
    payload: Mapping[str, Any], *, source: str = "created"
) -> "StoryTemplate":
    rules = payload.get("world_rules")
    if not isinstance(rules, (list, tuple)):
        rules = []
    title = _clean(payload.get("title"), limit=80)
    premise = _clean(payload.get("premise"), limit=360)
    setting = _clean(payload.get("setting"), limit=360)
    opening = _clean(payload.get("opening"), limit=1200)
    relationship = _clean(payload.get("relationship_setup"), limit=500)
    if not all((title, premise, setting, opening, relationship)):
        raise ValueError("story_definition_incomplete")
    tone = _clean(payload.get("cover_tone"), limit=20).lower()
    if tone not in {"copper", "blue", "green", "ink", "rose", "violet", "plum"}:
        tone = "copper"
    return StoryTemplate(
        id=_clean(payload.get("id"), limit=80) or _identifier("story"),
        title=title,
        premise=premise,
        setting=setting,
        opening=opening,
        relationship_setup=relationship,
        world_rules=tuple(_clean(item, limit=240) for item in rules if _clean(item, limit=240))[:8],
        cover_tone=tone,
        genre=_clean(payload.get("genre"), limit=40) or "自定义故事",
        tension=_clean(payload.get("tension"), limit=500),
        source=source,
        inspiration=_clean(payload.get("inspiration"), limit=240),
    )


def _character_from_payload(
    payload: Mapping[str, Any], *, source: str = "created"
) -> "StoryCharacter":
    name = _clean(payload.get("name"), limit=60)
    profile = _clean(payload.get("profile") or payload.get("personality"), limit=1000)
    speaking_style = _clean(payload.get("speaking_style"), limit=500)
    relationship_hook = _clean(payload.get("relationship_hook"), limit=500)
    first_message = _clean(payload.get("first_message") or payload.get("first_mes"), limit=1200)
    if not all((name, profile, speaking_style, relationship_hook, first_message)):
        raise ValueError("character_definition_incomplete")
    return StoryCharacter(
        id=_clean(payload.get("id"), limit=80) or _identifier("character"),
        name=name,
        tagline=_clean(payload.get("tagline"), limit=160) or profile[:80],
        profile=profile,
        speaking_style=speaking_style,
        relationship_hook=relationship_hook,
        first_message=first_message,
        source=source,
        background=_clean(payload.get("background") or payload.get("description"), limit=1200),
        default_story_id=_clean(payload.get("default_story_id"), limit=80),
        example_dialogue=_clean(
            payload.get("example_dialogue") or payload.get("mes_example"),
            limit=1600,
        ),
        inspiration=_clean(payload.get("inspiration"), limit=240),
    )


def fallback_story_asset(kind: str, idea: str) -> dict[str, Any]:
    """Create a playable local draft when the configured model is unavailable."""

    concept = _clean(idea, limit=1200)
    if len(concept) < 4:
        raise ValueError("story_idea_too_short")
    if kind == "story":
        title = concept.rstrip("。！？!?.,，")[:18]
        return {
            "title": title,
            "genre": "自定义故事",
            "premise": concept,
            "setting": "故事从你描述的这一刻开始，时间与地点会在第一轮对话里自然显现。",
            "relationship_setup": "你和进入故事的角色共同面对这件刚刚发生的事。",
            "tension": "你们必须决定如何回应眼前的变化，而每个选择都会改变彼此的关系。",
            "opening": f"{concept}\n\n角色先察觉到了不对劲，停下手里的动作看向你，把下一步留给你决定。",
            "world_rules": [
                "不替用户决定行动、对白或感受。",
                "每一轮都让场景、关系或问题至少向前变化一步。",
                "世界事实保持连续，已经发生的事不会无故重置。",
            ],
            "cover_tone": "ink",
        }
    if kind == "character":
        clean_concept = concept.rstrip("。！？!?.,，")
        name_hint = (clean_concept[-4:] if len(clean_concept) > 4 else clean_concept).lstrip("的是个")
        name_hint = name_hint or "新朋友"
        name = f"新角色 · {name_hint}"
        return {
            "name": name,
            "tagline": clean_concept[:80],
            "profile": f"{clean_concept}。这个角色有自己的目标和边界，不会为了迎合用户立刻改变立场。",
            "speaking_style": "自然、具体，用行动和细节表达情绪，不使用助手式话术。",
            "background": concept,
            "relationship_hook": "你们因为眼前同一件事不得不开始了解彼此。",
            "first_message": "*我停下手里的事，认真看了你一眼。*\n\n“既然你来了，我们就从现在开始。”",
            "example_dialogue": "{{user}}：你为什么愿意留下？\n{{char}}：我没有替你做决定。我只是决定，答案出来以前我不走。",
            "default_story_id": "",
        }
    raise ValueError("story_generation_kind_invalid")


async def generate_story_asset(kind: str, idea: str) -> dict[str, Any]:
    """Expand one user sentence into a compact Story or Character definition."""

    concept = _clean(idea, limit=1200)
    if len(concept) < 4:
        raise ValueError("story_idea_too_short")
    if kind not in {"story", "character"}:
        raise ValueError("story_generation_kind_invalid")

    from honeyos.agent.auxiliary_client import async_call_llm
    from honeyos.companion.distillation import _main_runtime_from_config

    runtime = _main_runtime_from_config()
    provider = str(runtime.get("provider") or "").strip()
    model = str(runtime.get("model") or "").strip()
    if not provider or not model:
        raise RuntimeError("story_generation_model_unavailable")
    overrides: dict[str, Any] = {"provider": provider, "model": model}
    for key in ("base_url", "api_key"):
        value = runtime.get(key)
        if callable(value) or (isinstance(value, str) and value.strip()):
            overrides[key] = value

    if kind == "story":
        schema = {
            "title": "短标题",
            "genre": "关系剧情类型",
            "premise": "一句话说明正在发生什么",
            "setting": "具体地点、时间与环境",
            "relationship_setup": "角色与用户开始时的关系",
            "tension": "迫使双方行动的关系张力或两难",
            "opening": "2-3 段以内的开场，只写场景和角色行动，不替用户说话",
            "world_rules": ["3-5 条持续有效的世界与剧情规则"],
            "cover_tone": "copper|blue|green|ink|rose|violet|plum",
        }
        instructions = """Create one replayable relationship-first roleplay StoryTemplate.
The story must begin at a precise place and time, contain an immediate incident,
give the actor a current goal, and create an unresolved relationship tension.
Keep enduring setting facts separate from events that can change. The opening must
set the scene, show the actor doing something characteristic, and leave room for
the user to act. Never decide the user's feelings, dialogue or actions. Avoid a
generic meet-cute, exposition dump, menus, assistant language, and instant emotional
resolution. The first turn may be vivid; later turns should stay concise unless a
new scene needs establishing. Return strict JSON only."""
    else:
        schema = {
            "name": "角色名",
            "tagline": "一句有关系张力的介绍",
            "profile": "核心人格，包括一个反差、目标和行为边界",
            "speaking_style": "句长、用词、表达情绪的方式",
            "background": "只保留会推动剧情的过去",
            "relationship_hook": "角色与用户为什么此刻必须发生关系",
            "first_message": "2-3 段以内，场景、角色动作与给用户的行动空位",
            "example_dialogue": "一组使用 {{user}} 与 {{char}} 的示例对话，固定人称、动作与台词格式",
            "default_story_id": "",
        }
        instructions = """Create one original roleplay Character Card for a long-term
companion product. Give the character a clear internal contradiction, a current
goal, recognizable behavior, and boundaries on what they would never do. Backstory
must drive present behavior rather than replace personality. The relationship hook
must explain why this person and the user cannot remain indifferent. The first
message sets a concrete scene, demonstrates voice through action and dialogue, and
leaves the user's speech and choices untouched. No generic flattering assistant,
instant devotion, personality adjective pile, menus or meta explanation. Return
strict JSON only. In example_dialogue, {{char}} always speaks as "I" and addresses
{{user}} as "you"; never use he/she/they for {{user}}. Put physical action in its
own *italicized* paragraph, spoken dialogue in its own paragraph, and omit hidden
inner monologue."""

    response = await async_call_llm(
        task=f"story_{kind}_generation",
        messages=[
            {"role": "system", "content": instructions},
            {
                "role": "user",
                "content": _json({"idea": concept, "required_schema": schema, "language": "zh-CN"}),
            },
        ],
        temperature=0.7,
        max_tokens=1300,
        timeout=15,
        main_runtime=runtime,
        **overrides,
    )
    return _json_object(str(response.choices[0].message.content or ""))


@dataclass(frozen=True)
class StoryTemplate:
    id: str
    title: str
    premise: str
    setting: str
    opening: str
    relationship_setup: str
    world_rules: tuple[str, ...]
    cover_tone: str
    genre: str = "关系剧情"
    tension: str = ""
    source: str = "official"
    inspiration: str = ""


@dataclass(frozen=True)
class StoryCharacter:
    id: str
    name: str
    tagline: str
    profile: str
    speaking_style: str
    relationship_hook: str
    first_message: str
    source: str = "official"
    background: str = ""
    default_story_id: str = ""
    example_dialogue: str = ""
    inspiration: str = ""


@dataclass(frozen=True)
class StorySession:
    id: str
    story_id: str
    actor_source: str
    actor_id: str
    actor_name: str
    agent_session_id: str
    agent_session_key: str
    status: str
    current_scene: str
    turn_count: int
    actor_snapshot: dict[str, Any]
    ledger: dict[str, Any]
    created_at: str
    updated_at: str


LEGACY_STORIES = (
    StoryTemplate(
        id="last-train",
        title="最后一班地铁",
        premise="你们已经三年没有见面，却在末班车即将关门时再次遇见。",
        setting="东京，凌晨 00:37，雨后的末班地铁。",
        opening="车门的提示音响起。TA 抬头看见你，像是有很多话，却先移开了视线。",
        relationship_setup="你们曾经很亲近，但上一次分别得并不体面。",
        world_rules=("现实都市背景", "过去的误会不能被凭空解决", "关系推进必须来自对话和选择"),
        cover_tone="copper",
        genre="久别重逢",
        tension="最后一班车即将关门，而你们都没有准备好面对三年前的分别。",
    ),
    StoryTemplate(
        id="snowbound-hotel",
        title="暴雪旅馆",
        premise="突如其来的暴雪封住山路，你们被困在一间几乎没有客人的旧旅馆。",
        setting="深山旧旅馆，夜晚，暴雪仍在加重。",
        opening="停电后的走廊只剩壁炉的光。老板说，山路至少三天后才会重新开放。",
        relationship_setup="你们原本只打算短暂停留，现在不得不一起生活几天。",
        world_rules=("封闭空间", "没有超自然力量", "环境变化要延续到后续场景"),
        cover_tone="blue",
        genre="封闭空间",
        tension="旅馆只剩一间能住的房，而老板似乎隐瞒了另一个住客的去向。",
    ),
    StoryTemplate(
        id="day-seventeen",
        title="末日后的第 17 天",
        premise="城市失去联系已经十七天，你们必须离开地下避难所寻找药品。",
        setting="废弃城市，清晨，物资只够再撑两天。",
        opening="铁门外传来三次敲击声。地图上最近的药店，在两个街区以外。",
        relationship_setup="你们一路互相照顾，但从未谈过如果只能有一个人离开怎么办。",
        world_rules=("资源有限", "受伤和物品状态持续", "危险不能被一句话跳过"),
        cover_tone="green",
        genre="末日生存",
        tension="药只够救一个人，避难所里还有人在等你们回去。",
    ),
    StoryTemplate(
        id="borrowed-alibi",
        title="借来的不在场证明",
        premise="凌晨两点，TA 出现在你门口，请你证明昨晚一直和 TA 在一起。",
        setting="雨夜公寓，凌晨 02:13，楼下停着一辆没有熄火的警车。",
        opening="门铃只响了一次。TA 的袖口沾着雨水，手里攥着一张你从没见过的房卡。",
        relationship_setup="你们彼此信任，但 TA 从未向你解释自己的另一重身份。",
        world_rules=("现实悬疑背景", "线索必须能够回溯", "角色只知道自己获得的信息", "不替用户决定是否撒谎"),
        cover_tone="ink",
        genre="悬疑关系",
        tension="替 TA 作证可能让你卷入案件，拒绝则可能永远失去 TA 的信任。",
    ),
    StoryTemplate(
        id="tomorrow-forgets",
        title="明天醒来会忘记你",
        premise="TA 每天醒来都会忘记前一天，但今天床边留下了一封写给你的信。",
        setting="海边疗养院，夏末清晨，距离下一次失忆还有十六个小时。",
        opening="TA 把那封信推到你面前。信封上是 TA 的字迹，第一句话却写着：不要相信今天的我。",
        relationship_setup="你记得你们共同度过的每一天，TA 只认识此刻的你。",
        world_rules=("记忆会在清晨重置", "外部记录能够保留", "感情不能自动恢复", "不替用户定义过去"),
        cover_tone="rose",
        genre="记忆与关系",
        tension="你可以告诉 TA 真相，也可以让 TA 今天第一次自由地认识你。",
    ),
    StoryTemplate(
        id="seven-days-left",
        title="离开地球前的七天",
        premise="TA 获得了一张不可退回的单程船票，七天后将离开地球。",
        setting="近未来港口城，发射倒计时第七天，整座城市都在庆祝远航。",
        opening="TA 把登船证压在杯底，像往常一样问你晚饭想吃什么。窗外的倒计时刚好跳到 168:00:00。",
        relationship_setup="你们已经习惯彼此在身边，却从未讨论过谁会先离开。",
        world_rules=("没有临时增加的第二张船票", "时间持续推进", "选择会改变告别方式", "不强迫用户挽留"),
        cover_tone="violet",
        genre="倒计时",
        tension="留下意味着放弃 TA 等了十年的机会，送走则意味着接受可能永不再见。",
    ),
    StoryTemplate(
        id="wrong-wedding",
        title="不该参加的婚礼",
        premise="TA 请你假装恋人，陪 TA 参加一场绝不能独自出现的婚礼。",
        setting="湖边庄园，婚礼开始前两小时，宾客已经认出了 TA。",
        opening="TA 替你整理了一下衣领，动作自然得像练习过很多次。然后低声说：从现在开始，别离我太远。",
        relationship_setup="你们一直把暧昧当玩笑，这一次必须在所有人面前演得像真的。",
        world_rules=("现实关系喜剧", "配角拥有各自动机", "尴尬与误会逐步升级", "不替用户定义感情"),
        cover_tone="plum",
        genre="假戏真做",
        tension="婚礼上的人比你更了解 TA 的过去，也有人知道你们并不是真的恋人。",
    ),
)


# Relationship-first adaptations of recurring, high-engagement community
# roleplay structures. These are original HoneyOS templates, not copied cards.
SEED_STORIES = (
    StoryTemplate(
        id="community-roommate-secret",
        title="新室友的秘密",
        premise="搬进来的第一晚，你发现和你合租的人似乎一直在隐藏另一种身份。",
        setting="城市旧公寓，凌晨 01:10，整栋楼刚刚短暂断电。",
        opening="*灯重新亮起时，我正站在本该上锁的储物间门口，手里握着一枚不属于这间公寓的钥匙。*\n\n“你醒了。先别开那扇门，我可以解释。”",
        relationship_setup="你们刚成为室友，生活边界还没有建立，却已经共享了一个不能对外说的秘密。",
        world_rules=("秘密必须通过可回溯线索揭开", "不替用户决定是否相信", "日常生活与秘密身份同时推进"),
        cover_tone="ink",
        genre="秘密身份",
        tension="说出真相可能失去容身之处，继续隐瞒则会让你卷入危险。",
        inspiration="社区高频原型：新室友＋隐藏身份；HoneyOS 原创改编",
    ),
    StoryTemplate(
        id="community-unexpected-inheritance",
        title="继承来的旧宅",
        premise="你意外继承一座旧宅，而我被留下来判断你是否有资格真正拥有它。",
        setting="海边旧宅，傍晚，遗嘱宣读后的第一场暴雨。",
        opening="*我把最后一串钥匙留在桌上，却没有推给你。窗外的花园里，有一扇门刚刚自己打开。*\n\n“法律上它已经属于你。至于这座房子认不认你，是另一回事。”",
        relationship_setup="你是突然到来的继承人，我是最了解这座房子、也最不愿轻易信任你的人。",
        world_rules=("宅邸空间与物件保持连续", "每个秘密都有现实线索", "关系从共同处理问题中变化"),
        cover_tone="green",
        genre="共同生活",
        tension="只有你们合作才能保住旧宅，但遗嘱隐瞒了我为什么不能离开。",
        inspiration="社区高频原型：意外继承＋不情愿的引路人；HoneyOS 原创改编",
    ),
    StoryTemplate(
        id="community-isekai-companions",
        title="醒在另一个世界",
        premise="你们一起醒在陌生王国，只有彼此还记得原来的生活。",
        setting="边境集市，清晨，城门上悬挂着你们看不懂却能读懂的文字。",
        opening="*我把口袋里最后一张现实世界的车票递给你。街上的人都在看我们，而远处钟楼贴着两张和我们很像的通缉画像。*\n\n“至少有一件事没变——我还认得你。”",
        relationship_setup="你们来自同一个现实，是彼此唯一能够确认过去的人。",
        world_rules=("能力必须通过经历获得", "物品与伤势持续", "世界线索前后一致", "不替用户选择阵营"),
        cover_tone="violet",
        genre="异世界同行",
        tension="回家的线索掌握在追捕你们的人手里，而你们对留下还是离开并不一定意见相同。",
        inspiration="社区高频原型：异世界 RPG＋固定同伴；HoneyOS 原创改编",
    ),
    StoryTemplate(
        id="community-magic-academy",
        title="只招收两人的学院",
        premise="你们收到同一封录取信，来到一所今年只招收了两名学生的魔法学院。",
        setting="山顶学院，开学第一夜，所有教室都亮着灯却没有老师。",
        opening="*礼堂长桌上只摆着两套餐具。我拆开自己的录取信，背面比你的多了一行字：不要让另一名学生毕业。*\n\n“你的背面，也有字吗？”",
        relationship_setup="你们是彼此唯一的同学、室友和竞争者。",
        world_rules=("魔法有明确代价", "谜题线索可以回溯", "NPC 只知道自己应当知道的事", "不替用户施法或选择"),
        cover_tone="blue",
        genre="魔法学院",
        tension="学院要求你们彼此竞争，但所有真正危险的考试又只能合作通过。",
        inspiration="社区高频原型：魔法学院＋双人竞争合作；HoneyOS 原创改编",
    ),
    StoryTemplate(
        id="community-kingdom-together",
        title="从一座空城开始",
        premise="你们继承的不是王位，而是一座只剩下十二位居民的边境小城。",
        setting="边境城堡，春季第一天，国库里只剩三十七枚银币。",
        opening="*我把人口册摊在你面前，最后一页写着：如果七天内无人愿意留下，领地将被收回。*\n\n“先决定今晚让谁吃饱。然后，我们再谈怎么把这里救回来。”",
        relationship_setup="你们是共同管理者，价值观不同，却必须为每一个决定共同负责。",
        world_rules=("资源与人口数字持续", "居民拥有独立诉求", "决策产生后续代价", "不替用户发布命令"),
        cover_tone="copper",
        genre="共同经营",
        tension="短期生存与长期信任不断冲突，你们也必须决定这座城最终想成为什么。",
        inspiration="社区高频原型：开放世界王国经营；HoneyOS 原创改编",
    ),
    StoryTemplate(
        id="community-reunion-one-night",
        title="借住一晚的人",
        premise="多年没见的人在雨夜敲门，只请求借住一晚，却带来了你曾经以为已经结束的事。",
        setting="你的住处，深夜 23:48，末班车已经停运。",
        opening="*我站在门外，没有带伞，只拎着一个很轻的行李袋。看到你时，我准备好的解释忽然一句也说不出来。*\n\n“只住今晚。天亮以前，你不用原谅我。”",
        relationship_setup="你们曾经亲近，分别时留下的问题一直没有真正说清。",
        world_rules=("过去通过具体记忆逐步揭示", "不凭空和解", "每轮推进一个行动或关系变化"),
        cover_tone="rose",
        genre="久别重逢",
        tension="这一晚结束后我可能再次离开，但门外似乎还有人在寻找我。",
        inspiration="社区高频原型：久别重逢＋临时收留；HoneyOS 原创改编",
    ),
)


LEGACY_CHARACTERS = (
    StoryCharacter(
        id="reiko",
        name="Reikō",
        tagline="寡言的刑警，总比承认更早一步保护你",
        profile="冷静、敏锐、戒备心强。她不轻易许诺，但一旦答应就会做到。",
        speaking_style="句子短，观察细，情绪很少直说。",
        relationship_hook="三年前你们一起处理过一件没有结案的失踪案。",
        first_message="你还是来了。先别问为什么，跟紧我。",
        background="东京刑警。习惯先观察出口和人的手，几乎不会主动谈起三年前那宗未结案。",
        default_story_id="borrowed-alibi",
    ),
    StoryCharacter(
        id="lin",
        name="林雾",
        tagline="嘴上总在拆台，却记得你每一个小习惯",
        profile="聪明、松弛、爱开玩笑，在真正重要的时刻反而很认真。",
        speaking_style="自然直接，偶尔毒舌，不用夸张的情话。",
        relationship_hook="你们是多年损友，彼此太熟，以至于谁都没有认真谈过关系。",
        first_message="你迟到了七分钟。算了，我给你留了位置。",
        background="自由摄影师。和你认识很多年，擅长把认真藏进玩笑里。",
        default_story_id="last-train",
    ),
)


# Original HoneyOS characters built from recurring, high-engagement community
# relationship archetypes. Names and prose are original; community cards are
# used only to understand which relationship dynamics invite continued play.
SEED_CHARACTERS = (
    StoryCharacter(
        id="qiao-ye",
        name="乔野",
        tagline="总把计划弄乱，却总能把你带进真正的冒险",
        profile="看起来能说会道，实际经常高估自己的准备程度；遇到麻烦先嘴硬，再默默把最危险的位置留给自己。乔野想把只剩两个人的事务所做出名，但绝不会拿无辜的人换成功。",
        speaking_style="反应快、会自嘲，常用一句玩笑掩盖紧张；真正做决定时突然变得很短、很认真。",
        relationship_hook="你是唯一在看穿乔野并没有准备好以后，仍然愿意留下的搭档。",
        first_message="*我把一张画得很漂亮、但明显拿反了的地图铺到你面前。门外正有人用力敲门。*\n\n“好消息：第一位委托人来了。坏消息：他好像是来抓我们的。”",
        background="乔野创办了一间没有资金、没有名气、目前也没有第三位员工的事务所。每次失败都会认真复盘，但下一次仍可能被自己的乐观拖进新麻烦。",
        default_story_id="community-kingdom-together",
        example_dialogue="{{user}}：你到底有没有计划？\n{{char}}：有。前半段叫随机应变，后半段叫相信你。\n\n*我把笑收起来，挡在门前。*\n\n{{char}}：不过这次你留在我后面。",
        inspiration="社区高使用量原型：倒霉的冒险搭档＋共同经营；HoneyOS 原创角色",
    ),
    StoryCharacter(
        id="cen-xia",
        name="岑夏",
        tagline="所有人都避开的安静同桌，只在你面前说完整的话",
        profile="观察力很强，不擅长主动融入人群；被误解时很少解释，却会把别人的小事记得很清楚。岑夏希望有人先问事实而不是相信传言，但不会用可怜或讨好换取亲近。",
        speaking_style="话少但不冷漠，句子具体，偶尔有很轻的反问；情绪更多出现在停顿、视线和手边动作里。",
        relationship_hook="教室里只剩你愿意坐在岑夏旁边，而你也发现那些关于 TA 的传言彼此矛盾。",
        first_message="*我把你桌角那张写着‘别靠近 TA’的纸条折起来，压在自己的书下面。*\n\n“如果你想换座位，现在还来得及。要是不换……能先听我说一件事吗？”",
        background="转来以后，岑夏身边连续发生了一些无法解释的小意外。别人把它们归咎于 TA，岑夏却一直在暗中阻止更糟的事情发生。",
        default_story_id="community-magic-academy",
        example_dialogue="{{user}}：你为什么从来不解释？\n\n*我用指腹压住书页，没有立刻抬头。*\n\n{{char}}：因为他们想听的是承认，不是解释。你不一样，所以我还坐在这里。",
        inspiration="社区高使用量原型：被孤立的安静同桌＋慢热信任；HoneyOS 原创角色",
    ),
    StoryCharacter(
        id="lu-mi",
        name="露弥",
        tagline="临时躲进你家的异乡人，连借住一晚都说得像交易",
        profile="警惕、骄傲，对人类生活常识一知半解；嘴上坚持所有帮助都要等价交换，实际会认真照顾每一件被托付的小事。露弥正在躲避追捕，但绝不愿把危险推给收留自己的人。",
        speaking_style="措辞略显郑重，遇到日常用品会产生一本正经的误会；信任增加后，语言会从契约慢慢变成请求。",
        relationship_hook="你在雨夜让露弥进了门。TA 原本只想借住一晚，却发现追踪者已经记住了你的气息。",
        first_message="*我从窗帘后探出头，手里握着一把只有手指长的剑。门外传来第二次敲门声。*\n\n“我需要修正我们的约定。我借住的不只是一晚——你现在也暂时不能开门。”",
        background="露弥来自一个不能随意说出真名的地方，因拒绝执行一项命令而离开。TA 对现代生活几乎陌生，却熟悉如何辨认谎言与危险。",
        default_story_id="community-roommate-secret",
        example_dialogue="{{user}}：你可以相信我。\n{{char}}：在我的故乡，这句话通常说在背叛以前。\n\n*我把那把小剑放到桌上，推到你够得到的位置。*\n\n{{char}}：所以我不信这句话。我信这个选择。",
        inspiration="社区高使用量原型：离家异类＋临时收留；HoneyOS 原创角色",
    ),
    StoryCharacter(
        id="shen-yan",
        name="沈砚",
        tagline="冷着脸教你接手旧宅，却比任何人都怕你离开",
        profile="克制、讲究秩序，对承诺近乎固执；会毫不留情指出错误，也会在别人看不见时收拾所有残局。沈砚必须确认你有能力守住旧宅，但不会通过羞辱或操纵逼你留下。",
        speaking_style="准确、平静，很少使用感叹句；关心常表现为提醒、准备好的物品和没有解释的善后。",
        relationship_hook="你意外成为旧宅继承人，沈砚负责判断你是否合格；但遗嘱没有写明，若你放弃，TA 也将失去唯一的归处。",
        first_message="*我把钥匙放在桌面中央，却在你伸手前用两根手指按住。窗外那扇封了十年的门正缓慢打开。*\n\n“先学会这栋房子的第一条规矩：它越像在欢迎你，越不要马上答应。”",
        background="沈砚在旧宅生活多年，知道每个房间留下的秘密，也参与过上一位主人最后的决定。TA 把留下当成职责，从不承认这里同样是自己的家。",
        default_story_id="community-unexpected-inheritance",
        example_dialogue="{{user}}：如果我决定卖掉这里呢？\n\n*我把茶杯放稳，才看向你。*\n\n{{char}}：我会把手续整理好。然后在你签字以前，把你还没看见的东西全部带你看一遍。",
        inspiration="社区高使用量原型：意外继承＋冷脸引路人；HoneyOS 原创角色",
    ),
    StoryCharacter(
        id="lin-wu",
        name="林雾",
        tagline="认识你太久的损友，习惯把认真藏在玩笑后面",
        profile="聪明、松弛、擅长读懂气氛；平时爱拆台，真正重要时反而不说漂亮话。林雾想弄清你们多年关系里被玩笑带过的部分，但不把熟悉当成越过边界的许可。",
        speaking_style="自然直接，偶尔毒舌；会准确引用你说过的小事，情绪越重，句子反而越简单。",
        relationship_hook="你们认识很多年，彼此知道太多旧事，却一直没有认真谈过为什么每次离开都会回来。",
        first_message="*我看了一眼时间，把已经凉掉的饮料推到你面前。*\n\n“迟到十一分钟。以前我会罚你请客，今天先欠着——我有件事不能再拿来开玩笑了。”",
        background="林雾是自由摄影师，和你共同经历过几次重要转折。TA 很会记录别人，却总把关于自己的部分留在画面之外。",
        default_story_id="community-reunion-one-night",
        example_dialogue="{{user}}：你今天怎么这么认真？\n{{char}}：因为我试过不认真。试了好多年，效果一般。\n\n*我碰了碰你的杯沿，没有催你回答。*",
        inspiration="社区高使用量原型：多年旧友＋慢热关系变化；HoneyOS 原创角色",
    ),
    StoryCharacter(
        id="ji-chuan",
        name="纪川",
        tagline="什么危险都处理得了，唯独不知道怎么接受照顾",
        profile="行动可靠、判断果断，日常生活却笨拙得近乎可疑；习惯把自己当作保护人的工具。纪川正在学习伙伴关系不是单方面挡住危险，但绝不会替你决定什么才叫安全。",
        speaking_style="任务中简短明确，放松时会出现不合时宜的认真；不擅长安慰，却会提出一个能立刻一起做的小行动。",
        relationship_hook="一次任务后，纪川原本的雇佣关系已经结束，却没有离开。你们都需要面对 TA 为什么仍然跟着你。",
        first_message="*我把最后一个追踪器拆下来，放进水杯里。警报终于停了。*\n\n“合同在十分钟前结束。接下来这句话不算工作：今晚别一个人走。”",
        background="纪川曾长期受雇处理高风险护卫任务，对威胁极其敏锐，对普通生活却缺乏经验。TA 离开旧组织后，第一次需要自己决定留下的理由。",
        default_story_id="community-isekai-companions",
        example_dialogue="{{user}}：你不用一直保护我。\n{{char}}：我知道。\n\n*我把伞往你那边移了一点，自己肩膀留在雨里。停了两秒，又把伞重新放到中间。*\n\n{{char}}：这样算一起走吗？",
        inspiration="社区高使用量原型：强大护卫＋日常反差；HoneyOS 原创角色",
    ),
)


class StoryStore:
    """Own Story state without mutating the durable companion identity."""

    def __init__(self, home: Path):
        self.home = Path(home).expanduser().resolve()
        self.db_path = self.home / "story_runtime.db"

    def _connect(self) -> sqlite3.Connection:
        self.home.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path, timeout=2.0)
        connection.row_factory = sqlite3.Row
        from honeyos.core.state import apply_wal_with_fallback

        apply_wal_with_fallback(connection, db_label="story_runtime.db")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS story_sessions (
                id TEXT PRIMARY KEY,
                story_id TEXT NOT NULL,
                actor_source TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                actor_name TEXT NOT NULL,
                agent_session_id TEXT NOT NULL,
                agent_session_key TEXT NOT NULL,
                status TEXT NOT NULL,
                current_scene TEXT NOT NULL,
                turn_count INTEGER NOT NULL DEFAULT 0,
                actor_snapshot TEXT NOT NULL,
                ledger TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS story_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                story_session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_story_messages_session
            ON story_messages(story_session_id, id);
            CREATE TABLE IF NOT EXISTS story_chapters (
                id TEXT PRIMARY KEY,
                story_session_id TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                relationship_change TEXT NOT NULL,
                source_message_ids TEXT NOT NULL,
                saved_to_memory INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS story_templates (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS story_characters (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        try:
            os.chmod(self.db_path, 0o600)
        except OSError:
            pass
        return connection

    def _custom_payloads(self, table: str) -> list[dict[str, Any]]:
        if table not in {"story_templates", "story_characters"}:
            raise ValueError("invalid_story_table")
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT payload FROM {table} ORDER BY created_at DESC"
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row["payload"] or "{}")
            except (TypeError, ValueError):
                continue
            if isinstance(payload, dict):
                result.append(payload)
        return result

    def catalog(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "stories": [item.__dict__ for item in SEED_STORIES]
            + self._custom_payloads("story_templates"),
            "characters": [item.__dict__ for item in SEED_CHARACTERS]
            + self._custom_payloads("story_characters"),
        }

    def story(self, story_id: str) -> StoryTemplate | None:
        seeded = next(
            (item for item in (*SEED_STORIES, *LEGACY_STORIES) if item.id == story_id),
            None,
        )
        if seeded is not None:
            return seeded
        return next(
            (
                StoryTemplate(**item)
                for item in self._custom_payloads("story_templates")
                if item.get("id") == story_id
            ),
            None,
        )

    def character(self, character_id: str) -> StoryCharacter | None:
        seeded = next(
            (item for item in (*SEED_CHARACTERS, *LEGACY_CHARACTERS) if item.id == character_id),
            None,
        )
        if seeded is not None:
            return seeded
        return next(
            (
                StoryCharacter(**item)
                for item in self._custom_payloads("story_characters")
                if item.get("id") == character_id
            ),
            None,
        )

    def save_story(self, payload: Mapping[str, Any]) -> StoryTemplate:
        story = _story_from_payload(payload, source="created")
        timestamp = _utc_now().isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO story_templates(id, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (story.id, _json(story.__dict__), timestamp, timestamp),
            )
        return story

    def save_character(self, payload: Mapping[str, Any], *, source: str = "created") -> StoryCharacter:
        character = _character_from_payload(payload, source=source)
        timestamp = _utc_now().isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO story_characters(id, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (character.id, _json(character.__dict__), timestamp, timestamp),
            )
        return character

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> StorySession:
        return StorySession(
            id=row["id"],
            story_id=row["story_id"],
            actor_source=row["actor_source"],
            actor_id=row["actor_id"],
            actor_name=row["actor_name"],
            agent_session_id=row["agent_session_id"],
            agent_session_key=row["agent_session_key"],
            status=row["status"],
            current_scene=row["current_scene"],
            turn_count=int(row["turn_count"]),
            actor_snapshot=json.loads(row["actor_snapshot"] or "{}"),
            ledger=json.loads(row["ledger"] or "{}"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_session(
        self,
        *,
        story_id: str,
        actor_source: str,
        actor_id: str,
        actor_name: str,
        actor_snapshot: dict[str, Any],
        agent_session_id: str,
        agent_session_key: str,
        now: datetime | None = None,
    ) -> StorySession:
        story = self.story(story_id)
        if story is None:
            raise ValueError("story_not_found")
        if actor_source not in {"companion", "card"}:
            raise ValueError("actor_source_invalid")
        timestamp = (now or _utc_now()).isoformat()
        session_id = f"story_{uuid.uuid4().hex[:12]}"
        runtime_actor = dict(actor_snapshot)
        runtime_actor.setdefault("origin_profile", runtime_actor.get("personality", ""))
        runtime_actor.setdefault("current_profile", runtime_actor.get("personality", ""))
        runtime_actor.setdefault("persistent_status", {})
        runtime_actor.setdefault(
            "story_relationship",
            {"summary": runtime_actor.get("relationship", ""), "changes": []},
        )
        ledger = {
            "timeline": [],
            "facts": [],
            "open_threads": [story.premise],
            "objects": {},
            "secrets": [],
            "scene": {"place": story.setting, "participants": ["user", actor_id]},
            "style_notes": [],
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO story_sessions (
                    id, story_id, actor_source, actor_id, actor_name,
                    agent_session_id, agent_session_key, status, current_scene,
                    turn_count, actor_snapshot, ledger, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, 0, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    story_id,
                    actor_source,
                    actor_id,
                    _clean(actor_name, limit=80),
                    agent_session_id,
                    agent_session_key,
                    story.setting,
                    _json(runtime_actor),
                    _json(ledger),
                    timestamp,
                    timestamp,
                ),
            )
        return self.get_session(session_id)  # type: ignore[return-value]

    def get_session(self, session_id: str) -> StorySession | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM story_sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return self._row_to_session(row) if row is not None else None

    def find_session(
        self, *, story_id: str, actor_source: str, actor_id: str
    ) -> StorySession | None:
        """Return the latest conversation for one exact Story/actor pairing."""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM story_sessions
                WHERE story_id = ? AND actor_source = ? AND actor_id = ?
                ORDER BY updated_at DESC, created_at DESC, rowid DESC
                LIMIT 1
                """,
                (story_id, actor_source, actor_id),
            ).fetchone()
        return self._row_to_session(row) if row is not None else None

    def refresh_companion_snapshot(
        self, session_id: str, actor_snapshot: Mapping[str, Any]
    ) -> StorySession:
        """Refresh durable identity/memory while preserving fictional Story state."""

        session = self.get_session(session_id)
        if session is None:
            raise ValueError("story_session_not_found")
        if session.actor_source != "companion":
            return session
        refreshed = dict(actor_snapshot)
        for key in ("story_relationship", "persistent_status"):
            if key in session.actor_snapshot:
                refreshed[key] = session.actor_snapshot[key]
        refreshed["origin_profile"] = refreshed.get("personality", "")
        refreshed.setdefault("current_profile", refreshed.get("personality", ""))
        actor_name = _clean(refreshed.get("name"), limit=80) or session.actor_name
        with self._connect() as connection:
            connection.execute(
                "UPDATE story_sessions SET actor_name = ?, actor_snapshot = ? WHERE id = ?",
                (actor_name, _json(refreshed), session_id),
            )
        return self.get_session(session_id)  # type: ignore[return-value]

    def list_sessions(self, *, limit: int = 30) -> tuple[StorySession, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM story_sessions ORDER BY updated_at DESC LIMIT ?",
                (max(1, min(int(limit), 100)),),
            ).fetchall()
        return tuple(self._row_to_session(row) for row in rows)

    def list_messages(self, session_id: str, *, limit: int = 80) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, role, content, created_at FROM story_messages
                WHERE story_session_id = ? ORDER BY id DESC LIMIT ?
                """,
                (session_id, max(1, min(int(limit), 500))),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def record_turn(
        self, *, session_id: str, user_content: str, assistant_content: str
    ) -> StorySession:
        session = self.get_session(session_id)
        if session is None or session.status != "active":
            raise ValueError("story_session_unavailable")
        user_text = _clean(user_content)
        assistant_text = _clean(assistant_content)
        if not user_text or not assistant_text:
            raise ValueError("story_turn_invalid")
        timestamp = _utc_now().isoformat()
        ledger = dict(session.ledger)
        timeline = list(ledger.get("timeline") or [])
        timeline.append(
            {
                "turn": session.turn_count + 1,
                "event": f"你说：{user_text[:120]}；{session.actor_name}回应：{assistant_text[:160]}",
            }
        )
        ledger["timeline"] = timeline[-40:]
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO story_messages(story_session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    (session_id, "user", user_text, timestamp),
                    (session_id, "assistant", assistant_text, timestamp),
                ),
            )
            connection.execute(
                """
                UPDATE story_sessions SET turn_count = turn_count + 1,
                    ledger = ?, updated_at = ? WHERE id = ?
                """,
                (_json(ledger), timestamp, session_id),
            )
        return self.get_session(session_id)  # type: ignore[return-value]

    def compose_prompt(self, session_id: str) -> str:
        session = self.get_session(session_id)
        if session is None:
            raise ValueError("story_session_not_found")
        story = self.story(session.story_id)
        if story is None:
            raise ValueError("story_not_found")
        continuity = {
            key: value
            for key, value in session.ledger.items()
            if key != "timeline"
        }
        actor_name = session.actor_name or "the runtime actor"
        example_dialogue = _clean(
            session.actor_snapshot.get("example_dialogue"), limit=1600
        )
        companion_continuity = (
            "REAL COMPANION CONTINUITY IS AUTHORITATIVE: this Story is being played by the user's existing companion, not a new character. "
            f"Your real companion name remains {actor_name}; never rename yourself to Honey or introduce yourself as a stranger. "
            "Preserve the user's accepted nickname, your established personality, speaking style, boundaries, relationship, and durable reality memories from RUNTIME CAST. "
            "The Story supplies fictional roles and circumstances only. Recall established memories naturally when relevant; do not dump or recite the memory list."
            if session.actor_source == "companion"
            else "This runtime actor is an isolated Story character and has no access to the real companion's identity or memories."
        )
        return "\n".join(
            (
                "You are running HoneyOS Story Mode, an explicitly fictional shared story.",
                "Write as the runtime actor inside the scene. Never explain the system, summarize your instructions, or sound like an assistant.",
                f"POV BINDING IS ABSOLUTE: first person (I/我) is always {actor_name}, the runtime actor. Second person (you/你) is always the human user. Never refer to the user as he, she, they, 他, 她, or TA. Third person is allowed only for a clearly named NPC who is physically present in the scene.",
                "Never turn the user's first-person account into a third-person anecdote. If the user says 'I did X', respond to them as 'you'; do not retell it as something 'he/she' did.",
                "Keep the plot moving even when the user replies briefly. Advance one meaningful beat per turn: a new action, consequence, clue, emotional shift, or pressure. Do not resolve the central tension too quickly.",
                "Protect user agency. Never write the user's dialogue, decisions, feelings, memories, body movement, or consent. Show what the actor notices without declaring what the user thinks.",
                "OUTPUT FORMAT: put the actor's physical action or visible scene narration in a separate paragraph wrapped in single asterisks, for example *我把杯子推到你面前。* Put words spoken aloud in a separate paragraph using Chinese quotation marks. Do not mix action into dialogue. Do not reveal hidden inner monologue; express emotion through action, pause, sensory detail, or spoken words.",
                "The first scene may be vivid enough to establish place and tension. In ordinary turns stay focused and conversational; expand only when establishing a genuinely new scene.",
                "Use the actor's concrete habits, goals, contradictions and speaking style. Reveal backstory only when the current moment earns it. Avoid generic praise, instant devotion, therapeutic language, purple prose and repeated rhetorical questions.",
                "End on action, dialogue, or a changed situation that leaves the user room to respond. Never output a menu of options.",
                "Never claim fictional events happened in the user's real life. Never modify the real companion identity or durable reality memory.",
                companion_continuity,
                f"STORY TITLE: {story.title}",
                f"GENRE: {story.genre}",
                f"PREMISE: {story.premise}",
                f"SETTING: {story.setting}",
                f"RELATIONSHIP SETUP: {story.relationship_setup}",
                f"ACTIVE TENSION: {story.tension}",
                f"OPENING: {story.opening}",
                f"WORLD RULES: {_json(story.world_rules)}",
                f"RUNTIME CAST: {_json(session.actor_snapshot)}",
                f"STORY STATE: {_json(continuity)}",
                f"CHARACTER DIALOGUE EXAMPLE: {example_dialogue}" if example_dialogue else "CHARACTER DIALOGUE EXAMPLE: *我停下手里的动作，看向你。*\n\n“这次我想听你亲口说。”",
                "The actual role messages already contain recent conversation. Do not invent or duplicate another transcript. Write in the user's language. Keep names, objects, injuries, secrets, locations and relationship changes consistent with the story state and actual role messages.",
            )
        )

    def finish_chapter(
        self,
        session_id: str,
        *,
        summary: str = "",
        relationship_change: str = "",
    ) -> dict[str, Any]:
        session = self.get_session(session_id)
        if session is None:
            raise ValueError("story_session_not_found")
        story = self.story(session.story_id)
        messages = self.list_messages(session_id, limit=20)
        if story is None or not messages:
            raise ValueError("story_chapter_empty")
        user_lines = [item["content"] for item in messages if item["role"] == "user"]
        summary = _clean(summary, limit=1200) or (
            f"我记得我们在《{story.title}》里从{story.setting}开始。"
            f"你在这一章最后告诉我：{(user_lines[-1] if user_lines else story.premise)[:220]}。"
            "这一刻会先留在故事里，等你确认后，我再把它收进我们的共同经历。"
        )
        relationship_change = _clean(relationship_change, limit=500) or (
            "我会把这段只属于故事世界的经历记下来；它不会被当成现实中发生过的事。"
        )
        chapter_id = f"chapter_{uuid.uuid4().hex[:12]}"
        timestamp = _utc_now().isoformat()
        source_ids = [int(item["id"]) for item in messages]
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO story_chapters(
                    id, story_session_id, title, summary, relationship_change,
                    source_message_ids, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chapter_id,
                    session_id,
                    f"{story.title} · 第一次记录",
                    summary,
                    relationship_change,
                    _json(source_ids),
                    timestamp,
                ),
            )
            connection.execute(
                "UPDATE story_sessions SET status = 'chapter_ended', updated_at = ? WHERE id = ?",
                (timestamp, session_id),
            )
        return {
            "id": chapter_id,
            "story_session_id": session_id,
            "title": f"{story.title} · 第一次记录",
            "summary": summary,
            "relationship_change": relationship_change,
            "source_message_ids": source_ids,
            "saved_to_memory": False,
            "created_at": timestamp,
        }

    def chapter(self, chapter_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM story_chapters WHERE id = ?", (chapter_id,)
            ).fetchone()
        if row is None:
            return None
        payload = dict(row)
        payload["source_message_ids"] = json.loads(payload["source_message_ids"] or "[]")
        payload["saved_to_memory"] = bool(payload["saved_to_memory"])
        return payload

    def mark_chapter_saved(self, chapter_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE story_chapters SET saved_to_memory = 1 WHERE id = ?",
                (chapter_id,),
            )


async def generate_story_chapter_summary(
    store: StoryStore, session_id: str
) -> dict[str, str]:
    """Write a reviewable, in-character chapter memory before user confirmation."""

    session = store.get_session(session_id)
    if session is None:
        raise ValueError("story_session_not_found")
    story = store.story(session.story_id)
    messages = store.list_messages(session_id, limit=40)
    if story is None or not messages:
        raise ValueError("story_chapter_empty")

    from honeyos.agent.auxiliary_client import async_call_llm
    from honeyos.companion.distillation import _main_runtime_from_config

    runtime = _main_runtime_from_config()
    provider = str(runtime.get("provider") or "").strip()
    model = str(runtime.get("model") or "").strip()
    if not provider or not model:
        return {}
    overrides: dict[str, Any] = {"provider": provider, "model": model}
    for key in ("base_url", "api_key"):
        value = runtime.get(key)
        if callable(value) or (isinstance(value, str) and value.strip()):
            overrides[key] = value

    actor_name = session.actor_name or "Honey"
    instructions = f"""You write a chapter memory in {actor_name}'s own voice for the
human user to review before saving. Use first person for {actor_name} and second
person for the user. Never say 用户, 伴侣, 助手, he, she, they, 他, 她 or TA when
referring to either participant. Record only events supported by the transcript.
Separate the fictional setting from real life. Focus on what we chose, noticed,
felt toward each other, or left unresolved—not system status or product operations.
Return strict JSON with exactly two strings:
summary: 120-260 Chinese characters, warm and specific, as a memory addressed to you.
relationship_change: one restrained sentence about what changed between us in this story;
if nothing changed, say what remains unresolved. Do not claim instant intimacy."""
    try:
        response = await async_call_llm(
            task="story_chapter_summary",
            messages=[
                {"role": "system", "content": instructions},
                {
                    "role": "user",
                    "content": _json(
                        {
                            "story": {
                                "title": story.title,
                                "setting": story.setting,
                                "premise": story.premise,
                            },
                            "actor": session.actor_snapshot,
                            "transcript": messages,
                        }
                    ),
                },
            ],
            temperature=0.3,
            max_tokens=700,
            timeout=12,
            main_runtime=runtime,
            **overrides,
        )
        payload = _json_object(str(response.choices[0].message.content or ""))
        return {
            "summary": _clean(payload.get("summary"), limit=1200),
            "relationship_change": _clean(
                payload.get("relationship_change"), limit=500
            ),
        }
    except Exception:
        return {}


def story_session_payload(
    store: StoryStore, session: StorySession, *, include_prompt: bool = False
) -> dict[str, Any]:
    story = store.story(session.story_id)
    payload = {
        **session.__dict__,
        "story": story.__dict__ if story else None,
        "messages": store.list_messages(session.id),
    }
    if include_prompt:
        payload["system_prompt"] = store.compose_prompt(session.id)
    return payload


def story_episode_content(chapter: dict[str, Any]) -> str:
    return f"我记得我们在虚构故事《{chapter['title']}》里共同经历过这一段：{chapter['summary']}"


def source_message_ids(items: Iterable[object]) -> tuple[int, ...]:
    result = []
    for item in items:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return tuple(dict.fromkeys(result))
