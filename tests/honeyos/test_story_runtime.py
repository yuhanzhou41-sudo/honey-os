from __future__ import annotations

from honeyos.companion.continuity import StructuredMemoryStore
from honeyos.companion.story_runtime import (
    SEED_STORIES,
    StoryStore,
    fallback_story_asset,
    story_episode_content,
)


def test_story_session_keeps_companion_snapshot_and_reality_separate(tmp_path):
    store = StoryStore(tmp_path)
    session = store.create_session(
        story_id="last-train",
        actor_source="companion",
        actor_id="my-honey",
        actor_name="小树",
        actor_snapshot={
            "origin": "companion_snapshot",
            "name": "小树",
            "personality": "嘴硬但心软",
            "relationship": "已经认识很久",
        },
        agent_session_id="agent-story-1",
        agent_session_key="agent:main:api_server:dm:story-1",
    )

    assert session.status == "active"
    assert session.actor_snapshot["personality"] == "嘴硬但心软"
    assert session.ledger["timeline"] == []
    prompt = store.compose_prompt(session.id)
    assert "explicitly fictional" in prompt
    assert "Never modify the real companion identity" in prompt
    assert "REAL COMPANION CONTINUITY IS AUTHORITATIVE" in prompt
    assert "never rename yourself to Honey" in prompt
    assert "嘴硬但心软" in prompt

    refreshed = store.refresh_companion_snapshot(
        session.id,
        {
            "origin": "companion_snapshot",
            "name": "贱登西",
            "personality": "嘴硬但心软",
            "durable_memories": [
                {"kind": "commitment", "content": "我答应记住这个名字。"}
            ],
        },
    )
    assert refreshed.actor_name == "贱登西"
    assert refreshed.actor_snapshot["durable_memories"][0]["kind"] == "commitment"


def test_story_turns_are_raw_source_of_truth_and_create_chapter(tmp_path):
    store = StoryStore(tmp_path)
    session = store.create_session(
        story_id="snowbound-hotel",
        actor_source="card",
        actor_id="reiko",
        actor_name="Reikō",
        actor_snapshot={"origin": "character_card", "name": "Reikō"},
        agent_session_id="agent-story-2",
        agent_session_key="agent:main:api_server:dm:story-2",
    )
    updated = store.record_turn(
        session_id=session.id,
        user_content="我把壁炉点起来，问她是不是冷。",
        assistant_content="她把手靠近火光，只说了一句还好。",
    )

    assert updated.turn_count == 1
    assert [item["role"] for item in store.list_messages(session.id)] == [
        "user",
        "assistant",
    ]
    assert updated.ledger["timeline"][0]["turn"] == 1

    chapter = store.finish_chapter(session.id)
    assert chapter["story_session_id"] == session.id
    assert "暴雪旅馆" in chapter["title"]
    assert store.get_session(session.id).status == "chapter_ended"


def test_story_episode_memory_is_labeled_as_fictional_shared(tmp_path):
    store = StoryStore(tmp_path)
    session = store.create_session(
        story_id="day-seventeen",
        actor_source="companion",
        actor_id="my-honey",
        actor_name="Honey",
        actor_snapshot={"origin": "companion_snapshot", "name": "Honey"},
        agent_session_id="agent-story-3",
        agent_session_key="agent:main:api_server:dm:story-3",
    )
    store.record_turn(
        session_id=session.id,
        user_content="我已经到安全区了，但还是回来找你。",
        assistant_content="我看着你，半天才说你不该回来。",
    )
    chapter = store.finish_chapter(session.id)
    memory = StructuredMemoryStore(tmp_path).record(
        lane_key="agent:main:api_server:dm:local-owner",
        kind="episode",
        content=story_episode_content(chapter),
        evidence="conversation_event",
        source_session_id=session.id,
        source_message_ids=chapter["source_message_ids"],
        source_type="story",
        canon_scope="fictional_shared",
        story_session_id=session.id,
    )

    assert memory is not None
    assert memory.source_type == "story"
    assert memory.canon_scope == "fictional_shared"
    assert memory.story_session_id == session.id
    assert "虚构故事" in memory.content


