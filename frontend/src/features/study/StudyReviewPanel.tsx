import { useEffect, useRef, useState, type FormEvent } from "react";
import QuestionIntakePanel from "./QuestionIntakePanel";
import { getStudyResourceContent, listStudyResources, type StudyResource, type StudyTask } from "../../api/study";
import {
  fileData, studyReview, type AnsweredQuestion, type Attempt, type CardPreview,
  type CardSource, type DailyScope, type DailySummary, type Question, type Quiz, type QuizResult, type Recall,
  type SavedCard, type StudyAnswer,
} from "../../api/study-review";

const field = "block w-full rounded border border-[var(--border)] bg-[var(--background)] p-2";
const action = "rounded border border-[var(--border)] px-3 py-1.5 disabled:opacity-50";
const panel = "space-y-3 rounded border border-[var(--border)] p-3";

function message(error: unknown) {
  return error instanceof Error ? error.message : "请求未完成，请重试。";
}

function useResources() {
  const [resources, setResources] = useState<StudyResource[]>([]);
  const [sourceError, setSourceError] = useState("");
  useEffect(() => {
    let active = true;
    listStudyResources()
      .then(value => { if (active) setResources(value.resources); })
      .catch(error => { if (active) setSourceError(message(error)); });
    return () => { active = false; };
  }, []);
  return { resources, sourceError };
}

function ResourcePicker({ resources, value, onChange, optional = false }: {
  resources: StudyResource[]; value: string; onChange: (value: string) => void; optional?: boolean;
}) {
  return (
    <label className="block">出处资料
      <select className={field} value={value} onChange={event => onChange(event.target.value)} required={!optional}>
        <option value="">{optional ? "无需参考资料" : "选择 Study 资料"}</option>
        {resources.map(resource => <option key={resource.id} value={resource.id}>{resource.title}</option>)}
      </select>
    </label>
  );
}

function Evidence({ title, excerpt }: { title: string; excerpt: string }) {
  return <blockquote className="whitespace-pre-wrap border-l-2 border-[var(--border)] pl-2 text-sm">
    <strong>{title}</strong><br />{excerpt}
  </blockquote>;
}

function provenance(question: Pick<Question, "kind" | "exam" | "year" | "location">) {
  if (question.kind === "past") return `${question.year} 年 ${question.exam} · ${question.location}`;
  if (question.kind === "mock") return "模拟题";
  if (question.kind === "web") return "网络题目 · 真题待核验";
  if (question.kind === "upload") return "上传题目";
  return "";
}

