import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { requestJson } from "../../api/client";
import { Button } from "../../components/ui/Button";

const endpoint = "/api/companion/study-skill";
const queryKey = ["study-skill"];
type Candidate = {
  version: number;
  digest: string;
  work_id: string;
  approved: boolean;
  manifest: { name: string; purpose: string; heading: string };
  checks: string[];
};
type Review = { active_version: number | null; candidates: Candidate[] };
type Action = "enable" | "disable" | "rollback";

function post<T>(body: object) {
  return requestJson<T>(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function StudySkillReview() {
  const client = useQueryClient();
  const [notes, setNotes] = useState("");
  const [reviewing, setReviewing] = useState<{ candidate: Candidate; action: Action }>();
  const review = useQuery({ queryKey, queryFn: () => requestJson<Review>(endpoint) });
  const preview = useMutation({ mutationFn: (text: string) => post<{ note: string }>({ action: "run", notes: text }) });
  const change = useMutation({
    mutationFn: ({ candidate, action }: NonNullable<typeof reviewing>) =>
      post<Review>({ action, version: candidate.version, digest: candidate.digest }),
    onSuccess: (result) => {
      client.setQueryData(queryKey, result);
      preview.reset();
      setReviewing(undefined);
    },
  });
  const actionLabels = { enable: "启用", disable: "停用", rollback: "回滚" };
  const error = change.error ?? preview.error ?? review.error;
  return (
    <section className="border-t border-[var(--border)] pt-8">
      <h2 className="text-lg font-semibold">复习笔记 Skill</h2>
      <p className="mt-2 text-sm text-[var(--foreground-muted)]">在聊天的工作模式中提交候选。启用后，可以在这里手动整理输入的文字。处理在本机完成，权限范围仅限本次输入。</p>
      <Button className="mt-3" variant="secondary" onClick={() => void review.refetch()} disabled={review.isFetching}>刷新候选</Button>
      {review.isPending ? <p className="mt-3 text-sm">正在读取候选…</p> : null}
      {review.data?.candidates.length === 0 ? <p className="mt-3 text-sm">暂无候选。</p> : null}
      <div className="mt-4 grid gap-3">
        {review.data?.candidates.map((candidate) => {
          const active = candidate.version === review.data.active_version;
          const action = active ? "disable" : candidate.approved && (review.data.active_version === null ||
            candidate.version < review.data.active_version) ? "rollback" : "enable";
          return (
            <article key={candidate.version} className="rounded-[var(--radius-md)] border border-[var(--border)] p-4">
              <h3 className="text-sm font-semibold">{candidate.manifest.name} · v{candidate.version} · {active ? "已启用" : candidate.approved ? "已审核" : "待审核"}</h3>
              <p className="mt-2 break-words text-sm">{candidate.manifest.purpose}</p>
              <p className="mt-1 break-words text-sm">输出标题「{candidate.manifest.heading}」</p>
              <details className="mt-2 text-xs">
                <summary className="cursor-pointer">来源与验证</summary>
                <p className="mt-2 break-all">工作任务 {candidate.work_id}</p>
                <p className="break-all">SHA-256 {candidate.digest}</p>
                <p>通过 {candidate.checks.join("、")}</p>
              </details>
              <Button className="mt-3" variant="secondary" disabled={change.isPending || preview.isPending}
                onClick={() => { change.reset(); setReviewing({ candidate, action }); }}>
                {actionLabels[action]}
              </Button>
              {reviewing?.candidate.version === candidate.version ? (
                <div className="mt-2 flex flex-wrap gap-2">
                  <Button disabled={change.isPending || preview.isPending} onClick={() => change.mutate(reviewing)}>确认{actionLabels[reviewing.action]} v{candidate.version}</Button>
                  <Button disabled={change.isPending} variant="secondary" onClick={() => setReviewing(undefined)}>取消</Button>
                </div>
              ) : null}
            </article>
          );
        })}
      </div>
      {review.data?.active_version != null ? (
        <form className="mt-4 grid gap-2" onSubmit={(event) => { event.preventDefault(); preview.mutate(notes); }}>
          <label htmlFor="study-skill-notes" className="text-sm font-semibold">复习内容</label>
          <textarea id="study-skill-notes" rows={4} maxLength={12000} value={notes}
            onChange={(event) => { setNotes(event.target.value); preview.reset(); }}
            className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-raised)] p-3" />
          <Button type="submit" className="w-fit" disabled={!notes.trim() || preview.isPending || change.isPending}>整理笔记</Button>
          {preview.data ? <output className="whitespace-pre-wrap break-words rounded-[var(--radius-md)] bg-[var(--surface)] p-3 text-sm">{preview.data.note}</output> : null}
        </form>
      ) : null}
      {error ? <p role="alert" className="mt-3 text-sm">{error.message}</p> : null}
    </section>
  );
}
