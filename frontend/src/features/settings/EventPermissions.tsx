import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { requestJson } from "../../api/client";
import { Button } from "../../components/ui/Button";
import { useHoneyStore } from "../../runtime/honey-store";

const endpoint = "/api/companion/events";
const queryKey = ["event-permissions"];
const sourceLabels = { chat: "聊天", study: "学习任务", reminder: "提醒" };
type Source = keyof typeof sourceLabels;
type EventReview = {
  grants: Array<{ source: Source; expires_at: string }>;
  audit: Array<{ source: Source; checked_at: string; allowed: boolean }>;
  events: Array<{ id: string; kind: string; occurred_at: string; source_ref: string }>;
};

export function EventPermissions() {
  const sessionId = useHoneyStore((state) => state.sessionId);
  const queryClient = useQueryClient();
  const review = useQuery({ queryKey, queryFn: () => requestJson<EventReview>(endpoint) });
  const [selection, setSelection] = useState<{ source: Source; events: EventReview["events"] }>();
  const action = useMutation({
    mutationFn: async ({ source, method }: { source: Source; method: "GET" | "POST" | "DELETE" }) => {
      const url = method === "GET"
        ? `${endpoint}?${new URLSearchParams({ source, session_id: sessionId || "" })}`
        : `${endpoint}/${source}/grant`;
      return { source, method, result: await requestJson<EventReview>(url, { method }) };
    },
    onSuccess: ({ source, method, result }) => {
      queryClient.setQueryData(queryKey, result);
      if (method === "GET") setSelection({ source, events: result.events });
    },
    onSettled: () => void queryClient.invalidateQueries({ queryKey }),
  });

  function perform(source: Source, method: "GET" | "POST" | "DELETE") {
    setSelection(undefined);
    action.mutate({ source, method });
  }

  return (
    <section className="border-t border-[var(--border)] pt-8">
      <h2 className="text-lg font-semibold">事件权限</h2>
      <p className="mt-2 text-sm text-[var(--foreground-muted)]">按来源授权一小时。查看时才读取事件类型、时间和来源编号，聊天内容与学习正文继续保存在各自的数据库里。</p>
      {review.isPending ? <p className="mt-3 text-sm">正在读取权限…</p> : null}
      {review.isError ? <p role="alert" className="mt-3 text-sm">{review.error.message}</p> : null}
      {review.data ? <div className="mt-3 grid gap-3">
        {(Object.keys(sourceLabels) as Source[]).map((source) => {
          const grant = review.data.grants.find((item) => item.source === source);
          return <div key={source} className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <strong className="block text-sm">{sourceLabels[source]}</strong>
              <small className="text-[var(--foreground-muted)]">
                {grant ? `有效期至 ${new Date(grant.expires_at).toLocaleTimeString()}` : "未授权"}
              </small>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button disabled={action.isPending} onClick={() => perform(source, grant ? "DELETE" : "POST")}>
                {grant ? "撤销" : "允许一小时"}
              </Button>
              {grant ? <Button disabled={action.isPending || (source === "chat" && !sessionId)} onClick={() => perform(source, "GET")}>查看事件</Button> : null}
            </div>
          </div>;
        })}
      </div> : null}
      {action.error ? <p role="alert" className="mt-3 text-sm">{action.error.message}</p> : null}
      {selection && review.data?.grants.some((grant) => grant.source === selection.source) ? (
        <div className="mt-4 text-sm">
          <h3 className="font-semibold">{sourceLabels[selection.source]}事件</h3>
          {selection.events.length ? <ul className="mt-2 grid gap-1">
            {selection.events.map((item) => <li key={item.id} title={item.source_ref}>{new Date(item.occurred_at).toLocaleString()} · {item.kind}</li>)}
          </ul> : <p className="mt-2">暂无事件。</p>}
        </div>
      ) : null}
      {review.data?.audit.length ? <details className="mt-4 text-sm">
        <summary>读取记录</summary>
        <ul className="mt-2 grid gap-1">
          {review.data.audit.map((item, index) => (
            <li key={index}>{new Date(item.checked_at).toLocaleString()} · {sourceLabels[item.source]} · {item.allowed ? "已允许" : "已拒绝"}</li>
          ))}
        </ul>
      </details> : null}
    </section>
  );
}
