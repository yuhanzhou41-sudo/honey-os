import {
  ArrowLeftIcon,
  ArrowRightIcon,
  BookOpenIcon,
  CheckIcon,
  DoorOpenIcon,
  MagicWandIcon,
  PlayIcon,
  PlusIcon,
  SparkleIcon,
  UploadSimpleIcon,
  UserCircleIcon,
  XIcon,
} from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { streamChat } from "../../api/chat";
import {
  createStorySession,
  fetchStoryCatalog,
  fetchStorySession,
  finishStoryChapter,
  generateStory,
  generateStoryCharacter,
  importStoryCharacter,
  saveStoryChapter,
  type StoryChapter,
  type StorySession,
  type StoryCharacter,
  type StoryTemplate,
} from "../../api/companion";
import { HoneyAvatar } from "../../components/honey/HoneyAvatar";
import { HoneyMessage } from "../../components/honey/HoneyMessage";
import { ErrorState, LoadingState } from "../../components/honey/PageState";
import { Button } from "../../components/ui/Button";
import type { HoneyEvent } from "../../runtime/honey-events";

const toneClass: Record<string, string> = {
  copper: "from-[#37271f] via-[#815538] to-[#d49a69]",
  blue: "from-[#172533] via-[#35556c] to-[#9bb5c5]",
  green: "from-[#202c27] via-[#425d4d] to-[#b0b89a]",
  ink: "from-[#17191f] via-[#353945] to-[#8b8f9c]",
  rose: "from-[#3a2228] via-[#88535e] to-[#d6a1a2]",
  violet: "from-[#242238] via-[#565277] to-[#aaa4c8]",
  plum: "from-[#30222e] via-[#704d69] to-[#c39aaa]",
};

function StoryCover({ story, compact = false }: { story: StoryTemplate; compact?: boolean }) {
  return (
    <div className={`relative overflow-hidden rounded-[var(--radius-lg)] bg-gradient-to-br ${toneClass[story.cover_tone] || toneClass.copper} text-white ${compact ? "min-h-40" : "min-h-64"}`}>
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_72%_12%,rgba(255,255,255,0.28),transparent_32%),linear-gradient(180deg,transparent,rgba(10,12,15,0.62))]" />
      <div className="relative flex h-full min-h-[inherit] flex-col justify-end p-5 sm:p-6">
        {story.inspiration ? <p className="mb-auto text-[11px] font-medium tracking-[0.08em] text-white/65">社区高频剧情原型 · HoneyOS 原创改编</p> : null}
        <h3 className="max-w-sm text-2xl font-semibold tracking-[-0.035em]">{story.title}</h3>
        <p className="mt-2 max-w-md text-sm leading-6 text-white/78">{story.premise}</p>
      </div>
    </div>
  );
}

type ActorChoice = { source: "companion" | "card"; id: string };
type CreateKind = "story" | "character";

function sourceLabel(source: string) {
  if (source === "companion") return "你的伴侣";
  if (source === "created") return "我的 Story 角色";
  if (source === "imported") return "导入角色";
  return "社区原型 · HoneyOS 原创";
}

function CharacterCard({ character, selected, onSelect }: { character: StoryCharacter; selected: boolean; onSelect: () => void }) {
  return (
    <button type="button" onClick={onSelect} className={`group grid min-h-48 content-between rounded-[var(--radius-lg)] border p-5 text-left transition-colors active:translate-y-px ${selected ? "border-[var(--accent)] bg-[color-mix(in_srgb,var(--accent)_7%,var(--surface-raised))]" : "border-[var(--border)] bg-[var(--surface-raised)] hover:border-[var(--foreground-faint)]"}`}>
      <div className="flex items-start gap-4">
        <HoneyAvatar name={character.name} className="size-14 shrink-0 rounded-full" />
        <div className="min-w-0">
          <p className="text-xs font-medium text-[var(--foreground-muted)]">{sourceLabel(character.source)}</p>
          <h3 className="mt-1 text-xl font-semibold tracking-[-0.025em]">{character.name}</h3>
          <p className="mt-2 line-clamp-2 text-sm leading-6 text-[var(--foreground-muted)]">{character.tagline}</p>
        </div>
        {selected ? <CheckIcon className="ml-auto shrink-0 text-[var(--accent)]" size={20} weight="bold" /> : null}
      </div>
      <div className="mt-5">
        <p className="line-clamp-2 text-sm leading-6">{character.profile}</p>
        {character.inspiration ? <p className="mt-3 line-clamp-1 text-[11px] text-[var(--foreground-faint)]">{character.inspiration}</p> : null}
      </div>
    </button>
  );
}