export default function StudyReviewPanel({ todayTasks = [], planId }: { todayTasks?: StudyTask[]; planId?: string }) {
  const { resources, sourceError } = useResources();
  const [questions, setQuestions] = useState<Question[]>([]);
  const [cards, setCards] = useState<SavedCard[]>([]);
  const [mode, setMode] = useState<"practice" | "wrong" | "cards" | "daily">("practice");
  const [active, setActive] = useState<Question>();
  const [choice, setChoice] = useState<number>();
  const [feedback, setFeedback] = useState<{ attempt: Attempt; question: AnsweredQuestion }>();
  const [history, setHistory] = useState<{ attempts: Attempt[]; question: AnsweredQuestion }>();
  const [pendingAttempt, setPendingAttempt] = useState<{ choice: number; id: string }>();
  const [resourceId, setResourceId] = useState("");
  const [sourceText, setSourceText] = useState("");
  const [cardResource, setCardResource] = useState("");
  const [cardSegment, setCardSegment] = useState(1);
  const [preview, setPreview] = useState<CardPreview>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([studyReview.questions(), studyReview.cards()]).then(([q, c]) => {
      if (active) { setQuestions(q.questions); setCards(c.cards); }
    }).catch(error => { if (active) setError(message(error)); });
    return () => { active = false; };
  }, []);

  async function work(action: () => Promise<void>) {
    setError("");
    setNotice("");
    setBusy(true);
    try { await action(); } catch (error) { setError(message(error)); }
    finally { setBusy(false); }
  }

  function openQuestion(question: Question) {
    setActive(question);
    setChoice(undefined);
    setFeedback(undefined);
    setPendingAttempt(undefined);
    setHistory(undefined);
  }

  function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    void work(async () => {
      const result = await studyReview.createQuestion({
        resource_id: resourceId, prompt: String(data.get("prompt")),
        options: String(data.get("options")).split(/\r?\n/).map(value => value.trim()).filter(Boolean),
        correct: Number(data.get("correct")) - 1, explanation: String(data.get("explanation")),
        excerpt: String(data.get("excerpt")),
      });
      const resultList = (await studyReview.questions()).questions;
      setQuestions(resultList);
      const created = resultList.find(question => question.id === result.id);
      if (created) openQuestion(created);
      form.reset();
      setResourceId("");
      setSourceText("");
      setNotice("题目已保存。");
    });
  }

  async function submit() {
    if (!active || choice === undefined) return;
    const attempt = pendingAttempt?.choice === choice ? pendingAttempt : { choice, id: crypto.randomUUID() };
    setPendingAttempt(attempt);
    await work(async () => {
      const result = await studyReview.attempt(active.id, choice, attempt.id, planId);
      setFeedback(result);
      setHistory(undefined);
      setQuestions(previous => previous.map(item => item.id === active.id
        ? { ...item, latest_correct: result.attempt.correct } : item));
      setPendingAttempt(undefined);
    });
  }

  async function generate(source: CardSource) {
    await work(async () => {
      setPreview(await studyReview.preview(source));
      setMode("cards");
    });
  }

  function editCard(index: number, fieldName: "front" | "back" | "excerpt", value: string) {
    setPreview(previous => previous && ({
      ...previous, cards: previous.cards.map((card, i) => i === index ? { ...card, [fieldName]: value } : card),
    }));
  }

  return <div className="space-y-4">
    <nav aria-label="复习类型" className="flex flex-wrap gap-2">
      {([["practice", "题库"], ["wrong", "错题"], ["cards", "知识点闪卡"], ["daily", "今日复习"]] as const).map(([key, label]) =>
        <button key={key} className={action} type="button" disabled={busy} aria-pressed={key === mode}
          onClick={() => {
            setMode(key);
            setActive(undefined);
            if (mode === "daily") void work(async () => setQuestions((await studyReview.questions()).questions));
          }}>{label}</button>)}
    </nav>
    {(error || sourceError) && <p role="alert">{error || sourceError}</p>}
    {notice && <p role="status">{notice}</p>}
    {busy && <p role="status">正在处理…</p>}

    {mode === "practice" && <QuestionIntakePanel planId={planId} tasks={todayTasks}
      onSaved={() => studyReview.questions().then(value => setQuestions(value.questions))} />}
    {mode === "practice" && <details className={panel}>
      <summary>新增单选题</summary>
      <form className="space-y-2" onSubmit={create}>
        <ResourcePicker resources={resources} value={resourceId} onChange={value => { setResourceId(value); setSourceText(""); }} />
        <button type="button" className={action} disabled={!resourceId || busy} onClick={() =>
          void work(async () => setSourceText((await getStudyResourceContent(resourceId)).content.extracted_text))
        }>查看资料正文</button>
        {sourceText && <pre className="max-h-48 overflow-auto whitespace-pre-wrap text-sm">{sourceText}</pre>}
        <label className="block">题干<textarea className={field} name="prompt" required maxLength={5000} /></label>
        <label className="block">选项（每行一个）<textarea className={field} name="options" required /></label>
        <label className="block">正确选项序号<input className={field} name="correct" type="number" min="1" max="6" defaultValue="1" required /></label>
        <label className="block">解析（选填）<textarea className={field} name="explanation" maxLength={3000} /></label>
        <label className="block">出处原文<textarea className={field} name="excerpt" required maxLength={1500} /></label>
        <button className={action} disabled={busy || !resourceId}>保存题目</button>
      </form>
    </details>}
    {mode === "practice" && <QuestionImport resources={resources} onSaved={() =>
      studyReview.questions().then(value => setQuestions(value.questions))} />}

    {mode === "daily" && <DailyReview resources={resources} tasks={todayTasks} planId={planId} />}

    {(mode === "practice" || mode === "wrong") && <>
      <ul className="space-y-2">{questions.filter(item => mode !== "wrong" || item.latest_correct === 0)
        .map(item => <li key={item.id}>
          <button className={action} disabled={busy} onClick={() => openQuestion(item)}>
            {provenance(item) && <small className="block">{provenance(item)}</small>}{item.prompt}
          </button>
        </li>)}</ul>
      {!questions.some(item => mode !== "wrong" || item.latest_correct === 0) &&
        <p>{mode === "wrong" ? "暂无待复习的错题。" : "题库暂无练习题。"}</p>}
      {active && <section className={panel}>
        <h3 className="font-semibold">{active.prompt}</h3>
        {active.source_url && <a className="underline" href={active.source_url} target="_blank" rel="noreferrer">打开题目来源</a>}
        <fieldset disabled={busy || Boolean(feedback)}>
          <legend>选择答案</legend>
          {active.options.map((option, index) => <label className="block" key={index}>
            <input type="radio" name="answer" checked={choice === index} onChange={() => setChoice(index)} /> {option}
          </label>)}
        </fieldset>
        {!feedback && <button className={action} disabled={choice === undefined || busy} onClick={() => void submit()}>提交作答</button>}
        {feedback && <>
          <p role="status">{feedback.attempt.correct ? "回答正确" : "回答错误"}。正确答案：{active.options[feedback.question.correct ?? -1]}</p>
          {feedback.question.explanation && <p>{feedback.question.explanation}</p>}
          <Evidence title={active.source_title} excerpt={active.excerpt} />
          <button className={action} disabled={busy} onClick={() => openQuestion(active)}>重做本题</button>
          {!feedback.attempt.correct && <button className={action} disabled={busy} onClick={() => void generate({ question_id: active.id })}>从错题生成闪卡</button>}
        </>}
        {!feedback && active.latest_correct === 0 && <button className={action} disabled={busy}
          onClick={() => void generate({ question_id: active.id })}>从错题生成闪卡</button>}
        <button className={action} disabled={busy} onClick={() => void work(async () => setHistory(await studyReview.history(active.id,planId)))}>查看作答记录</button>
        {history && (history.attempts.length
          ? <ol className="list-decimal pl-5">{history.attempts.map(a => <li key={a.id}>
            {new Date(a.created_at).toLocaleString()} · {active.options[a.choice]} · {a.correct ? "答对" : "答错"}
          </li>)}</ol> : <p>还没有作答记录。</p>)}
      </section>}
    </>}

    {mode === "cards" && <>
      <header>
        <h3 className="font-semibold">知识点闪卡</h3>
        <p className="text-sm text-[var(--foreground-muted)]">
          从资料整理知识点，或从答错的题生成卡片。复习时先看正面回忆，再翻开背面核对知识点和出处。
        </p>
      </header>
      <section className={panel}>
        <ResourcePicker resources={resources} value={cardResource} onChange={value => {
          setCardResource(value);
          setCardSegment(1);
        }} />
        <SegmentInput value={cardSegment} onChange={setCardSegment} />
        <button className={action} disabled={busy || !cardResource}
          onClick={() => void generate({ resource_id: cardResource, segment: cardSegment })}>整理成闪卡</button>
      </section>
      {preview && <section className={panel}>
        <h3>闪卡预览 · {preview.source_title}</h3>
        {preview.partial && <p>资料第 {preview.segment} / {preview.segments} 段，每段最多 1,800 字。</p>}
        {preview.cards.map((card, index) => <div className={panel} key={index}>
          <label className="block">正面<textarea className={field} value={card.front} disabled={busy}
            onChange={event => editCard(index, "front", event.target.value)} /></label>
          <label className="block">背面<textarea className={field} value={card.back} disabled={busy}
            onChange={event => editCard(index, "back", event.target.value)} /></label>
          <label className="block">出处原文<textarea className={field} value={card.excerpt} disabled={busy}
            onChange={event => editCard(index, "excerpt", event.target.value)} /></label>
          <button type="button" className={action} disabled={busy} onClick={() => setPreview({
            ...preview, cards: preview.cards.filter((_, i) => i !== index),
          })}>移除这张草稿</button>
        </div>)}
        <button className={action} disabled={busy || !preview.cards.length} onClick={() => void work(async () => {
          const { resource_id, question_id, cards } = preview;
          setCards((await studyReview.saveCards({ resource_id, question_id }, cards)).cards);
          setPreview(undefined);
          setNotice("闪卡已保存。");
        })}>确认保存闪卡</button>
        <button className={action} disabled={busy} onClick={() => setPreview(undefined)}>取消预览</button>
      </section>}
      {cards.map(card => <details key={card.id} className={panel + " bg-[var(--surface-raised)]"}>
        <summary className="cursor-pointer">
          <span className="text-xs text-[var(--foreground-muted)]">正面 · {card.question_id ? "来自错题" : "来自资料"}</span>
          <span className="block whitespace-pre-wrap text-base font-medium">{card.front}</span>
          <span className="text-xs text-[var(--foreground-muted)]">点击翻看背面</span>
        </summary>
        <div className="space-y-2 border-t border-[var(--border)] pt-3">
          <p className="text-xs text-[var(--foreground-muted)]">背面 · 知识点</p>
          <p className="whitespace-pre-wrap">{card.back}</p>
          <Evidence title={card.source_title} excerpt={card.excerpt} />
        </div>
      </details>)}
      {!cards.length && <p>暂无已保存闪卡。</p>}
    </>}
  </div>;
}

