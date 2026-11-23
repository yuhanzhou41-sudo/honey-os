import { ArrowsOutSimpleIcon, LinkBreakIcon, TrashIcon } from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";

import {
  detachUnderstandingEvidence,
  fetchUnderstandingGraph,
  fetchUnderstandingLabel,
  suppressUnderstandingLabel,
  type GraphEvidence,
  type GraphLabel,
  type LabelVersion,
} from "../../api/understanding";

const CATEGORY_LABELS: Record<string, string> = {
  interest_preference: "兴趣偏好",
  behavior_pattern: "行为方式",
  learning_work_style: "学习方式",
  communication_style: "沟通方式",
  relationship_style: "关系方式",
  value_tendency: "价值取向",
};

const KIND_LABELS: Record<string, string> = {
  episode: "共同经历",
  commitment: "答应过的",
  temporary_state: "临时状态",
  open_loop: "待续",
};

const STATE_LABELS: Record<string, string> = {
  tentative: "初步",
  supported: "已支持",
  disputed: "存疑",
  needs_reassessment: "待复核",
  user_suppressed: "已被你禁止",
};

const ROW_H = 76;
const LABEL_X = 90;
const MEMORY_X = 610;

type Point = { x: number; y: number };

type TimelineEvent = {
  at: number;
  kind: "formed" | "support" | "counter" | "revision";
  title: string;
  detail?: string;
};

function relColor(relation: string): string {
  return relation === "counter" ? "#d97706" : "#2563eb";
}

function fmtTime(value: string | null | undefined): string {
  if (!value) return "时间未知";
  const t = Date.parse(value);
  return Number.isFinite(t) ? new Date(t).toLocaleString() : "时间未知";
}

function buildTimeline(label: GraphLabel): TimelineEvent[] {
  const events: TimelineEvent[] = [];
  const formed = Date.parse(label.created_at ?? "");
  if (Number.isFinite(formed)) {
    events.push({ at: formed, kind: "formed", title: "标签形成" });
  }
  label.evidence.forEach((ev) => {
    const at = Date.parse(ev.occurred_at ?? "");
    const mem = ev.memory?.content ?? ev.ref;
    events.push({
      at: Number.isFinite(at) ? at : formed,
      kind: ev.relation === "counter" ? "counter" : "support",
      title: ev.relation === "counter" ? "出现反证" : "获得支持",
      detail: mem.length > 40 ? `${mem.slice(0, 40)}…` : mem,
    });
  });
  (label.versions ?? []).forEach((v: LabelVersion) => {
    const at = Date.parse(v.created_at ?? "");
    events.push({
      at: Number.isFinite(at) ? at : formed,
      kind: "revision",
      title: `修订 r${v.revision} · ${actorLabel(v.actor)}`,
      detail: `${STATE_LABELS[v.state] ?? v.state} / ${v.grade || "—"}`,
    });
  });
  return events.sort((a, b) => b.at - a.at);
}

function actorLabel(actor: string): string {
  switch (actor) {
    case "user_edit":
      return "你修改了描述";
    case "user_suppress":
      return "你禁止了标签";
    case "user_restore":
      return "你恢复了标签";
    case "user_detach":
      return "你解除了关联";
    case "source_withdrawal":
      return "来源撤回，自动重算";
    case "recompute":
      return "系统重算可信度";
    default:
      return actor || "系统";
  }
}

