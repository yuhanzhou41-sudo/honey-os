from __future__ import annotations

from contextlib import closing
from datetime import datetime, time, timedelta, timezone
import json
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import StudyPlanStatus, StudyTaskStatus
from .service import StudyService


def text(value, label: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise ValueError(f"{label}须填写，最多 {limit} 字。")
    return value.strip()


class StudyReview:
    """Practice and cards share the existing profile-local Study database."""

    def __init__(self, study: StudyService):
        self.study = study
        with closing(self._connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS study_review_questions (
                    id TEXT PRIMARY KEY, prompt TEXT NOT NULL, options TEXT NOT NULL,
                    correct INTEGER NOT NULL, explanation TEXT NOT NULL,
                    resource_id TEXT NOT NULL, source_title TEXT NOT NULL, excerpt TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS study_review_attempts (
                    id TEXT PRIMARY KEY, question_id TEXT NOT NULL REFERENCES study_review_questions(id),
                    choice INTEGER NOT NULL, correct INTEGER NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS study_review_attempt_question
                    ON study_review_attempts(question_id);
                CREATE TABLE IF NOT EXISTS study_review_cards (
                    id TEXT PRIMARY KEY, question_id TEXT REFERENCES study_review_questions(id),
                    resource_id TEXT NOT NULL, source_title TEXT NOT NULL,
                    front TEXT NOT NULL, back TEXT NOT NULL, excerpt TEXT NOT NULL,
                    UNIQUE(resource_id, front)
                );
                CREATE TABLE IF NOT EXISTS study_review_recalls (
                    id TEXT PRIMARY KEY, card_id TEXT NOT NULL REFERENCES study_review_cards(id),
                    response TEXT NOT NULL, rating INTEGER, created_at TEXT NOT NULL, due_at TEXT
                );
                CREATE INDEX IF NOT EXISTS study_review_recalls_card ON study_review_recalls(card_id);
                CREATE INDEX IF NOT EXISTS study_review_recalls_created ON study_review_recalls(created_at);
                CREATE INDEX IF NOT EXISTS study_review_attempts_created ON study_review_attempts(created_at);
                CREATE TABLE IF NOT EXISTS study_review_quizzes (
                    id TEXT PRIMARY KEY, question_ids TEXT NOT NULL, answers TEXT
                );
                CREATE TABLE IF NOT EXISTS study_review_question_sources (
                    question_id TEXT PRIMARY KEY REFERENCES study_review_questions(id),
                    kind TEXT NOT NULL, exam TEXT, year INTEGER, location TEXT,
                    UNIQUE(kind, exam, year, location)
                );
            """)

    def _connect(self):
        return self.study.repository._connect()

    def source(self, resource_id):
        resource_id = text(resource_id, "资料", 100)
        resource = self.study.get_resource(resource_id)
        # Reuse online/source verification; prose and evidence come from the index.
        self.study.build_chat_resource_context([resource_id])
        content = self.study.get_resource_content(resource_id)["extracted_text"]
        return resource, content

    @staticmethod
    def _question(row, *, answered=False):
        result = dict(row)
        result["options"] = json.loads(result["options"])
        if not answered:
            result.pop("correct")
            result.pop("explanation")
        return result

    def list_questions(self, *, wrong_only=False):
        with closing(self._connect()) as db:
            rows = db.execute("""
                SELECT q.*, s.kind, s.exam, s.year, s.location,
                    (SELECT a.correct FROM study_review_attempts a
                    WHERE a.question_id=q.id ORDER BY a.rowid DESC LIMIT 1) AS latest_correct
                FROM study_review_questions q
                LEFT JOIN study_review_question_sources s ON s.question_id=q.id ORDER BY q.rowid DESC
            """)
            return [self._question(row) for row in rows
                    if not wrong_only or row["latest_correct"] == 0]

    def create_question(self, payload):
        resource, content = self.source(payload.get("resource_id"))
        row = self.validate_question(payload, resource, content)
        with closing(self._connect()) as db, db:
            db.execute("INSERT INTO study_review_questions VALUES (?,?,?,?,?,?,?,?)", row)
        return row[0]

    @staticmethod
    def validate_question(payload, resource, content):
        if not isinstance(payload, dict):
            raise ValueError("题目格式无效。")
        prompt = text(payload.get("prompt"), "题干", 5000)
        options = payload.get("options")
        if not isinstance(options, list) or not 2 <= len(options) <= 6:
            raise ValueError("单选题须有 2 到 6 个选项。")
        options = [text(item, "选项", 1000) for item in options]
        if len(set(options)) != len(options):
            raise ValueError("选项须互不相同。")
        correct = payload.get("correct")
        if type(correct) is not int or not 0 <= correct < len(options):
            raise ValueError("请选择正确选项。")
        excerpt = text(payload.get("excerpt"), "出处原文", 1500)
        if excerpt not in content:
            raise ValueError("出处须逐字来自所选资料。")
        explanation = (payload.get("explanation") or "").strip() if isinstance(payload.get("explanation"), str) else ""
        if len(explanation) > 3000:
            raise ValueError("解析最多 3000 字。")
        return (uuid4().hex, prompt, json.dumps(options), correct, explanation,
                resource.id, resource.title, excerpt)

    def import_questions(self, payload):
        resource, content = self.source(payload.get("resource_id"))
        kind = payload.get("kind")
        rows = payload.get("questions")
        if kind not in ("past", "mock") or not isinstance(rows, list) or not 1 <= len(rows) <= 100:
            raise ValueError("请选择题型并提供 1 至 100 道题。")
        questions = []
        sources = []
        for entry in rows:
            row = self.validate_question(entry, resource, content)
            exam = year = location = None
            if kind == "past":
                exam = text(entry.get("exam"), "考试", 200)
                year = entry.get("year")
                location = text(entry.get("location"), "原题位置", 200)
                if type(year) is not int or not 1900 <= year <= datetime.now(timezone.utc).year:
                    raise ValueError("请填写有效的考试年份。")
                evidence = resource.title + "\n" + content
                if exam not in evidence or str(year) not in evidence:
                    raise ValueError("资料标题或正文须含所填的考试名称和年份。")
                if row[1] not in row[7] or any(option not in row[7] for option in json.loads(row[2])):
                    raise ValueError("真题出处原文须包含题干和全部选项。")
            questions.append(row)
            sources.append((row[0], kind, exam, year, location))
        with closing(self._connect()) as db, db:
            for row, provenance in zip(questions, sources):
                db.execute("INSERT INTO study_review_questions VALUES (?,?,?,?,?,?,?,?)", row)
                inserted = db.execute("""
                    INSERT INTO study_review_question_sources VALUES (?,?,?,?,?)
                    ON CONFLICT(kind, exam, year, location) DO NOTHING
                """, provenance)
                if not inserted.rowcount:
                    raise ValueError("同一考试、年份和原题位置已入库。")
        return {"imported": len(questions)}

    def _get(self, db, question_id):
        row = db.execute("""
            SELECT q.*, s.kind, s.exam, s.year, s.location FROM study_review_questions q
            LEFT JOIN study_review_question_sources s ON s.question_id=q.id WHERE q.id=?
        """, (question_id,)).fetchone()
        if row is None:
            raise KeyError(question_id)
        return row

    def attempt(self, question_id, choice, attempt_id):
        attempt_id = text(attempt_id, "作答编号", 100)
        with closing(self._connect()) as db, db:
            question = self._get(db, question_id)
            if type(choice) is not int or not 0 <= choice < len(json.loads(question["options"])):
                raise ValueError("请选择一个选项。")
            db.execute("INSERT OR IGNORE INTO study_review_attempts VALUES (?,?,?,?,?)",
                       (attempt_id, question_id, choice, choice == question["correct"],
                        datetime.now(timezone.utc).isoformat()))
            row = db.execute("SELECT * FROM study_review_attempts WHERE id=?", (attempt_id,)).fetchone()
            if row["question_id"] != question_id or row["choice"] != choice:
                raise ValueError("作答编号已用于其他提交，请刷新后重试。")
            return {"attempt": dict(row), "question": self._question(question, answered=True)}

    def history(self, question_id):
        with closing(self._connect()) as db:
            question = self._get(db, question_id)
            attempts = [dict(row) for row in db.execute(
                "SELECT * FROM study_review_attempts WHERE question_id=? ORDER BY rowid DESC",
                (question_id,),
            )]
            return {"attempts": attempts, "question": self._question(question, answered=bool(attempts))}

    def card_context(self, resource_id, question_id):
        question = None
        if question_id:
            with closing(self._connect()) as db:
                question = self._question(self._get(db, question_id), answered=True)
                wrong = db.execute("SELECT 1 FROM study_review_attempts WHERE question_id=? AND correct=0",
                                   (question_id,)).fetchone()
                if not wrong:
                    raise ValueError("请从已有错题生成闪卡。")
            resource_id = question["resource_id"]
        resource, content = self.source(resource_id)
        if question and question["excerpt"] not in content:
            raise ValueError("题目出处已更改，请选择当前资料重新整理。")
        return resource, content, question

    def validate_cards(self, rows, content):
        if not isinstance(rows, list) or not 1 <= len(rows) <= 8:
            raise ValueError("请选择 1 到 8 张闪卡。")
        result = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("闪卡格式无效。")
            card = {
                "front": text(row.get("front"), "卡片正面", 500),
                "back": text(row.get("back"), "卡片背面", 2000),
                "excerpt": text(row.get("excerpt"), "出处原文", 800),
            }
            if card["excerpt"] not in content:
                raise ValueError("闪卡出处须逐字来自所选资料。")
            result.append(card)
        return result

    def save_cards(self, resource_id, question_id, rows):
        resource, content, question = self.card_context(resource_id, question_id)
        cards = self.validate_cards(rows, content)
        with closing(self._connect()) as db, db:
            for card in cards:
                db.execute("""
                    INSERT INTO study_review_cards VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(resource_id, front) DO UPDATE SET
                      question_id=COALESCE(excluded.question_id, study_review_cards.question_id),
                      source_title=excluded.source_title, back=excluded.back, excerpt=excluded.excerpt
                """, (uuid4().hex, question["id"] if question else None, resource.id,
                      resource.title, card["front"], card["back"], card["excerpt"]))

    def list_cards(self):
        with closing(self._connect()) as db:
            return [dict(card) for card in db.execute(
                "SELECT * FROM study_review_cards ORDER BY rowid DESC"
            )]

    def daily_items(self, scope, kind):
        keyword = (scope.get("keyword") or "")
        if not isinstance(keyword, str) or len(keyword) > 500:
            raise ValueError("知识点最多 500 字。")
        keyword = keyword.strip().casefold()
        resource_id = scope.get("resource_id")
        wrong = scope.get("wrong") is True
        kind_filter = scope.get("kind")
        if not (keyword or resource_id or wrong or (kind == "quiz" and kind_filter)):
            raise ValueError("请选择当天的知识点、资料或错题。")
        questions = self.list_questions()
        by_id = {question["id"]: question for question in questions}
        if kind == "quiz":
            items = questions
        else:
            items = self.list_cards()
        matches = []
        for item in items:
            if resource_id and item["resource_id"] != resource_id:
                continue
            question = item if kind == "quiz" else by_id.get(item["question_id"], {})
            if kind == "quiz" and kind_filter and question.get("kind") != kind_filter:
                continue
            if wrong and question.get("latest_correct") != 0:
                continue
            fields = [item.get(key, "") for key in ("front", "back", "prompt", "source_title", "excerpt")]
            fields.append(question.get("prompt", ""))
            if keyword and not any(keyword in field.casefold() for field in fields):
                continue
            matches.append(item)
        return matches

    def draw_card(self, scope):
        matches = self.daily_items(scope, "card")
        with closing(self._connect()) as db:
            due = {row["card_id"]: row["due_at"] for row in db.execute("""
                SELECT card_id, due_at FROM study_review_recalls
                WHERE rating IS NOT NULL ORDER BY rowid
            """)}
        now = datetime.now(timezone.utc).isoformat()
        eligible = [card for card in matches if due.get(card["id"], "") <= now]
        if not eligible:
            return {"card": None, "matched": len(matches)}
        card = min(eligible, key=lambda item: (item["id"] not in due, due.get(item["id"], "")))
        return {"card": {"id": card["id"], "front": card["front"]}, "matched": len(matches)}

    def recall(self, card_id, payload):
        recall_id = text(payload.get("id"), "复述编号", 100)
        response = text(payload.get("response"), "复述内容", 5000)
        with closing(self._connect()) as db, db:
            card = db.execute("SELECT * FROM study_review_cards WHERE id=?", (card_id,)).fetchone()
            if card is None:
                raise KeyError(card_id)
            db.execute("""
                INSERT INTO study_review_recalls (id, card_id, response, created_at)
                VALUES (?,?,?,?) ON CONFLICT(id) DO NOTHING
            """, (recall_id, card_id, response, datetime.now(timezone.utc).isoformat()))
            row = db.execute("SELECT * FROM study_review_recalls WHERE id=?", (recall_id,)).fetchone()
            if row["card_id"] != card_id or row["response"] != response:
                raise ValueError("复述编号已用于其他提交。")
            return {"card": dict(card), "recall": dict(row)}

    def assess(self, recall_id, rating):
        if type(rating) is not int or rating not in (0, 1, 2):
            raise ValueError("请选择掌握程度。")
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM study_review_recalls WHERE id=?", (recall_id,)).fetchone()
            if row is None:
                raise KeyError(recall_id)
            if row["rating"] is None:
                previous = db.execute("""
                    SELECT rating, due_at, created_at FROM study_review_recalls
                    WHERE card_id=? AND rating IS NOT NULL ORDER BY rowid DESC LIMIT 1
                """, (row["card_id"],)).fetchone()
                interval = (timedelta(minutes=10), timedelta(days=1), timedelta(days=3))[rating]
                if rating == 2 and previous and previous["rating"] == 2:
                    previous_interval = datetime.fromisoformat(previous["due_at"]) - datetime.fromisoformat(previous["created_at"])
                    interval = min(timedelta(days=30), max(interval, previous_interval * 2))
                due = (datetime.now(timezone.utc) + interval).isoformat()
                db.execute("UPDATE study_review_recalls SET rating=?, due_at=? WHERE id=?", (rating, due, recall_id))
            elif row["rating"] != rating:
                raise ValueError("这次复述已记录掌握程度。")
            return dict(db.execute("SELECT * FROM study_review_recalls WHERE id=?", (recall_id,)).fetchone())

    def recall_history(self):
        with closing(self._connect()) as db:
            return [dict(row) for row in db.execute("""
                SELECT r.*, c.front FROM study_review_recalls r
                JOIN study_review_cards c ON c.id=r.card_id ORDER BY r.rowid DESC LIMIT 100
            """)]

    def daily_summary(self, zone_name):
        try:
            zone = ZoneInfo(text(zone_name, "时区", 100))
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("无法识别当前时区。") from exc
        day = datetime.now(zone).date()
        start, end = (
            datetime.combine(value, time.min, zone).astimezone(timezone.utc).isoformat()
            for value in (day, day + timedelta(days=1))
        )
        tasks = [
            {"id": task.id, "title": task.title, "status": task.status.value, "plan": plan.title}
            for plan in self.study.list_plans() if plan.status != StudyPlanStatus.ARCHIVED
            for task in plan.tasks if task.scheduled_date == day
        ]
        with closing(self._connect()) as db:
            attempts, correct = db.execute("""
                SELECT COUNT(*), COALESCE(SUM(correct), 0) FROM study_review_attempts
                WHERE created_at >= ? AND created_at < ?
            """, (start, end)).fetchone()
            recalls, mastered = db.execute("""
                SELECT COUNT(*), COUNT(CASE WHEN rating=2 THEN 1 END) FROM study_review_recalls
                WHERE created_at >= ? AND created_at < ?
            """, (start, end)).fetchone()
        pending = [task for task in tasks if task["status"] != StudyTaskStatus.COMPLETED]
        suggestions = []
        if pending:
            suggestions.append("核对下列未完成任务，从中选一个优先完成，或在计划中确认调整日期。")
        if attempts and correct / attempts < 0.8:
            suggestions.append("今日正确率低于 80%，建议在安排新内容前先重做错题。")
        if recalls > mastered:
            suggestions.append("还有复述未达到已掌握，可在到期后重新抽背。")
        return {"date": day.isoformat(), "completed": len(tasks) - len(pending), "tasks": len(tasks),
                "pending": pending, "attempts": attempts, "correct": correct,
                "recalls": recalls, "mastered": mastered, "suggestions": suggestions}

    def create_quiz(self, scope):
        count = scope.get("count")
        if type(count) is not int or not 10 <= count <= 20:
            raise ValueError("请选择 10 至 20 题。")
        matches = self.daily_items(scope, "quiz")
        if len(matches) < count:
            return {"id": None, "available": len(matches), "questions": []}
        questions = matches[:count]
        quiz_id = uuid4().hex
        with closing(self._connect()) as db, db:
            db.execute("INSERT INTO study_review_quizzes (id, question_ids) VALUES (?,?)",
                       (quiz_id, json.dumps([question["id"] for question in questions])))
        return {"id": quiz_id, "available": len(matches), "questions": [
            {key: question[key] for key in ("id", "prompt", "options", "kind", "exam", "year", "location")}
            for question in questions
        ]}

    def submit_quiz(self, quiz_id, choices):
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            quiz = db.execute("SELECT * FROM study_review_quizzes WHERE id=?", (quiz_id,)).fetchone()
            if quiz is None:
                raise KeyError(quiz_id)
            ids = json.loads(quiz["question_ids"])
            if not isinstance(choices, list) or len(choices) != len(ids):
                raise ValueError("请完成整套题后提交。")
            if quiz["answers"] is not None:
                result = json.loads(quiz["answers"])
                if choices != [item["choice"] for item in result["results"]]:
                    raise ValueError("这套练习已经提交。")
                return result
            results = []
            now = datetime.now(timezone.utc).isoformat()
            for question_id, choice in zip(ids, choices):
                question = self._question(self._get(db, question_id), answered=True)
                if type(choice) is not int or not 0 <= choice < len(question["options"]):
                    raise ValueError("请为每道题选择一个选项。")
                correct = choice == question["correct"]
                db.execute("INSERT INTO study_review_attempts VALUES (?,?,?,?,?)",
                           (uuid4().hex, question_id, choice, correct, now))
                results.append({"question": question, "choice": choice, "correct": correct})
            result = {"score": sum(item["correct"] for item in results), "results": results}
            db.execute("UPDATE study_review_quizzes SET answers=? WHERE id=?", (json.dumps(result), quiz_id))
            return result
