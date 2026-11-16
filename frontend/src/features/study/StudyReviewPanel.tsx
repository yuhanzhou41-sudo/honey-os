import { useEffect, useState, type FormEvent } from "react";
import { getStudyResourceContent, listStudyResources, type StudyResource } from "../../api/study";
import {
  studyReview, type AnsweredQuestion, type Attempt, type CardPreview,
  type CardSource, type Question, type SavedCard, type StudyAnswer,
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

export default function StudyReviewPanel() {
  const { resources, sourceError } = useResources();
  const [questions, setQuestions] = useState<Question[]>([]);
  const [cards, setCards] = useState<SavedCard[]>([]);
  const [mode, setMode] = useState<"practice" | "wrong" | "cards">("practice");
  const [active, setActive] = useState<Question>();
  const [choice, setChoice] = useState<number>();
  const [feedback, setFeedback] = useState<{ attempt: Attempt; question: AnsweredQuestion }>();
  const [history, setHistory] = useState<{ attempts: Attempt[]; question: AnsweredQuestion }>();
  const [pendingAttempt, setPendingAttempt] = useState<{ choice: number; id: string }>();
  const [resourceId, setResourceId] = useState("");
  const [sourceText, setSourceText] = useState("");
  const [cardResource, setCardResource] = useState("");
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
      const result = await studyReview.attempt(active.id, choice, attempt.id);
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
      {([["practice", "题库"], ["wrong", "错题"], ["cards", "知识点闪卡"]] as const).map(([key, label]) =>
        <button key={key} className={action} type="button" disabled={busy} aria-pressed={key === mode}
          onClick={() => { setMode(key); setActive(undefined); }}>{label}</button>)}
    </nav>
    {(error || sourceError) && <p role="alert">{error || sourceError}</p>}
    {notice && <p role="status">{notice}</p>}
    {busy && <p role="status">正在处理…</p>}

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

    {mode !== "cards" && <>
      <ul className="space-y-2">{questions.filter(item => mode !== "wrong" || item.latest_correct === 0)
        .map(item => <li key={item.id}>
          <button className={action} disabled={busy} onClick={() => openQuestion(item)}>{item.prompt}</button>
        </li>)}</ul>
      {!questions.some(item => mode !== "wrong" || item.latest_correct === 0) &&
        <p>{mode === "wrong" ? "暂无待复习的错题。" : "题库暂无练习题。"}</p>}
      {active && <section className={panel}>
        <h3 className="font-semibold">{active.prompt}</h3>
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
        <button className={action} disabled={busy} onClick={() => void work(async () => setHistory(await studyReview.history(active.id)))}>查看作答记录</button>
        {history && (history.attempts.length
          ? <ol className="list-decimal pl-5">{history.attempts.map(a => <li key={a.id}>
            {new Date(a.created_at).toLocaleString()} · {active.options[a.choice]} · {a.correct ? "答对" : "答错"}
          </li>)}</ol> : <p>还没有作答记录。</p>)}
      </section>}
    </>}

    {mode === "cards" && <>
      <section className={panel}>
        <ResourcePicker resources={resources} value={cardResource} onChange={setCardResource} />
        <button className={action} disabled={busy || !cardResource}
          onClick={() => void generate({ resource_id: cardResource })}>整理成闪卡</button>
      </section>
      {preview && <section className={panel}>
        <h3>闪卡预览 · {preview.source_title}</h3>
        {preview.partial && <p>这批卡片基于资料前 12,000 字。</p>}
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
      {cards.map(card => <details key={card.id} className={panel}>
        <summary>{card.front}</summary>
        <p className="whitespace-pre-wrap">{card.back}</p>
        <Evidence title={card.source_title} excerpt={card.excerpt} />
      </details>)}
      {!cards.length && <p>暂无已保存闪卡。</p>}
    </>}
  </div>;
}

async function fileData(file: File): Promise<string> {
  if (!file.size || file.size > 6 * 1024 * 1024) throw new Error("请选择 6 MB 以内的非空题目文件。");
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("无法读取题目文件，请重选。"));
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
    reader.readAsDataURL(file);
  });
}

export function StudyQuestionPanel() {
  const { resources, sourceError } = useResources();
  const [question, setQuestion] = useState("");
  const [resourceId, setResourceId] = useState("");
  const [result, setResult] = useState<StudyAnswer>();
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
    void work(async () => setResult(await studyReview.answer(question, resourceId)));
  }}>
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
    {result && <section aria-label="答疑结果" className={panel}>
      <p className="whitespace-pre-wrap">{result.answer}</p>
      {result.citations.map(citation => <Evidence key={citation.excerpt} title={citation.source_title} excerpt={citation.excerpt} />)}
    </section>}
  </form>;
}