function CharacterPicker({ characters, actor, onSelect }: { characters: StoryCharacter[]; actor: ActorChoice | null; onSelect: (character: StoryCharacter) => void }) {
  const companion = characters.find((character) => character.source === "companion");
  const storyCharacters = characters.filter((character) => character.source !== "companion");
  return (
    <div className="mt-5 grid gap-7">
      {companion ? (
        <section>
          <p className="mb-3 text-xs font-semibold tracking-[0.08em] text-[var(--foreground-muted)]">带上你现在的伴侣</p>
          <div className="max-w-[24rem]"><CharacterCard character={companion} selected={actor?.source === "companion"} onSelect={() => onSelect(companion)} /></div>
        </section>
      ) : null}
      {storyCharacters.length ? (
        <section>
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <p className="text-xs font-semibold tracking-[0.08em] text-[var(--foreground-muted)]">或者遇见一个独立 Story 角色</p>
            <p className="text-xs text-[var(--foreground-faint)]">不会进入主聊天，也不会改写 Honey</p>
          </div>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{storyCharacters.map((character) => <CharacterCard key={`${character.source}-${character.id}`} character={character} selected={actor?.source === "card" && actor.id === character.id} onSelect={() => onSelect(character)} />)}</div>
        </section>
      ) : null}
    </div>
  );
}

function CreateDialog({ kind, busy, error, onClose, onSubmit }: { kind: CreateKind; busy: boolean; error: boolean; onClose: () => void; onSubmit: (idea: string) => void }) {
  const [idea, setIdea] = useState("");
  const isStory = kind === "story";
  return (
    <div className="fixed inset-0 z-30 grid place-items-center bg-black/35 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="story-create-title">
      <form onSubmit={(event) => { event.preventDefault(); if (idea.trim()) onSubmit(idea.trim()); }} className="w-full max-w-xl rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)] p-6 shadow-[0_28px_90px_rgba(20,18,16,0.24)] sm:p-8">
        <div className="flex items-start gap-4">
          <div className="grid size-11 shrink-0 place-items-center rounded-[var(--radius-md)] bg-[var(--surface-subtle)] text-[var(--accent)]"><MagicWandIcon size={22} /></div>
          <div>
            <h2 id="story-create-title" className="text-2xl font-semibold tracking-[-0.03em]">{isStory ? "想经历一个怎样的故事？" : "你想遇见一个什么样的人？"}</h2>
            <p className="mt-2 text-sm leading-6 text-[var(--foreground-muted)]">{isStory ? "一句话就可以。HoneyOS 会补全场景、关系张力、开场和持续规则。" : "写下最重要的反差、身份或你们的关系。生成的角色只会在 Story 中出现，不会替换主聊天里的 Honey。"}</p>
          </div>
          <button type="button" onClick={onClose} className="ml-auto grid size-9 shrink-0 place-items-center rounded-[var(--radius-sm)] hover:bg-[var(--surface-subtle)]" aria-label="关闭"><XIcon size={18} /></button>
        </div>
        <label className="mt-7 grid gap-2">
          <span className="text-sm font-semibold">一句话设定</span>
          <textarea autoFocus value={idea} onChange={(event) => setIdea(event.target.value)} rows={4} placeholder={isStory ? "例如：我们因为暴雪，被困在一间山里的旧旅馆。" : "例如：一个表面冷淡、其实很容易心软的女刑警，我们三年前认识。"} className="min-h-32 resize-none rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] px-4 py-3 leading-7 outline-none placeholder:text-[var(--foreground-faint)] focus:border-[var(--accent)] focus:ring-2 focus:ring-[color-mix(in_srgb,var(--accent)_18%,transparent)]" />
        </label>
        {error ? <p className="mt-3 text-sm text-[var(--danger)]">刚才没有生成成功。可以换一种说法再试一次。</p> : null}
        <div className="mt-6 flex justify-end gap-3">
          <Button type="button" variant="secondary" onClick={onClose}>取消</Button>
          <Button type="submit" disabled={!idea.trim() || busy}><MagicWandIcon size={18} />{busy ? "正在生成" : isStory ? "生成故事" : "生成角色"}</Button>
        </div>
      </form>
    </div>
  );
}