const mastery = ["未掌握", "部分掌握", "已掌握"];

function SegmentInput({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  return <label className="block">资料片段（每 1,800 字一段）
    <input className={field} type="number" min="1" step="1" value={value}
      onChange={event => onChange(Number(event.target.value))} />
  </label>;
}

function QuestionImport({ resources, onSaved }: { resources: StudyResource[]; onSaved: () => Promise<void> }) {
  const [resource, setResource] = useState("");
  const [kind, setKind] = useState<"past" | "mock">("past");
  const [segment, setSegment] = useState(1);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try { await action(); } catch (failure) { setError(message(failure)); }
    finally { setBusy(false); }
  }

  return <details className={panel}>
    <summary>从资料库批量导入</summary>
    <fieldset className="space-y-2" disabled={busy}>
      <ResourcePicker resources={resources} value={resource} onChange={value => {
        setResource(value);
        setDraft("");
        setSegment(1);
      }} />
      <label className="block">题型
        <select className={field} value={kind} onChange={event => {
          setKind(event.target.value === "mock" ? "mock" : "past");
          setDraft("");
        }}><option value="past">历年真题</option><option value="mock">模拟题</option></select>
      </label>
      {kind === "mock" && <>
        <SegmentInput value={segment} onChange={setSegment} />
        <button className={action} disabled={!resource} onClick={() => void run(async () => {
          const generated = await studyReview.previewQuestions(resource, segment);
          setDraft(JSON.stringify(generated.questions, null, 2));
          setNotice(`片段 ${segment} / ${generated.segments}。请核对题目、答案和引用。`);
        })}>用本机 Qwen 生成草稿</button>
      </>}
      <label className="block">题目 JSON
        <textarea className={field} rows={8} value={draft} onChange={event => setDraft(event.target.value)} />
      </label>
      <p className="text-sm">使用 JSON 数组。题目填写 prompt、options、从 0 开始的 correct、explanation 和 excerpt。
        {kind === "past" && "真题另填 exam、year 和 location，并让 excerpt 包含原题题干和选项。"}
      </p>
      <button className={action} disabled={!resource || !draft.trim()} onClick={() => void run(async () => {
        let questions: unknown;
        try { questions = JSON.parse(draft); } catch { throw new Error("题目 JSON 格式有误。"); }
        const saved = await studyReview.importQuestions(resource, kind, questions);
        setDraft("");
        setNotice(`已入库 ${saved.imported} 道题。`);
        await onSaved();
      })}>确认入库</button>
    </fieldset>
    {busy && <p role="status">正在处理…</p>}
    {notice && <p role="status">{notice}</p>}
    {error && <p role="alert">{error}</p>}
  </details>;
}