export default function UnderstandingPage() {
  const queryClient = useQueryClient();
  const [category, setCategory] = useState<string>("all");
  const [sinceDays, setSinceDays] = useState<number>(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [selectedMemory, setSelectedMemory] = useState<string | null>(null);
  const [view, setView] = useState({ scale: 1, tx: 0, ty: 0 });
  const dragRef = useRef<Point | null>(null);

  const graph = useQuery({
    queryKey: ["understanding-graph"],
    queryFn: () => fetchUnderstandingGraph({ limit: 200 }),
  });

  const labelDetail = useQuery({
    queryKey: ["understanding-label", selected],
    queryFn: () => fetchUnderstandingLabel(selected!),
    enabled: !!selected,
  });

  const suppress = useMutation({
    mutationFn: (labelId: string) => suppressUnderstandingLabel(labelId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["understanding-graph"] });
      if (selected) queryClient.invalidateQueries({ queryKey: ["understanding-label", selected] });
    },
  });
  const detach = useMutation({
    mutationFn: ({ labelId, ref }: { labelId: string; ref: string }) =>
      detachUnderstandingEvidence(labelId, ref),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["understanding-graph"] });
      if (selected) queryClient.invalidateQueries({ queryKey: ["understanding-label", selected] });
    },
  });

  const labels = graph.data?.labels ?? [];

  const filtered = useMemo(() => {
    const cutoff = sinceDays > 0 ? Date.now() - sinceDays * 86400000 : 0;
    return labels.filter((label) => {
      if (category !== "all" && label.category_id !== category) return false;
      if (cutoff) {
        const stamp = Date.parse(label.created_at ?? "");
        if (!Number.isFinite(stamp) || stamp < cutoff) return false;
      }
      return true;
    });
  }, [labels, category, sinceDays]);

  // Layout: labels on the left, unique memories on the right.
  const layout = useMemo(() => {
    const memoryKeys: string[] = [];
    const memoryMeta = new Map<string, GraphEvidence>();
    filtered.forEach((label) =>
      label.evidence.forEach((ev) => {
        if (ev.memory && !memoryMeta.has(ev.ref)) {
          memoryMeta.set(ev.ref, ev);
          memoryKeys.push(ev.ref);
        }
      }),
    );
    const labelPos = new Map<string, Point>();
    filtered.forEach((label, i) => labelPos.set(label.id, {
      x: LABEL_X, y: 60 + i * ROW_H,
    }));
    const memoryPos = new Map<string, Point>();
    memoryKeys.forEach((ref, i) => memoryPos.set(ref, {
      x: MEMORY_X, y: 60 + i * ROW_H,
    }));
    return {
      labelPos, memoryPos, memoryMeta,
      height: Math.max(360, 60 + Math.max(filtered.length, memoryKeys.length) * ROW_H),
    };
  }, [filtered]);

  // Labels citing the currently selected memory (client-side from the graph).
  const memoryRelatedLabels = useMemo(() => {
    if (!selectedMemory) return [];
    return filtered.filter((l) => l.evidence.some((ev) => ev.ref === selectedMemory));
  }, [filtered, selectedMemory]);

  const active: GraphLabel | undefined = labelDetail.data ?? filtered.find((l) => l.id === selected);
  const timeline = useMemo(() => (active ? buildTimeline(active) : []), [active]);

  const selectedMemoryEv = selectedMemory ? layout.memoryMeta.get(selectedMemory) : undefined;

  const categories = useMemo(() => {
    const set = new Set(labels.map((l) => l.category_id));
    return ["all", ...Array.from(set)];
  }, [labels]);

  function edgeOpacity(labelId: string): number {
    if (selected && selected !== labelId) return 0.2;
    if (selectedMemory) {
      const label = filtered.find((l) => l.id === labelId);
      if (!label?.evidence.some((ev) => ev.ref === selectedMemory)) return 0.2;
    }
    return 0.85;
  }

  function onWheel(e: React.WheelEvent) {
    e.preventDefault();
    setView((v) => {
      const next = Math.min(2.5, Math.max(0.4, v.scale - e.deltaY * 0.001));
      return { ...v, scale: next };
    });
  }
  function onPointerDown(e: React.PointerEvent) {
    dragRef.current = { x: e.clientX, y: e.clientY };
  }
  function onPointerMove(e: React.PointerEvent) {
    if (!dragRef.current) return;
    const dx = e.clientX - dragRef.current.x;
    const dy = e.clientY - dragRef.current.y;
    dragRef.current = { x: e.clientX, y: e.clientY };
    setView((v) => ({ ...v, tx: v.tx + dx, ty: v.ty + dy }));
  }
  function onPointerUp() {
    dragRef.current = null;
  }

  function selectLabel(id: string) {
    setSelected(id);
    setSelectedMemory(null);
  }
  function selectMemory(ref: string) {
    setSelectedMemory(ref);
    setSelected(null);
  }

  if (graph.isLoading) {
    return <div style={{ padding: 24, color: "#667085" }}>正在加载 Honey 对你的理解…</div>;
  }
  if (graph.isError) {
    return (
      <div style={{ padding: 24, color: "#b42318" }}>
        图谱加载失败。请确认 HoneyOS 服务可用后重试。
      </div>
    );
  }

  return (
    <div style={{ display: "flex", height: "100%", minHeight: 0 }}>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <div style={{ padding: "16px 20px", borderBottom: "1px solid #eaecf0" }}>
          <h1 style={{ margin: 0, fontSize: 20 }}>Honey 对我的理解</h1>
          <p style={{ margin: "4px 0 12px", color: "#667085", fontSize: 13 }}>
            共 {graph.data?.total ?? 0} 条理解标签。节点与连线均来自真实记忆数据；点击标签或记忆节点查看详情与时间轨迹。
          </p>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
            <label style={{ fontSize: 13 }}>
              分类：
              <select value={category} onChange={(e) => setCategory(e.target.value)}>
                {categories.map((c) => (
                  <option key={c} value={c}>
                    {c === "all" ? "全部" : CATEGORY_LABELS[c] ?? c}
                  </option>
                ))}
              </select>
            </label>
            <label style={{ fontSize: 13 }}>
              时间：
              <select value={sinceDays} onChange={(e) => setSinceDays(Number(e.target.value))}>
                <option value={0}>全部</option>
                <option value={30}>近 30 天</option>
                <option value={90}>近 90 天</option>
                <option value={365}>近一年</option>
              </select>
            </label>
            <button
              type="button"
              onClick={() => setView({ scale: 1, tx: 0, ty: 0 })}
              style={{ fontSize: 13, display: "inline-flex", alignItems: "center", gap: 4 }}
            >
              <ArrowsOutSimpleIcon size={16} /> 重置视图
            </button>
          </div>
        </div>

        {filtered.length === 0 ? (
          <div style={{ padding: 40, color: "#667085", fontSize: 14 }}>
            {labels.length === 0
              ? "还没有形成任何用户理解标签。当 Honey 从长期记忆、共同经历或承诺中总结出稳定的你时，这里会出现节点。"
              : "当前筛选条件下没有标签。可调整分类或时间范围。"}
          </div>
        ) : (
          <div
            style={{ flex: 1, overflow: "hidden", cursor: "grab", background: "#fcfcfd" }}
            onWheel={onWheel}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerLeave={onPointerUp}
          >
            <svg width="100%" height="100%" viewBox={`0 0 900 ${layout.height}`}>
              <g transform={`translate(${view.tx} ${view.ty}) scale(${view.scale})`}>
                {filtered.map((label) =>
                  label.evidence.map((ev) => {
                    const from = layout.labelPos.get(label.id);
                    const to = ev.memory ? layout.memoryPos.get(ev.ref) : undefined;
                    if (!from || !to) return null;
                    const midX = (from.x + to.x) / 2;
                    return (
                      <path
                        key={`${label.id}-${ev.ref}`}
                        d={`M ${from.x} ${from.y} C ${midX} ${from.y}, ${midX} ${to.y}, ${to.x} ${to.y}`}
                        stroke={relColor(ev.relation)}
                        strokeWidth={ev.relation === "counter" ? 2 : 1.5}
                        strokeDasharray={ev.relation === "counter" ? "5 4" : undefined}
                        fill="none"
                        opacity={edgeOpacity(label.id)}
                      />
                    );
                  }),
                )}
                {filtered.map((label) => {
                  const p = layout.labelPos.get(label.id)!;
                  const isSel = selected === label.id;
                  return (
                    <g key={label.id} onClick={() => selectLabel(label.id)} style={{ cursor: "pointer" }}>
                      <circle cx={p.x} cy={p.y} r={isSel ? 12 : 9}
                        fill={label.suppressed ? "#98a2b3" : "#7c3aed"} />
                      <text x={p.x - 16} y={p.y + 4} textAnchor="end" fontSize={13}
                        fill={isSel ? "#101828" : "#475467"} fontWeight={isSel ? 600 : 400}>
                        {label.text || "(已隐藏)"}
                      </text>
                    </g>
                  );
                })}
                {Array.from(layout.memoryPos.entries()).map(([ref, p]) => {
                  const ev = layout.memoryMeta.get(ref);
                  const mem = ev?.memory;
                  if (!mem) return null;
                  const isSel = selectedMemory === ref;
                  return (
                    <g key={ref} onClick={() => selectMemory(ref)} style={{ cursor: "pointer" }}>
                      <rect x={p.x} y={p.y - 22} width={230} height={44} rx={8}
                        fill={isSel ? "#eef2ff" : "#ffffff"}
                        stroke={isSel ? "#7c3aed" : "#d0d5dd"}
                        strokeWidth={isSel ? 2 : 1} />
                      <text x={p.x + 12} y={p.y - 6} fontSize={12} fill="#344054">
                        {KIND_LABELS[mem.kind] ?? mem.kind}
                        {mem.imprint?.status === "known" ? ` · 印象:${mem.imprint.label ?? mem.imprint.axis ?? ""}` : ""}
                      </text>
                      <text x={p.x + 12} y={p.y + 12} fontSize={12} fill="#667085">
                        {mem.content.length > 16 ? `${mem.content.slice(0, 16)}…` : mem.content}
                      </text>
                    </g>
                  );
                })}
              </g>
            </svg>
          </div>
        )}
      </div>

      <aside style={{ width: 380, borderLeft: "1px solid #eaecf0", padding: 20, overflowY: "auto" }}>
        {selectedMemory && selectedMemoryEv?.memory ? (
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h2 style={{ fontSize: 16, margin: "0 0 4px" }}>
                {KIND_LABELS[selectedMemoryEv.memory.kind] ?? selectedMemoryEv.memory.kind}
              </h2>
              <button type="button" style={{ fontSize: 12, color: "#667085" }}
                onClick={() => setSelectedMemory(null)}>关闭</button>
            </div>
            <div style={{ fontSize: 13, margin: "8px 0", lineHeight: 1.6, color: "#101828" }}>
              {selectedMemoryEv.memory.content}
            </div>
            <div style={{ fontSize: 11, color: "#98a2b3", marginBottom: 8 }}>
              会话 {selectedMemoryEv.memory.source_session_id} · {fmtTime(selectedMemoryEv.memory.created_at)}
            </div>
            <div style={{ fontSize: 11, color: "#6941c6", marginBottom: 12 }}>
              {selectedMemoryEv.memory.imprint?.status === "known"
                ? `历史情绪印记：${selectedMemoryEv.memory.imprint.label ?? selectedMemoryEv.memory.imprint.axis ?? "有反应"}`
                : selectedMemoryEv.memory.imprint?.status === "unknown"
                  ? "历史情绪印记：未知"
                  : "无历史情绪印记"}
            </div>
            <div style={{ fontSize: 12, color: "#475467", marginBottom: 6, fontWeight: 600 }}>
              相关标签（{memoryRelatedLabels.length}）
            </div>
            {memoryRelatedLabels.length === 0 ? (
              <div style={{ fontSize: 12, color: "#98a2b3" }}>当前图谱中没有标签引用这条记忆。</div>
            ) : (
              memoryRelatedLabels.map((l) => (
                <button key={l.id} type="button"
                  onClick={() => selectLabel(l.id)}
                  style={{
                    display: "block", width: "100%", textAlign: "left", marginBottom: 6,
                    padding: "8px 10px", border: "1px solid #eaecf0", borderRadius: 8,
                    background: "#fff", cursor: "pointer", fontSize: 12, color: "#101828",
                  }}>
                  <div>{l.text || "(已隐藏)"}</div>
                  <div style={{ fontSize: 11, color: "#98a2b3", marginTop: 2 }}>
                    {STATE_LABELS[l.state] ?? l.state} · {l.grade || "—"}
                    {l.evidence.find((e) => e.ref === selectedMemory)?.relation === "counter" ? " · 反证" : " · 支持"}
                  </div>
                </button>
              ))
            )}
          </div>
        ) : !active ? (
          <div style={{ color: "#667085", fontSize: 13 }}>
            点击左侧标签节点查看详情、支持与反证证据、时间轨迹，并可忘记标签或解除错误关联；点击右侧记忆节点查看完整内容与相关标签。
          </div>
        ) : (
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <h2 style={{ fontSize: 16, margin: "0 0 4px" }}>{active.text || "(已隐藏)"}</h2>
              {selected && (
                <button type="button" style={{ fontSize: 12, color: "#667085" }}
                  onClick={() => setSelected(null)}>关闭</button>
              )}
            </div>
            <div style={{ fontSize: 12, color: "#667085", marginBottom: 12 }}>
              {CATEGORY_LABELS[active.category_id] ?? active.category_id} · 范围 {active.scope_key}
              <br />状态：{active.suppressed ? "已被你禁止" : (STATE_LABELS[active.state] ?? active.state)} · 可信度 {active.grade || "—"} · 修订 {active.revision}
            </div>
            <div style={{ fontSize: 12, color: "#667085", marginBottom: 8 }}>
              支持 {active.evidence.filter((e) => e.relation !== "counter").length} 条 ·
              反证 {active.evidence.filter((e) => e.relation === "counter").length} 条
              {labelDetail.isFetching ? " · 正在加载修订历史…" : ""}
            </div>

            <div style={{ fontSize: 13, fontWeight: 600, color: "#344054", margin: "12px 0 6px" }}>
              证据
            </div>
            {active.evidence.length === 0 ? (
              <div style={{ fontSize: 13, color: "#667085" }}>该标签目前没有可用证据。</div>
            ) : (
              active.evidence.map((ev) => (
                <div key={ev.ref} style={{
                  border: "1px solid #eaecf0", borderRadius: 8, padding: 10, marginBottom: 10,
                }}>
                  <div style={{ fontSize: 12, color: relColor(ev.relation), fontWeight: 600 }}>
                    {ev.relation === "counter" ? "反证" : "支持"}
                  </div>
                  {ev.memory ? (
                    <>
                      <div style={{ fontSize: 13, margin: "4px 0" }}>{ev.memory.content}</div>
                      <div style={{ fontSize: 11, color: "#98a2b3" }}>
                        {KIND_LABELS[ev.memory.kind] ?? ev.memory.kind} · {fmtTime(ev.memory.created_at)}
                        {ev.occurred_at ? ` · 发生于 ${fmtTime(ev.occurred_at)}` : ""}
                      </div>
                      <div style={{ fontSize: 11, color: "#6941c6", marginTop: 2 }}>
                        {ev.memory.imprint?.status === "known"
                          ? `历史情绪印记：${ev.memory.imprint.label ?? ev.memory.imprint.axis ?? "有反应"}`
                          : ev.memory.imprint?.status === "unknown"
                            ? "历史情绪印记：未知"
                            : "无历史情绪印记"}
                      </div>
                      <button type="button"
                        onClick={() => selectMemory(ev.ref)}
                        style={{ marginTop: 4, fontSize: 11, color: "#7c3aed", border: "none", background: "none", padding: 0, cursor: "pointer" }}>
                        查看记忆详情 →
                      </button>
                    </>
                  ) : (
                    <div style={{ fontSize: 12, color: "#667085" }}>{ev.ref}</div>
                  )}
                  <button
                    type="button"
                    onClick={() => detach.mutate({ labelId: active.id, ref: ev.ref })}
                    style={{ marginTop: 6, fontSize: 11, display: "inline-flex", gap: 4 }}
                  >
                    <LinkBreakIcon size={14} /> 解除此关联
                  </button>
                </div>
              ))
            )}

            <div style={{ fontSize: 13, fontWeight: 600, color: "#344054", margin: "16px 0 6px" }}>
              时间轨迹
            </div>
            {timeline.length === 0 ? (
              <div style={{ fontSize: 12, color: "#98a2b3" }}>暂无变化记录。</div>
            ) : (
              <div style={{ position: "relative", paddingLeft: 14 }}>
                <div style={{
                  position: "absolute", left: 4, top: 4, bottom: 4, width: 2,
                  background: "#eaecf0",
                }} />
                {timeline.map((ev, i) => (
                  <div key={i} style={{ position: "relative", marginBottom: 10 }}>
                    <div style={{
                      position: "absolute", left: -14, top: 4, width: 8, height: 8,
                      borderRadius: "50%",
                      background: ev.kind === "counter" ? "#d97706"
                        : ev.kind === "revision" ? "#7c3aed"
                        : ev.kind === "formed" ? "#101828" : "#2563eb",
                    }} />
                    <div style={{ fontSize: 12, fontWeight: 600, color: "#344054" }}>{ev.title}</div>
                    {ev.detail && <div style={{ fontSize: 11, color: "#667085" }}>{ev.detail}</div>}
                    <div style={{ fontSize: 10, color: "#98a2b3" }}>{fmtTime(new Date(ev.at).toISOString())}</div>
                  </div>
                ))}
              </div>
            )}

            {!active.suppressed && (
              <button
                type="button"
                onClick={() => {
                  if (window.confirm("忘记这个理解标签？原记忆不会被删除。")) {
                    suppress.mutate(active.id);
                  }
                }}
                style={{
                  marginTop: 8, fontSize: 13, color: "#b42318",
                  display: "inline-flex", alignItems: "center", gap: 4,
                }}
              >
                <TrashIcon size={16} /> 忘记这个标签
              </button>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}
