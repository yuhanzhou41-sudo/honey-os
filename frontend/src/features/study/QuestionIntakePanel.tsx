import { useEffect, useRef, useState } from "react";
import { fileData, studyReview, type ExamSource, type IntakeDraft, type QuestionDraft } from "../../api/study-review";
import type { StudyTask } from "../../api/study";

const field = "block w-full rounded border border-[var(--border)] bg-[var(--background)] p-2";
const button = "rounded border border-[var(--border)] px-3 py-1.5 disabled:opacity-50";
const panel = "space-y-3 rounded border border-[var(--border)] p-3";
const accept = ".txt,.md,.markdown,.json,.csv,.tsv,.xml,.pdf,.docx,.pptx,.xlsx,image/*";

async function intakeFile(file: File) {
  if (!file.type.startsWith("image/") ||
      (["image/png", "image/jpeg", "image/webp"].includes(file.type) && file.size <= 6 * 1024 * 1024)) return file;
  const image = await createImageBitmap(file);
  try {
    const canvas = document.createElement("canvas");
    const scale = Math.min(1, 2400 / Math.max(image.width, image.height));
    canvas.width = Math.round(image.width * scale);
    canvas.height = Math.round(image.height * scale);
    const context = canvas.getContext("2d");
    if (!context) throw new Error("无法处理图片，请转换为 PNG 或 JPEG 后重试。");
    context.fillStyle = "#fff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, "image/jpeg", 0.9));
    if (!blob) throw new Error("无法转换图片。");
    return new File([blob], file.name.replace(/\.[^.]+$/, "") + ".jpg", { type: "image/jpeg" });
  } finally {
    image.close();
  }
}

const blank = (): QuestionDraft => ({ prompt: "", options: ["", ""], correct: null, explanation: "", excerpt: "" });