export function StoryPage() {
  const catalog = useQuery({ queryKey: ["story-catalog"], queryFn: fetchStoryCatalog });
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const importRef = useRef<HTMLInputElement>(null);
  const characterStepRef = useRef<HTMLDivElement>(null);
  const readyStepRef = useRef<HTMLElement>(null);
  const [view, setView] = useState<"stories" | "characters">("stories");
  const [storyId, setStoryId] = useState("");
  const [actor, setActor] = useState<ActorChoice | null>(null);
  const [createKind, setCreateKind] = useState<CreateKind | null>(null);
  const create = useMutation({
    mutationFn: createStorySession,
    onSuccess: (session) => navigate(`/stories/${session.id}`),
  });
  const generate = useMutation<StoryTemplate | StoryCharacter, Error, { kind: CreateKind; idea: string }>({
    mutationFn: ({ kind, idea }: { kind: CreateKind; idea: string }) => kind === "story" ? generateStory(idea) : generateStoryCharacter(idea),
    onSuccess: async (item, variables) => {
      await queryClient.invalidateQueries({ queryKey: ["story-catalog"] });
      if (variables.kind === "story") { setStoryId(item.id); setView("stories"); }
      else { setActor({ source: "card", id: item.id }); setView("characters"); }
      setCreateKind(null);
    },
  });
  const importCard = useMutation({
    mutationFn: importStoryCharacter,
    onSuccess: async (character) => {
      await queryClient.invalidateQueries({ queryKey: ["story-catalog"] });
      setActor({ source: "card", id: character.id });
      setView("characters");
    },
  });

  if (catalog.isLoading) return <div className="p-6 sm:p-9"><LoadingState /></div>;
  if (catalog.isError || !catalog.data) return <div className="grid min-h-full place-items-center p-6"><ErrorState /></div>;
  const data = catalog.data;
  const selectedStory = data.stories.find((story) => story.id === storyId);
  const companion = { ...data.companion, source: "companion", background: "", default_story_id: "", inspiration: "" };
  const allCharacters = [companion, ...data.characters];
  const selectedCharacter = actor?.source === "companion" ? companion : data.characters.find((character) => character.id === actor?.id);

  function chooseCharacter(character: StoryCharacter) {
    setActor({ source: character.source === "companion" ? "companion" : "card", id: character.id });
    window.setTimeout(() => readyStepRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }), 80);
  }

  function chooseStory(id: string) {
    setStoryId(id);
    window.setTimeout(() => characterStepRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
  }

  function start() {
    if (!selectedStory || !actor) return;
    create.mutate({ story_id: selectedStory.id, actor_source: actor.source, actor_id: actor.id });
  }

  async function handleImport(file: File | undefined) {
    if (!file) return;
    try {
      const card = JSON.parse(await file.text()) as Record<string, unknown>;
      importCard.mutate(card);
    } catch {
      window.alert("这不是有效的角色卡 JSON。当前版本先支持 V1、V2、V3 JSON。");
    } finally {
      if (importRef.current) importRef.current.value = "";
    }
  }

  return (
    <section className="min-h-full bg-[var(--background)] px-4 py-7 sm:px-8 sm:py-9">
      <div className="mx-auto w-full max-w-[72rem]">
        <header className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <div className="flex items-center gap-3 text-[var(--accent)]"><BookOpenIcon size={22} weight="duotone" /><span className="text-sm font-semibold">故事</span></div>
            <h1 className="mt-4 text-4xl font-semibold tracking-[-0.045em] sm:text-5xl">今天想发生一点什么？</h1>
            <p className="mt-4 max-w-xl text-base leading-7 text-[var(--foreground-muted)]">带现在的 {data.companion.name} 进入另一个世界，或先遇见一个新的人。故事里的变化不会改写现实人格。</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => setCreateKind("character")}><PlusIcon size={18} />创建角色</Button>
            <Button variant="secondary" onClick={() => setCreateKind("story")}><PlusIcon size={18} />创建故事</Button>
            <Button variant="secondary" onClick={() => importRef.current?.click()}><UploadSimpleIcon size={18} />导入角色</Button>
            <input ref={importRef} type="file" accept="application/json,.json" className="hidden" onChange={(event) => void handleImport(event.target.files?.[0])} />
          </div>
        </header>

        {data.sessions.length ? (
          <section className="mt-10">
            <h2 className="text-lg font-semibold">继续上次的故事</h2>
            <div className="mt-4 flex gap-3 overflow-x-auto pb-2">
              {data.sessions.slice(0, 4).map((session) => (
                <Link key={session.id} to={`/stories/${session.id}`} className="min-w-[17rem] rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)] p-4 transition-transform active:translate-y-px">
                  <div className="flex items-center gap-3">
                    <HoneyAvatar name={session.actor_name} className="size-11 rounded-full" />
                    <div className="min-w-0">
                      <p className="truncate font-semibold">{session.story?.title}</p>
                      <p className="mt-0.5 text-xs text-[var(--foreground-muted)]">{session.actor_name}，已经进行 {session.turn_count} 轮</p>
                    </div>
                    <ArrowRightIcon className="ml-auto" size={18} />
                  </div>
                </Link>
              ))}
            </div>
          </section>
        ) : null}

        <div className="mt-12 flex w-fit rounded-[var(--radius-md)] bg-[var(--surface-subtle)] p-1" role="tablist" aria-label="浏览故事或角色">
          <button type="button" role="tab" aria-selected={view === "stories"} onClick={() => setView("stories")} className={`min-h-10 rounded-[var(--radius-sm)] px-5 text-sm font-semibold ${view === "stories" ? "bg-[var(--surface-raised)] shadow-sm" : "text-[var(--foreground-muted)]"}`}>从故事开始</button>
          <button type="button" role="tab" aria-selected={view === "characters"} onClick={() => setView("characters")} className={`min-h-10 rounded-[var(--radius-sm)] px-5 text-sm font-semibold ${view === "characters" ? "bg-[var(--surface-raised)] shadow-sm" : "text-[var(--foreground-muted)]"}`}>从角色开始</button>
        </div>

        {view === "stories" ? (
          <section className="mt-7">
            <h2 className="text-xl font-semibold">先选择发生什么</h2>
            <p className="mt-2 text-sm text-[var(--foreground-muted)]">选中后，再决定让现在的 {data.companion.name} 还是另一个角色进入。</p>
            <div className="mt-5 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
              {data.stories.map((story, index) => (
                <button key={story.id} type="button" aria-pressed={storyId === story.id} onClick={() => chooseStory(story.id)} className={`group text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)] ${index === 0 ? "xl:col-span-2" : ""}`}>
                  <div className={`rounded-[calc(var(--radius-lg)+2px)] border-2 p-1 transition-colors ${storyId === story.id ? "border-[var(--accent)]" : "border-transparent"}`}><StoryCover story={story} compact /></div>
                </button>
              ))}
            </div>
            {selectedStory ? (
              <div ref={characterStepRef} className="mt-9 scroll-mt-6 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-5 sm:p-7">
                <p className="text-xs font-semibold tracking-[0.08em] text-[var(--accent)]">第 2 步</p>
                <h2 className="mt-2 text-xl font-semibold">谁和你一起进入《{selectedStory.title}》？</h2>
                <p className="mt-2 text-sm text-[var(--foreground-muted)]">选择后就可以开始剧情。</p>
                <CharacterPicker characters={allCharacters} actor={actor} onSelect={chooseCharacter} />
              </div>
            ) : null}
          </section>
        ) : (
          <section className="mt-7">
            <h2 className="text-xl font-semibold">先选择和谁进入</h2>
            <p className="mt-2 text-sm text-[var(--foreground-muted)]">{data.companion.name} 是你的长期伴侣；其余是参考社区高使用量关系原型创作的独立 Story 角色。</p>
            <CharacterPicker characters={allCharacters} actor={actor} onSelect={chooseCharacter} />
            {selectedCharacter ? (
              <div className="mt-9">
                <h2 className="text-xl font-semibold">想和 {selectedCharacter.name} 去哪个故事？</h2>
                <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{data.stories.map((story) => <button key={story.id} type="button" onClick={() => setStoryId(story.id)} className={`rounded-[var(--radius-lg)] border p-4 text-left active:translate-y-px ${storyId === story.id ? "border-[var(--accent)] bg-[color-mix(in_srgb,var(--accent)_7%,var(--surface-raised))]" : "border-[var(--border)] bg-[var(--surface-raised)]"}`}><p className="text-xs font-medium text-[var(--foreground-muted)]">{story.genre}</p><h3 className="mt-1 font-semibold">{story.title}</h3><p className="mt-2 line-clamp-2 text-sm leading-6 text-[var(--foreground-muted)]">{story.premise}</p></button>)}</div>
              </div>
            ) : null}
          </section>
        )}

        {selectedStory && selectedCharacter ? (
          <section ref={readyStepRef} className="mt-10 grid scroll-mt-6 gap-6 rounded-[var(--radius-lg)] border-2 border-[var(--accent)] bg-[var(--surface-raised)] p-5 shadow-[0_18px_50px_rgba(56,48,39,0.10)] sm:p-7 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,0.72fr)]">
            <div>
              <p className="text-sm font-medium text-[var(--accent)]">{sourceLabel(selectedCharacter.source)}</p>
              <div className="mt-3 flex items-center gap-4"><HoneyAvatar name={selectedCharacter.name} className="size-16 rounded-full" /><div><h2 className="text-2xl font-semibold">{selectedCharacter.name}</h2><p className="mt-1 text-sm text-[var(--foreground-muted)]">进入《{selectedStory.title}》</p></div></div>
              <dl className="mt-6 grid gap-5 text-sm sm:grid-cols-2">
                <div><dt className="font-semibold">人格</dt><dd className="mt-2 leading-6 text-[var(--foreground-muted)]">{selectedCharacter.profile || "还没有填写人格，会保持现在的相处方式。"}</dd></div>
                <div><dt className="font-semibold">说话方式</dt><dd className="mt-2 leading-6 text-[var(--foreground-muted)]">{selectedCharacter.speaking_style || `沿用 ${data.companion.name} 当前的表达方式。`}</dd></div>
                <div><dt className="font-semibold">你们的关系</dt><dd className="mt-2 leading-6 text-[var(--foreground-muted)]">{selectedCharacter.relationship_hook || selectedStory.relationship_setup}</dd></div>
                <div><dt className="font-semibold">故事里的张力</dt><dd className="mt-2 leading-6 text-[var(--foreground-muted)]">{selectedStory.tension || selectedStory.premise}</dd></div>
              </dl>
            </div>
            <div className="flex flex-col justify-between rounded-[var(--radius-md)] bg-[var(--surface-subtle)] p-5">
              <div><p className="text-sm font-semibold">进入后会发生什么</p><p className="mt-3 text-sm leading-6 text-[var(--foreground-muted)]">{selectedCharacter.source === "companion" ? `${selectedCharacter.name} 会保留现在的人格、你们的关系和已有记忆，只把故事设定叠加在独立快照上。` : `${selectedCharacter.name} 使用这张角色卡的人格，不会读取或改写你现在的 ${data.companion.name}。`}</p></div>
              <Button className="mt-6 w-full" disabled={create.isPending} onClick={start}><PlayIcon size={18} weight="fill" />{create.isPending ? "正在打开故事" : "开始故事"}</Button>
              {create.isError ? <p className="mt-3 text-sm text-[var(--danger)]">故事没有打开，请稍后再试。</p> : null}
            </div>
          </section>
        ) : null}
      </div>
      {createKind ? <CreateDialog kind={createKind} busy={generate.isPending} error={generate.isError} onClose={() => setCreateKind(null)} onSubmit={(idea) => generate.mutate({ kind: createKind, idea })} /> : null}
    </section>
  );
}