function DailyReview({ resources, tasks, planId }: { resources: StudyResource[]; tasks: StudyTask[]; planId?: string }) {
  const [scope, setScope] = useState<DailyScope>({ keyword: "", resource_id: "", wrong: false });
  const [count, setCount] = useState(10);
  const [card, setCard] = useState<Pick<SavedCard, "id" | "front">>();
  const [response, setResponse] = useState("");
  const [recallId, setRecallId] = useState("");
  const [revealed, setRevealed] = useState<{ card: SavedCard; recall: Recall }>();
  const [history, setHistory] = useState<(Recall & { front: string; archived?: number })[]>();
  const [summary, setSummary] = useState<DailySummary>();
  const [quiz, setQuiz] = useState<Quiz>();
  const [choices, setChoices] = useState<Record<string, number>>({});
  const [result, setResult] = useState<QuizResult>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const ready = Boolean(scope.keyword.trim() || scope.resource_id || scope.wrong);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try { await action(); } catch (failure) { setError(message(failure)); }
    finally { setBusy(false); }
  }

  function draw() {
    void run(async () => {
      const next = await studyReview.draw(scope);
      setCard(next.card ?? undefined);
      setRevealed(undefined);
      setResponse("");
      setRecallId(crypto.randomUUID());
      if (!next.card) setNotice(next.matched ? "该范围的闪卡均未到复习时间。" : "该范围没有闪卡。");
    });
  }

  return <section className={panel}>
    <button className={action} disabled={busy} onClick={() => void run(async () =>
      setSummary(await studyReview.summary(planId)))}>查看今日复盘</button>
    {summary && <section className={panel} aria-label="今日复盘">
      <h3 className="font-semibold">{summary.date} 学习复盘</h3>
      <p>任务完成 {summary.completed} / {summary.tasks} · 答对 {summary.correct} / {summary.attempts}
        {" · "}抽背掌握 {summary.mastered} / {summary.recalls}</p>
      {summary.suggestions.map(item => <p key={item}>{item}</p>)}
      {summary.pending.length > 0 && <ul className="list-disc pl-5">
        {summary.pending.map(task => <li key={task.id}>{task.plan} · {task.title}</li>)}
      </ul>}
    </section>}
    <fieldset disabled={busy} className="space-y-2">
      <legend>今日学习范围</legend>
      {tasks.length > 0 && <label className="block">从今日任务填写知识点
        <select className={field} value="" onChange={event => {
          const task = tasks.find(item => item.id === event.target.value);
          if (task) setScope({ ...scope, keyword: task.title });
        }}>
          <option value="">选择今日任务</option>
          {tasks.map(task => <option key={task.id} value={task.id}>{task.title}</option>)}
        </select>
      </label>}
      <label className="block">知识点
        <input className={field} value={scope.keyword} maxLength={500}
          onChange={event => setScope({ ...scope, keyword: event.target.value })} />
      </label>
      <label className="block">复习资料
        <select className={field} value={scope.resource_id}
          onChange={event => setScope({ ...scope, resource_id: event.target.value })}>
          <option value="">所有资料</option>
          {resources.map(resource => <option key={resource.id} value={resource.id}>{resource.title}</option>)}
        </select>
      </label>
      <label className="block">
        <input type="checkbox" checked={scope.wrong}
          onChange={event => setScope({ ...scope, wrong: event.target.checked })} /> 只复习当前错题
      </label>
      <button className={action} disabled={!ready || Boolean(revealed && revealed.recall.rating === null)}
        onClick={draw}>{revealed ? "抽下一张" : "抽背到期闪卡"}</button>
      <label className="block">练习题量
        <select className={field} value={count} onChange={event => setCount(Number(event.target.value))}>
          {Array.from({ length: 11 }, (_, index) => index + 10).map(size => <option key={size}>{size}</option>)}
        </select>
      </label>
      <label className="block">练习题型
        <select className={field} value={scope.kind ?? ""} onChange={event => setScope({ ...scope, kind: event.target.value })}>
          <option value="">全部</option><option value="past">历年真题</option><option value="mock">模拟题</option>
        </select>
      </label>
      <button className={action} disabled={!ready && !scope.kind} onClick={() => void run(async () => {
        const next = await studyReview.quiz(scope, count);
        setQuiz(next.id ? next : undefined);
        setChoices({});
        setResult(undefined);
        if (!next.id) setNotice(`该范围有 ${next.available} 道题，所选题量为 ${count}。`);
      })}>组卷</button>
    </fieldset>
    {error && <p role="alert">{error}</p>}
    {(busy || notice) && <p role="status">{busy ? "正在处理…" : notice}</p>}
    {card && <section className={panel}>
      <h3 className="font-semibold whitespace-pre-wrap">{card.front}</h3>
      {!revealed && <>
        <label className="block">先复述你的答案
          <textarea className={field} value={response} maxLength={5000} disabled={busy}
            onChange={event => { setResponse(event.target.value); setRecallId(crypto.randomUUID()); }} />
        </label>
        <button className={action} disabled={busy || !response.trim()} onClick={() => void run(async () => {
          setRevealed(await studyReview.recall(card.id, recallId, response, planId));
          setHistory(undefined);
        })}>提交复述并核对</button>
      </>}
      {revealed && <>
        <p className="whitespace-pre-wrap">你的复述：{revealed.recall.response}</p>
        <p className="whitespace-pre-wrap">标准知识点：{revealed.card.back}</p>
        <Evidence title={revealed.card.source_title} excerpt={revealed.card.excerpt} />
        {revealed.recall.rating === null ? <fieldset disabled={busy} className="flex flex-wrap gap-2">
          <legend>记录掌握程度</legend>
          {mastery.map((label, rating) => <button key={label} className={action} onClick={() => void run(async () => {
            setRevealed({ ...revealed, recall: await studyReview.rate(revealed.recall.id, rating,planId) });
            setHistory(undefined);
          })}>{label}</button>)}
        </fieldset> : <p role="status">{mastery[revealed.recall.rating]} · 下次复习 {new Date(revealed.recall.due_at!).toLocaleString()}</p>}
      </>}
    </section>}
    <button className={action} disabled={busy} onClick={() => void run(async () =>
      setHistory((await studyReview.recalls(planId)).recalls))}>查看抽背记录</button>
    {history && (history.length ? <ol className="space-y-2">{history.map(entry => <li key={entry.id} className={panel}>
      <strong>{entry.front}</strong>
      <p className="whitespace-pre-wrap">{entry.response}</p>
      <p>{new Date(entry.created_at).toLocaleString()} · {entry.rating === null ? "待自评" : mastery[entry.rating]}</p>
      {entry.rating === null && !entry.archived && <button className={action} disabled={busy}
        onClick={() => void run(async () => {
          const saved = await studyReview.recall(entry.card_id, entry.id, entry.response, planId);
          setCard(saved.card);
          setRevealed(saved);
          setHistory(undefined);
        })}>继续核对并自评</button>}
    </li>)}</ol> : <p>还没有抽背记录。</p>)}
    {quiz?.id && <section className={panel}>
      <h3 className="font-semibold">整套练习 · {quiz.questions.length} 题</h3>
      {result && <p role="status">得分 {result.score} / {result.results.length}</p>}
      {quiz.questions.map((question, index) => {
        const graded = result?.results[index];
        return <fieldset className={panel} key={question.id} disabled={busy || Boolean(result)}>
          <legend>{index + 1}. {question.prompt}</legend>
          {provenance(question) && <p className="text-sm">{provenance(question)}</p>}
          {question.options.map((option, choice) => <label className="block" key={choice}>
            <input type="radio" name={question.id} checked={choices[question.id] === choice}
              onChange={() => setChoices({ ...choices, [question.id]: choice })} /> {option}
          </label>)}
          {graded && <>
            <p>{graded.correct ? "回答正确" : "回答错误"}。正确答案：{question.options[graded.question.correct ?? -1]}</p>
            {graded.question.explanation && <p>{graded.question.explanation}</p>}
            <Evidence title={graded.question.source_title} excerpt={graded.question.excerpt} />
            {graded.question.source_url && <a className="underline" href={graded.question.source_url}
              target="_blank" rel="noreferrer">打开题目来源</a>}
          </>}
        </fieldset>;
      })}
      {!result && <button className={action} disabled={busy || Object.keys(choices).length !== quiz.questions.length}
        onClick={() => void run(async () => {
          setResult(await studyReview.submitQuiz(quiz.id!, quiz.questions.map(question => choices[question.id]), planId));
        })}>提交整套练习</button>}
    </section>}
  </section>;
}