export default function QuestionIntakePanel({ planId, tasks, onSaved }: {
  planId?: string; tasks: StudyTask[]; onSaved: () => Promise<void>;
}) {
  const camera = useRef<HTMLInputElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const container = useRef<HTMLDetailsElement>(null);
  const [capture, setCapture] = useState<{ stream: MediaStream; name: string }>();
  const [mode, setMode] = useState<"upload" | "search" | "mock">("upload");
  const [file, setFile] = useState<File>();
  const [topic, setTopic] = useState("");
  const [searchResults, setSearchResults] = useState<ExamSource[]>();
  const [webSource, setWebSource] = useState<ExamSource>();
  const [offer, setOffer] = useState(false);
  const [preview, setPreview] = useState<IntakeDraft>();
  const [segment, setSegment] = useState(1);
  const [taskId, setTaskId] = useState("");
  const [usePlan, setUsePlan] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (!capture || !video.current) return;
    video.current.srcObject = capture.stream;
    return () => capture.stream.getTracks().forEach(track => track.stop());
  }, [capture]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try { await action(); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "处理失败，请重试。"); }
    finally { setBusy(false); }
  }

  function chooseFile(value?: File) {
    if (busy || !value) return;
    setFile(value);
    setPreview(undefined);
    setSegment(1);
  }

  function openCamera() {
    if (!navigator.mediaDevices?.getUserMedia) {
      camera.current?.click();
      return;
    }
    openCapture(() => navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" } }, audio: false,
    }), "相机拍摄.jpg");
  }

  function openCapture(getStream: () => Promise<MediaStream>, name: string) {
    void run(async () => {
      const stream = await getStream();
      if (container.current?.open) setCapture({ stream, name });
      else stream.getTracks().forEach(track => track.stop());
    });
  }

  function captureFrame() {
    const frame = video.current;
    if (!capture || !frame?.videoWidth) {
      setError("图像尚未就绪，请稍后重试。");
      return;
    }
    const canvas = document.createElement("canvas");
    canvas.width = frame.videoWidth;
    canvas.height = frame.videoHeight;
    const context = canvas.getContext("2d");
    if (!context) {
      setError("无法截取图像，请上传图片。");
      return;
    }
    context.drawImage(frame, 0, 0);
    const { name } = capture;
    setCapture(undefined);
    canvas.toBlob(blob => {
      if (blob) chooseFile(new File([blob], name, { type: "image/jpeg" }));
      else setError("无法截取图像，请上传图片。");
    }, "image/jpeg", 0.92);
  }

  function showDraft(value: IntakeDraft, fromSegment = 1) {
    setSegment(fromSegment);
    setPreview({ ...value, questions: value.questions.length ? value.questions : [blank()] });
  }

  function getDraft(fromSegment = 1, source = webSource) {
    void run(async () => {
      if (source && mode === "search") {
        const result = await studyReview.webDrafts(source.url, fromSegment);
        showDraft(result, fromSegment);
        if (!result.questions.length && !result.warning) setOffer(true);
      }
      if (file && mode === "upload") {
        const upload = await intakeFile(file);
        showDraft(await studyReview.uploadDrafts(upload.name, await fileData(upload), fromSegment), fromSegment);
      }
    });
  }

  function generate() {
    void run(async () => {
      const selectedPlan = usePlan ? planId : undefined;
      const ids = selectedPlan ? (taskId ? [taskId] : tasks.map(task => task.id)) : [];
      showDraft(await studyReview.practiceDrafts(topic.trim(), selectedPlan, ids));
      setOffer(false);
    });
  }

  function edit(index: number, patch: Partial<QuestionDraft>) {
    setPreview(current => current && ({
      ...current, questions: current.questions.map((question, row) => row === index ? { ...question, ...patch } : question),
    }));
  }

  function selectMode(value: typeof mode) {
    setCapture(undefined);
    setMode(value);
    setPreview(undefined);
    setError("");
    setNotice("");
    setOffer(false);
  }

  return <details ref={container} className={panel} onToggle={event => {
    if (!event.currentTarget.open) setCapture(undefined);
  }}>
    <summary>添加练习题</summary>
    <nav aria-label="添加练习题方式" className="flex flex-wrap gap-2">
      {([["upload", "上传题目"], ["search", "联网找真题"], ["mock", "AI 出模拟题"]] as const).map(([key, label]) =>
        <button key={key} type="button" className={button} disabled={busy} aria-pressed={mode === key}
          onClick={() => selectMode(key)}>{label}</button>)}
    </nav>
    <fieldset key={mode} className="space-y-2" disabled={busy}>
      {mode === "upload" ? <>
        <label className="block">选择题目文件
          <input className={field} type="file" accept={accept} onChange={event => {
            chooseFile(event.target.files?.[0]); event.target.value = "";
          }} />
        </label>
        <input ref={camera} type="file" accept="image/*" capture="environment" hidden onChange={event => {
          chooseFile(event.target.files?.[0]); event.target.value = "";
        }} />
        <button className={button} type="button" onClick={openCamera}>拍照上传</button>
        {navigator.mediaDevices?.getDisplayMedia && <button className={button} type="button" onClick={() =>
          openCapture(() => navigator.mediaDevices.getDisplayMedia({ video: true, audio: false }), "截屏.jpg")
        }>截取屏幕</button>}
        {capture && <div className={panel}>
          <video ref={video} autoPlay muted playsInline className="max-h-56 w-full" />
          <button className={button} type="button" onClick={captureFrame}>使用当前画面</button>
          <button className={button} type="button" onClick={() => setCapture(undefined)}>关闭预览</button>
        </div>}
        <label className="block">粘贴截图
          <input className={field} readOnly placeholder="截屏后在这里粘贴"
            onPaste={event => {
              const screenshot = Array.from(event.clipboardData.items ?? []).find(item => item.type.startsWith("image/"))?.getAsFile()
                ?? Array.from(event.clipboardData.files ?? []).find(item => item.type.startsWith("image/"));
              if (screenshot) { event.preventDefault(); chooseFile(screenshot); }
            }} />
        </label>
        <p className="text-sm">支持常用图片、文本、PDF 和 Office 文档。图片通过已配置的视觉模型识别。</p>
        {file && <p>{file.name}</p>}
        <button className={button} type="button" disabled={!file} onClick={() => getDraft()}>提取题目</button>
      </> : <>
        <label className="block">{mode === "search" ? "真题主题" : "出题主题"}
          <input className={field} value={topic} maxLength={180} onChange={event => {
            setTopic(event.target.value);
            if (mode === "search") {
              setSearchResults(undefined); setWebSource(undefined); setOffer(false); setPreview(undefined);
            }
          }} />
        </label>
        {mode === "search" && <>
          <button className={button} type="button" disabled={!topic.trim()} onClick={() => void run(async () => {
            const result = await studyReview.searchExams(topic.trim());
            setPreview(undefined);
            setWebSource(undefined);
            setSearchResults(result.sources);
            setOffer(result.sources.length === 0);
          })}>搜索真题</button>
          {searchResults && <ul className="space-y-2">
            {searchResults.map(source => <li className={panel} key={source.url}>
              <a className="underline" href={source.url} target="_blank" rel="noreferrer">{source.title}</a>
              {source.description && <p className="text-sm">{source.description}</p>}
              <button className={button} type="button" onClick={() => {
                setPreview(undefined); setSegment(1); setWebSource(source); getDraft(1, source);
              }}>提取这份来源的题目</button>
            </li>)}
          </ul>}
          {!!searchResults?.length && <button className={button} type="button" onClick={() => setOffer(true)}>没有找到可用真题</button>}
        </>}
        {(mode === "mock" || offer) && <>
          {offer && <p>没有可用真题。要根据主题和复习计划生成模拟题吗？</p>}
          {planId && <label className="block">
            <input type="checkbox" checked={usePlan} onChange={event => setUsePlan(event.target.checked)} /> 使用当前学习计划
          </label>}
          {planId && usePlan && tasks.length > 0 && <label className="block">今日任务
            <select className={field} value={taskId} onChange={event => setTaskId(event.target.value)}>
              <option value="">今日全部任务</option>
              {tasks.map(task => <option key={task.id} value={task.id}>{task.title}</option>)}
            </select>
          </label>}
          <button className={button} type="button" disabled={!topic.trim() && !(usePlan && planId)}
            onClick={generate}>{offer ? "同意并生成模拟题" : "生成模拟题"}</button>
          {offer && <button className={button} type="button" onClick={() => setOffer(false)}>暂不生成</button>}
        </>}
      </>}
    </fieldset>
    {busy && <p role="status">正在处理…</p>}
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {preview && <fieldset disabled={busy} className={panel}>
      <legend>{preview.source.kind === "mock" ? "模拟题草稿" : "核对提取结果"}</legend>
      <p>{preview.source.title}</p>
      {preview.source.url && <a className="underline" href={preview.source.url} target="_blank" rel="noreferrer">打开原网页</a>}
      {preview.warning && <p>{preview.warning} 可以从正文手动录题。</p>}
      {preview.partial && <p>只提取了前 12,000 字。可拆分文件后继续录入。</p>}
      <details open={preview.source.kind !== "mock"}>
        <summary>{preview.source.kind === "mock" ? "出题范围" : "提取的原文"}</summary>
        <pre className="max-h-48 overflow-auto whitespace-pre-wrap text-sm">{preview.text}</pre>
      </details>
      {preview.segments > 1 && <p>第 {segment} / {preview.segments} 段。保存本段后可继续提取下一段。</p>}
      {preview.questions.map((question, index) => <fieldset className={panel} key={index}>
        <legend>第 {index + 1} 题</legend>
        <label className="block">题干<textarea className={field} value={question.prompt} maxLength={5000}
          onChange={event => edit(index, { prompt: event.target.value })} /></label>
        <label className="block">选项（每行一个）<textarea className={field} value={question.options.join("\n")}
          onChange={event => edit(index, { options: event.target.value.split("\n") })} /></label>
        <label className="block">正确选项
          <select className={field} value={question.correct ?? ""} onChange={event =>
            edit(index, { correct: event.target.value === "" ? null : Number(event.target.value) })}>
            <option value="">核对并选择正确选项</option>
            {question.options.map((option, index) => <option key={index} value={index}>{index + 1}. {option}</option>)}
          </select>
        </label>
        <label className="block">解析（选填）<textarea className={field} value={question.explanation ?? ""} maxLength={3000}
          onChange={event => edit(index, { explanation: event.target.value })} /></label>
        {preview.source.kind !== "mock" && <label className="block">出处原文
          <textarea className={field} value={question.excerpt} maxLength={1500}
            onChange={event => edit(index, { excerpt: event.target.value })} />
        </label>}
        {preview.source.kind === "web" && <>
          <label className="block"><input type="checkbox" checked={question.verified_past ?? false}
            onChange={event => edit(index, { verified_past: event.target.checked })} /> 我已对照原卷核验这道真题</label>
          {question.verified_past && <>
            <label className="block">考试<input className={field} value={question.exam ?? ""} maxLength={200}
              onChange={event => edit(index, { exam: event.target.value })} /></label>
            <label className="block">年份<input className={field} type="number" value={question.year ?? ""}
              onChange={event => edit(index, { year: event.target.value ? Number(event.target.value) : undefined })} /></label>
            <label className="block">原卷题号<input className={field} value={question.location ?? ""} maxLength={200}
              onChange={event => edit(index, { location: event.target.value })} /></label>
          </>}
        </>}
        <button className={button} type="button" onClick={() => setPreview({
          ...preview, questions: preview.questions.filter((_, row) => row !== index),
        })}>移除此题</button>
      </fieldset>)}
      {preview.source.kind !== "mock" && <button className={button} type="button" disabled={preview.questions.length >= 20}
        onClick={() => setPreview({ ...preview, questions: [...preview.questions, blank()] })}>手动添一题</button>}
      <button className={button} type="button" disabled={!preview.questions.length || preview.questions.some(
        question => question.correct === null || !question.prompt.trim() || !question.excerpt.trim() ||
          question.options.length < 2 || question.options.length > 6 || question.options.some(option => !option.trim()))
      } onClick={() => void run(async () => {
        const saved = await studyReview.saveIntake(preview.source.id, preview.questions);
        await onSaved();
        if (segment < preview.segments) {
          const next = segment + 1;
          setNotice(`已入库 ${saved.imported} 道题。请选择下一段继续。`);
          setSegment(next);
          setPreview(undefined);
        } else {
          setNotice(`已入库 ${saved.imported} 道题。`);
          setPreview(undefined);
        }
      })}>确认入库</button>
      <button className={button} type="button" onClick={() => setPreview(undefined)}>取消草稿</button>
      {segment < preview.segments && <button className={button} type="button"
        onClick={() => getDraft(segment + 1)}>跳过本段</button>}
    </fieldset>}
    {segment > 1 && !preview && (mode === "upload" || webSource) && <button type="button" className={button}
      disabled={busy} onClick={() => getDraft(segment)}>提取第 {segment} 段</button>}
  </details>;
}