type ViewMessage = { role: "user" | "assistant"; content: string };

function StoryNarrative({ content }: { content: string }) {
  const paragraphs = content.split(/\n{2,}/).map((item) => item.trim()).filter(Boolean);
  return (
    <div className="grid gap-3 break-words leading-7">
      {paragraphs.map((paragraph, index) => {
        const isAction = paragraph.length > 2 && paragraph.startsWith("*") && paragraph.endsWith("*");
        return isAction
          ? <p key={index} className="italic text-[var(--foreground-muted)]">{paragraph.slice(1, -1).trim()}</p>
          : <p key={index} className="whitespace-pre-wrap">{paragraph}</p>;
      })}
    </div>
  );
}

export function StorySessionPage() {
  const { storySessionId = "" } = useParams();
  const queryClient = useQueryClient();
  const sessionQuery = useQuery({
    queryKey: ["story-session", storySessionId],
    queryFn: () => fetchStorySession(storySessionId),
    enabled: Boolean(storySessionId),
  });
  const [draft, setDraft] = useState("");
  const [localMessages, setLocalMessages] = useState<ViewMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [liveText, setLiveText] = useState("");
  const [sendError, setSendError] = useState("");
  const [chapter, setChapter] = useState<StoryChapter | null>(null);
  const finish = useMutation({ mutationFn: () => finishStoryChapter(storySessionId), onSuccess: (result) => setChapter(result.chapter) });
  const save = useMutation({ mutationFn: (chapterId: string) => saveStoryChapter(chapterId), onSuccess: () => setChapter((current) => current ? { ...current, saved_to_memory: true } : current) });

  const session = sessionQuery.data;
  const messages = useMemo(() => {
    if (!session) return localMessages;
    const persisted = session.messages.map(({ role, content }) => ({ role, content }));
    return localMessages.length ? localMessages : persisted;
  }, [session, localMessages]);

  async function send(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || !session || sending || session.status !== "active") return;
    setDraft("");
    setSending(true);
    setLiveText("");
    setSendError("");
    const before = messages;
    setLocalMessages([...before, { role: "user", content: text }]);
    let finalText = "";
    try {
      await streamChat({
        sessionId: session.agent_session_id,
        sessionKey: session.agent_session_key,
        message: text,
        systemMessage: session.system_prompt,
        isolatedContext: true,
        storySessionId,
        onEvent: (event: HoneyEvent) => {
          const payload = event.payload as Record<string, unknown>;
          if (event.name === "assistant.delta") {
            finalText += String(payload.delta || "");
            setLiveText(finalText);
          }
          if (event.name === "assistant.completed") {
            finalText = String(payload.content || finalText);
            setLiveText(finalText);
          }
          if (event.name === "error") {
            throw new Error(String(payload.message || "story_reply_failed"));
          }
        },
      });
      if (finalText) {
        const next = [...before, { role: "user" as const, content: text }, { role: "assistant" as const, content: finalText }];
        setLocalMessages(next);
        setLiveText("");
        await queryClient.invalidateQueries({ queryKey: ["story-session", storySessionId] });
      }
    } catch {
      setLocalMessages(before);
      setDraft(text);
      setLiveText("");
      setSendError("刚才没有接上。你的话还在，可以再发一次。");
    } finally {
      setSending(false);
    }
  }

  if (sessionQuery.isLoading) return <div className="p-6 sm:p-9"><LoadingState /></div>;
  if (sessionQuery.isError || !session) return <div className="grid min-h-full place-items-center p-6"><ErrorState /></div>;

  return (
    <section className={`relative flex h-full min-h-0 flex-col overflow-hidden bg-gradient-to-br ${toneClass[session.story.cover_tone] || toneClass.copper}`}>
      <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(12,14,17,0.30),rgba(12,14,17,0.68)),radial-gradient(circle_at_70%_10%,rgba(255,255,255,0.16),transparent_36%)]" />
      <header className="relative z-[1] flex min-h-[5rem] items-center gap-3 border-b border-white/15 px-4 text-white sm:px-7">
        <Link to="/stories" className="grid size-10 place-items-center rounded-[var(--radius-sm)] hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white" aria-label="离开故事"><ArrowLeftIcon size={20} /></Link>
        <HoneyAvatar name={session.actor_name} className="size-10 rounded-full" />
        <div className="min-w-0"><h1 className="truncate font-semibold">{session.story.title}</h1><p className="truncate text-xs text-white/68">{session.actor_name}，{session.current_scene}</p></div>
        <Button className="ml-auto border-white/20 bg-white/10 text-white hover:bg-white/15" variant="secondary" disabled={!messages.length || finish.isPending || session.status !== "active"} onClick={() => finish.mutate()}><DoorOpenIcon size={18} /><span className="hidden sm:inline">结束这一章</span></Button>
      </header>

      <div className="relative z-[1] min-h-0 flex-1 overflow-y-auto px-3 py-6 sm:px-7">
        <div className="mx-auto flex min-h-full w-full max-w-[52rem] flex-col justify-end gap-5">
          {!messages.length ? (
            <article className="max-w-[44rem] rounded-[var(--radius-lg)] bg-[color-mix(in_srgb,var(--surface-raised)_94%,transparent)] p-5 shadow-[0_18px_50px_rgba(8,10,13,0.24)] backdrop-blur-md sm:p-7">
              <p className="text-sm font-semibold text-[var(--accent)]">{session.story.setting}</p>
              <p className="mt-4 text-lg leading-8">{session.story.opening}</p>
              <p className="mt-4 text-[var(--foreground-muted)]">{String(session.actor_snapshot.first_message || "我看见你了。接下来，想从哪里开始？")}</p>
            </article>
          ) : null}
          {messages.map((message, index) => message.role === "assistant" ? (
            <article key={`${message.role}-${index}`} className="flex items-start gap-3"><HoneyAvatar name={session.actor_name} className="mt-1 size-9 rounded-full" /><div className="min-w-0 max-w-[44rem] rounded-[var(--radius-lg)] bg-[color-mix(in_srgb,var(--surface-raised)_96%,transparent)] px-5 py-4 shadow-[0_12px_36px_rgba(8,10,13,0.18)] backdrop-blur-md"><StoryNarrative content={message.content} /></div></article>
          ) : (
            <article key={`${message.role}-${index}`} className="ml-auto max-w-[78%] rounded-[var(--radius-lg)] bg-[#282722] px-4 py-3 text-white"><HoneyMessage content={message.content} role="user" plain messageId={`story-${index}`} /></article>
          ))}
          {liveText ? <article className="flex items-start gap-3" aria-live="polite"><HoneyAvatar name={session.actor_name} className="mt-1 size-9 rounded-full" /><div className="min-w-0 max-w-[44rem] rounded-[var(--radius-lg)] bg-[color-mix(in_srgb,var(--surface-raised)_96%,transparent)] px-5 py-4 backdrop-blur-md"><StoryNarrative content={liveText} /></div></article> : null}
        </div>
      </div>

      <form onSubmit={send} className="relative z-[1] mx-auto mb-4 flex w-[calc(100%-1.5rem)] max-w-[52rem] items-end gap-2 rounded-[var(--radius-lg)] border border-white/20 bg-[color-mix(in_srgb,var(--surface-raised)_94%,transparent)] p-2 shadow-[0_16px_50px_rgba(8,10,13,0.26)] backdrop-blur-xl sm:mb-6">
        <textarea value={draft} onChange={(event) => setDraft(event.target.value)} rows={1} disabled={sending || session.status !== "active"} placeholder={session.status === "active" ? `对${session.actor_name}说点什么` : "这一章已经结束"} className="max-h-36 min-h-11 min-w-0 flex-1 resize-none bg-transparent px-3 py-2.5 outline-none" />
        <Button type="submit" size="icon" disabled={!draft.trim() || sending || session.status !== "active"} aria-label="发送"><ArrowRightIcon size={19} /></Button>
      </form>
      {sendError ? <p className="relative z-[1] mx-auto -mt-2 mb-3 w-[calc(100%-2rem)] max-w-[52rem] text-sm text-white" role="alert">{sendError}</p> : null}

      {chapter ? (
        <div className="absolute inset-0 z-20 grid place-items-center bg-black/45 p-4 backdrop-blur-sm">
          <article className="w-full max-w-xl rounded-[var(--radius-lg)] bg-[var(--surface-raised)] p-6 text-[var(--foreground)] shadow-[0_28px_90px_rgba(0,0,0,0.32)] sm:p-8">
            <div className="flex items-center gap-2 text-[var(--accent)]"><SparkleIcon size={20} weight="duotone" /><span className="text-sm font-semibold">这一章发生了什么</span></div>
            <h2 className="mt-4 text-2xl font-semibold tracking-[-0.03em]">{chapter.title}</h2>
            <p className="mt-4 leading-7 text-[var(--foreground-muted)]">{chapter.summary}</p>
            <p className="mt-4 rounded-[var(--radius-md)] bg-[var(--surface-subtle)] p-4 text-sm leading-6">{chapter.relationship_change}</p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Button disabled={save.isPending || chapter.saved_to_memory} onClick={() => save.mutate(chapter.id)}>{chapter.saved_to_memory ? <CheckIcon size={18} /> : <BookOpenIcon size={18} />}{chapter.saved_to_memory ? "已保存到共同经历" : "确认保存到共同经历"}</Button>
              <Button variant="secondary" onClick={() => setChapter(null)}>暂不保存</Button>
              <Link to="/" className="inline-flex min-h-10 items-center rounded-[var(--radius-sm)] px-4 text-sm font-medium text-[var(--foreground-muted)] hover:text-[var(--foreground)]">回到聊天</Link>
            </div>
          </article>
        </div>
      ) : null}
    </section>
  );
}