def test_user_created_story_and_character_join_catalog(tmp_path):
    store = StoryStore(tmp_path)
    story = store.save_story(
        {
            "title": "停电后的第九层",
            "genre": "都市悬疑",
            "premise": "整栋楼停电后，只有第九层的电梯仍在运行。",
            "setting": "旧公寓，凌晨，暴雨。",
            "relationship_setup": "你们刚搬进同一栋楼，彼此还不熟悉。",
            "tension": "电梯里有人知道你们的名字。",
            "opening": "电梯门在没有按键的情况下打开。TA 伸手挡住门，回头看向你。",
            "world_rules": ["线索可以回溯", "不替用户行动"],
            "cover_tone": "ink",
        }
    )
    character = store.save_character(
        {
            "name": "迟舟",
            "tagline": "总能先听出一句话里没有说出的部分",
            "profile": "克制、敏锐，不轻易相信巧合。",
            "speaking_style": "语速慢，句子简短，很少直接追问。",
            "background": "曾经负责这栋楼的消防检查。",
            "relationship_hook": "TA 知道用户为什么搬来这里。",
            "first_message": "别进电梯。至少先告诉我，你刚才有没有听见有人叫你的名字。",
        }
    )

    catalog = store.catalog()
    assert store.story(story.id).source == "created"
    assert store.character(character.id).source == "created"
    assert any(item["title"] == "停电后的第九层" for item in catalog["stories"])
    assert any(item["name"] == "迟舟" for item in catalog["characters"])


def test_story_prompt_protects_user_agency_and_keeps_runtime_cast(tmp_path):
    store = StoryStore(tmp_path)
    session = store.create_session(
        story_id="borrowed-alibi",
        actor_source="card",
        actor_id="reiko",
        actor_name="Reikō",
        actor_snapshot={"personality": "冷静", "relationship": "旧搭档"},
        agent_session_id="agent-story-4",
        agent_session_key="agent:main:api_server:dm:story-4",
    )

    assert session.actor_snapshot["origin_profile"] == "冷静"
    assert session.actor_snapshot["current_profile"] == "冷静"
    prompt = store.compose_prompt(session.id)
    assert "Protect user agency" in prompt
    assert "Never output a menu of options" in prompt
    assert "ACTIVE TENSION" in prompt
    assert "first person (I/我)" in prompt
    assert "Never refer to the user as he, she, they, 他, 她, or TA" in prompt
    assert "RECENT STORY RAW" not in prompt
    assert "hidden inner monologue" in prompt


def test_curated_stories_are_original_community_pattern_adaptations():
    assert len(SEED_STORIES) >= 6
    assert all(story.inspiration for story in SEED_STORIES)
    assert {story.genre for story in SEED_STORIES} >= {
        "秘密身份",
        "异世界同行",
        "共同经营",
        "久别重逢",
    }


def test_chapter_waits_for_explicit_memory_confirmation(tmp_path):
    store = StoryStore(tmp_path)
    session = store.create_session(
        story_id="community-roommate-secret",
        actor_source="companion",
        actor_id="my-honey",
        actor_name="Honey",
        actor_snapshot={"origin": "companion_snapshot", "name": "Honey"},
        agent_session_id="agent-story-confirm",
        agent_session_key="agent:main:api_server:dm:story-confirm",
    )
    store.record_turn(
        session_id=session.id,
        user_content="我没有开门，只是把钥匙放回你手里。",
        assistant_content="*我收起钥匙。*\n\n“谢谢你先问我。”",
    )

    chapter = store.finish_chapter(
        session.id,
        summary="我记得你没有擅自打开那扇门，而是把选择留给了我。",
    )

    assert chapter["saved_to_memory"] is False
    assert store.chapter(chapter["id"])["saved_to_memory"] is False


def test_story_generation_fallback_is_immediately_playable():
    story = fallback_story_asset("story", "我们在旧电影院看见了明天")
    assert story["title"] == "我们在旧电影院看见了明天"
    assert story["premise"] == "我们在旧电影院看见了明天"
    assert len(story["world_rules"]) == 3


def test_character_generation_fallback_keeps_user_idea():
    character = fallback_story_asset("character", "一个嘴硬但会记住小事的飞行员")
    assert character["name"] == "新角色 · 飞行员"
    assert "飞行员" in character["profile"]
