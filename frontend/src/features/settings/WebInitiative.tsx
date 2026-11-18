import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { requestJson } from "../../api/client";
import { Button } from "../../components/ui/Button";

const endpoint = "/api/companion/web-initiative";
const queryKey = ["web-initiative"];
type Preference = {
  enabled: boolean;
  paused_for_work: boolean;
  last_check_at: string | null;
  recent_deliveries: string[];
};

export function WebInitiative() {
  const client = useQueryClient();
  const preference = useQuery({
    queryKey, queryFn: () => requestJson<Preference>(endpoint), refetchInterval: 30_000,
  });
  const toggle = useMutation({
    mutationFn: (enabled: boolean) => requestJson<Preference>(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    }),
    onSuccess: (result) => client.setQueryData(queryKey, result),
  });

  return (
    <section className="border-t border-[var(--border)] pt-8">
      <h2 className="text-lg font-semibold">主动联系</h2>
      <p className="mt-2 text-sm text-[var(--foreground-muted)]">白天每小时评估，23:00–08:00 每三小时评估。聊天活跃时暂停检查。Honey 想开口时，消息出现在这里的聊天里。</p>
      {preference.data ? (
        <Button className="mt-3" disabled={toggle.isPending} onClick={() => toggle.mutate(!preference.data?.enabled)}>
          {preference.data.enabled ? "关闭主动联系" : "开启主动联系"}
        </Button>
      ) : null}
      {preference.data ? (
        <div className="mt-3 grid gap-2 text-sm text-[var(--foreground-muted)]">
          {preference.data.paused_for_work ? <p>工作模式进行中，暂缓主动联系。</p> : null}
          <p>最近评估 {preference.data.last_check_at ? new Date(preference.data.last_check_at).toLocaleString() : "暂无记录"}</p>
          <details>
            <summary className="cursor-pointer">最近发送记录</summary>
            {preference.data.recent_deliveries?.length ? (
              <ol className="mt-2 grid gap-1">
                {preference.data.recent_deliveries.map((sentAt, index) => (
                  <li key={`${sentAt}-${index}`}>{new Date(sentAt).toLocaleString()}</li>
                ))}
              </ol>
            ) : <p className="mt-2">暂无发送记录。</p>}
          </details>
        </div>
      ) : null}
      {preference.isPending ? <p className="mt-2 text-sm">正在读取设置…</p> : null}
      {preference.error || toggle.error ? <p role="alert" className="mt-2 text-sm">{(toggle.error || preference.error)?.message}</p> : null}
    </section>
  );
}