export function StudyQuestionDialog({ onClose }: { onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const node = dialog.current;
    node?.showModal();
    return () => node?.close();
  }, []);

  function dismiss() {
    dialog.current?.close();
    onClose();
  }

  return (
    <dialog ref={dialog} aria-labelledby="study-qa-title"
      className="fixed inset-y-0 right-0 left-auto m-0 h-dvh max-h-none w-full max-w-xl overflow-y-auto border-l border-[var(--border)] bg-[var(--background)] p-0 text-[var(--foreground)] shadow-xl backdrop:bg-black/30"
      onCancel={event => { event.preventDefault(); dismiss(); }}
      onClick={event => { if (event.target === event.currentTarget) dismiss(); }}>
      <aside className="min-h-full space-y-4 p-5">
        <header className="flex items-center justify-between gap-4">
          <h2 id="study-qa-title" className="text-lg font-semibold">Study 答疑</h2>
          <button type="button" className={action} onClick={dismiss} aria-label="关闭答疑">收起</button>
        </header>
        <StudyQuestionPanel />
      </aside>
    </dialog>
  );
}

function StudyQuestionPanel() {
  const { resources, sourceError } = useResources();
  const [question, setQuestion] = useState("");
  const [resourceId, setResourceId] = useState("");
  const [result, setResult] = useState<StudyAnswer & { question: string }>();
  const [busy, setBusy] = useState(false);
  const [partial, setPartial] = useState(false);
  const [error, setError] = useState("");

  async function work(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    setResult(undefined);
    try { await action(); } catch (error) { setError(message(error)); }
    finally { setBusy(false); }
  }

  return <form className="space-y-3" onSubmit={event => {
    event.preventDefault();
    void work(async () => setResult({ ...await studyReview.answer(question, resourceId), question: question.trim() }));
  }}>
    <p className="text-sm text-[var(--foreground-muted)]">上传题目文件或直接输入问题，核对题干后发送给 HoneyOS。</p>
    <label className="block">上传题目文件
      <input className={field} type="file" accept=".txt,.md,.markdown,.json,.csv,.tsv,.xml,.pdf,.docx,.pptx,.xlsx,.png,.jpeg,.jpg,.webp"
        disabled={busy} onChange={event => {
          const file = event.target.files?.[0];
          if (!file) return;
          event.target.value = "";
          setQuestion("");
          setPartial(false);
          void work(async () => {
            const extracted = await studyReview.extract(file.name, await fileData(file));
            setQuestion(extracted.question);
            setPartial(extracted.partial);
          });
        }} />
    </label>
    <label className="block">核对题目<textarea className={field} rows={8} value={question} maxLength={12000}
      required disabled={busy} onChange={event => { setQuestion(event.target.value); setResult(undefined); }} /></label>
    {partial && <p>只展示前 12,000 字。请核对完整题干和所需图表信息后提交。</p>}
    <ResourcePicker resources={resources} value={resourceId} optional onChange={value => { setResourceId(value); setResult(undefined); }} />
    <button className={action} disabled={busy || !question.trim()}>确认题目并答疑</button>
    {busy && <p role="status">正在处理题目…</p>}
    {(error || sourceError) && <p role="alert">{error || sourceError}</p>}
    {result && <section aria-label="答疑对话" className="space-y-3" aria-live="polite">
      <article className={panel + " ml-8 bg-[var(--surface-subtle)]"}>
        <h3 className="text-sm font-medium">你的题目</h3>
        <p className="whitespace-pre-wrap">{result.question}</p>
      </article>
      <article aria-label="答疑结果" className={panel + " mr-8 bg-[var(--surface-raised)]"}>
        <h3 className="text-sm font-medium">HoneyOS 解答</h3>
        <p className="whitespace-pre-wrap">{result.answer}</p>
        {result.citations.map(citation => <Evidence key={citation.excerpt} title={citation.source_title} excerpt={citation.excerpt} />)}
      </article>
    </section>}
  </form>;
}
