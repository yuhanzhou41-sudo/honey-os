from honeyos.companion.reply_style import reply_style_context
from honeyos.core.state import SessionDB


def test_style_feedback_is_topic_scoped_and_disappears_on_retraction(tmp_path):
    db = SessionDB(tmp_path / "state.db")
    try:
        db.create_session("one", "api_server")
        db.create_session("two", "api_server")
        db.append_message("one", "user", "Explain how a backup can be verified.")
        row = db.append_message("one", "assistant", "Start by checking its hash.")
        db.set_message_reaction("one", row, "👍", note="I like the direct phrasing.", toggle=False)
        assert "direct phrasing" in reply_style_context(db, "one", "How should I verify the backup?")
        assert not reply_style_context(db, "one", "Would you like to go for a walk?")
        assert not reply_style_context(db, "two", "How should I verify the backup?")
        db.set_message_reaction("one", row, None, toggle=False)
        assert not reply_style_context(db, "one", "How should I verify the backup?")
    finally:
        db.close()


def test_style_feedback_crosses_sessions_in_owner_lane_only(tmp_path):
    db = SessionDB(tmp_path / "state.db")
    try:
        for session, user in (("old", "alice"), ("new", "alice"), ("other", "bob")):
            db.create_session(session, "api_server", session_key="same", user_id=user, chat_id="chat")
        db.append_message("old", "user", "Explain how a backup can be verified.")
        row = db.append_message("old", "assistant", "Start by checking its hash.")
        db.set_message_reaction("old", row, "👎", note="Show an example.", toggle=False)
        assert "Show an example." in reply_style_context(db, "new", "How should I verify the backup?")
        assert not reply_style_context(db, "other", "How should I verify the backup?")
    finally:
        db.close()


def test_liked_reply_is_the_only_eligible_personality_source(tmp_path):
    from honeyos.companion.personality_candidates import PersonalityCandidateStore
    from honeyos.companion.personality_observation_hook import capture_liked_reply, liked_observation_ids

    db = SessionDB(tmp_path / "state.db")
    try:
        db.create_session("one", "api_server")
        db.append_message("one", "user", "Explain how a backup can be verified.")
        row = db.append_message("one", "assistant", "Start by checking its hash.")
        store = PersonalityCandidateStore(tmp_path, liked_only=True)
        assert not capture_liked_reply(tmp_path, db, "one", row)
        db.set_message_reaction("one", row, "👎", toggle=False)
        assert not capture_liked_reply(tmp_path, db, "one", row)
        db.set_message_reaction("one", row, "👍", toggle=False)
        observation = capture_liked_reply(tmp_path, db, "one", row)
        assert observation and capture_liked_reply(tmp_path, db, "one", row) == observation
        pending = store.list_pending_observations()
        assert liked_observation_ids(tmp_path, pending) == {observation}
        db.set_message_reaction("one", row, None, toggle=False)
        assert liked_observation_ids(tmp_path, pending) == set()
    finally:
        db.close()


def test_intention_is_self_authored_recent_and_respects_the_user(tmp_path):
    from honeyos.companion.turn_intention import pending_intention_context

    db = SessionDB(tmp_path / "state.db")
    try:
        db.create_session("one", "api_server")
        db.append_message("one", "user", "我想继续聊花园。")
        db.append_message("one", "assistant", "你想聊花园，我理解。")
        assert not pending_intention_context(db, "one", "继续")
        db.append_message("one", "assistant", "我想下次聊花园里种的薄荷。")
        assert "薄荷" in pending_intention_context(db, "one", "继续")
        assert not pending_intention_context(db, "one", "今天怎么备份文件？")
        assert not pending_intention_context(db, "one", "花园的事别再提")
    finally:
        db.close()
