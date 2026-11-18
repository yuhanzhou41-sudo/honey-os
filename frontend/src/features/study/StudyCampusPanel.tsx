import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { companionAccess, SOURCE_LABELS } from "../../api/companion-access";
import { profilePrefix } from "../../api/client";

type CampusLink = {
  id: string;
  name: string;
  description: string;
  url: string;
  placeholder: string;
};

const STORAGE_KEY = "honeyos.campus.links";

const DEFAULTS: CampusLink[] = [
  {
    id: "chaoxing",
    name: "学习通",
    description: "课程任务、签到与课程资料。登录和操作在浏览器里完成。",
    url: "https://i.chaoxing.com/",
    placeholder: "https://i.chaoxing.com/",
  },
  {
    id: "jwc",
    name: "教务系统",
    description: "课表、考试安排与成绩查询。首次使用需自己登录。",
    url: "https://jwc.cqmu.edu.cn/",
    placeholder: "学校教务系统网址",
  },
  {
    id: "zongce",
    name: "综测",
    description: "学年综合测评填报。带 ticket 的链接会过期，这里只保留系统首页。",
    url: "https://xgxt.cqmu.edu.cn/",
    placeholder: "https://xgxt.cqmu.edu.cn/",
  },
  {
    id: "erke",
    name: "二课",
    description: "第二课堂活动与学分。校内系统地址请填写一次，之后从这里进入。",
    url: "",
    placeholder: "第二课堂系统网址",
  },
  {
    id: "portal",
    name: "校园门户",
    description: "信息门户登录（统一身份认证）。旧地址 portal.paas 已停用，这里已换成新地址。",
    url: "https://my.cqmu.edu.cn/",
    placeholder: "https://my.cqmu.edu.cn/",
  },
];

function stripTicket(raw: string): { url: string; stripped: boolean } {
  try {
    const parsed = new URL(raw);
    if (!parsed.searchParams.has("ticket")) return { url: raw, stripped: false };
    parsed.searchParams.delete("ticket");
    return { url: parsed.toString(), stripped: true };
  } catch {
    return { url: raw, stripped: false };
  }
}

function loadLinks(): CampusLink[] {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}") as Record<string, string>;
    return DEFAULTS.map((item) => {
      const saved = (raw[item.id] ?? "").trim();
      if (item.id === "portal" && saved.includes("portal.paas.cqmu.edu.cn")) {
        return { ...item, url: item.url };
      }
      return { ...item, url: saved || item.url };
    });
  } catch {
    return DEFAULTS;
  }
}

export function StudyCampusPanel() {
  const [links, setLinks] = useState<CampusLink[]>(loadLinks);
  const [message, setMessage] = useState("");
  const work = useQuery({ queryKey: ["companion", "work"], queryFn: companionAccess.work, retry: false });
  const access = useQuery({ queryKey: ["companion", "events"], queryFn: companionAccess.events, retry: false });

  function update(id: string, url: string) {
    setLinks((rows) => rows.map((item) => (item.id === id ? { ...item, url } : item)));
  }

  function save() {
    const payload: Record<string, string> = {};
    let stripped = false;
    const next = links.map((item) => {
      const clean = stripTicket(item.url.trim());
      if (clean.stripped) stripped = true;
      payload[item.id] = clean.url;
      return { ...item, url: clean.url };
    });
    setLinks(next);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    setMessage(stripped ? "入口已保存；会过期的 ticket 已去掉，登录时系统会重新跳转。" : "入口已保存在本机浏览器。");
  }

  function open(link: CampusLink) {
    const clean = stripTicket(link.url.trim());
    if (!clean.url) {
      setMessage(`请先填写${link.name}的网址。`);
      return;
    }
    if (clean.stripped) {
      setMessage(`已去掉会过期的 ticket，打开首页后按提示重新登录。`);
    }
    window.open(clean.url, "_blank", "noopener,noreferrer");
  }

  const prefix = profilePrefix();

  return (
    <div className="space-y-5 text-sm">
      <p className="text-[var(--foreground-muted)]">
        这里只保存入口链接，不保存账号密码；登录、签到现在网页里由你自己完成。
      </p>
      <p className="text-xs text-[var(--foreground-muted)]">
        这些站点在公网就能访问，不需要校园网或 VPN。若打不开，可先尝试关闭代理，或把 *.cqmu.edu.cn 设为直连。
      </p>

      <section className="space-y-3">
        {links.map((link) => (
          <article key={link.id} className="rounded-xl border border-[var(--border)] p-3">
            <div className="flex items-center justify-between gap-3">
              <h3 className="font-medium">{link.name}</h3>
              <span className="text-xs text-[var(--foreground-muted)]">
                {link.url.trim() ? "已设置入口" : "待填写网址"}
              </span>
            </div>
            <p className="mt-1 text-xs text-[var(--foreground-muted)]">{link.description}</p>
            <div className="mt-2 flex gap-2">
              <input
                aria-label={`${link.name}网址`}
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm"
                placeholder={link.placeholder}
                value={link.url}
                onChange={(event) => update(link.id, event.target.value)}
              />
              <button type="button" className="rounded-full border border-[var(--border)] px-3 py-1.5 text-sm"
                onClick={() => open(link)}>
                打开
              </button>
            </div>
          </article>
        ))}
        <button type="button" className="rounded-full bg-[var(--accent)] px-3 py-1.5 text-sm font-medium text-white"
          onClick={save}>
          保存入口
        </button>
      </section>

      <section className="space-y-3 border-t border-[var(--border)] pt-3">
        <h3 className="font-medium">工作模式</h3>
        <p className="text-xs text-[var(--foreground-muted)]">
          工作模式负责需要连续操作的任务；在聊天里说“进入工作模式”开始，这里只显示状态。
        </p>
        <div className="rounded-xl border border-[var(--border)] p-3">
          {work.isPending ? (
            <p className="text-xs text-[var(--foreground-muted)]">正在读取状态…</p>
          ) : work.isError ? (
            <p className="text-xs text-[var(--foreground-muted)]">当前版本没有提供工作模式接口。</p>
          ) : (
            <>
              <div className="flex items-center justify-between">
                <span>当前状态</span>
                <span className={work.data?.enabled ? "text-[var(--accent)]" : "text-[var(--foreground-muted)]"}>
                  {work.data?.enabled ? "进行中" : "未开启"}
                </span>
              </div>
              {work.data?.enabled && (
                <p className="mt-1 truncate text-xs text-[var(--foreground-muted)]">
                  会话 {work.data.session_id || "未知"} · 任务 {work.data.work_id || "未知"}
                </p>
              )}
            </>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <a className="rounded-full border border-[var(--border)] px-3 py-1.5 text-sm"
            href={`${prefix}/`}>
            去聊天开始工作模式
          </a>
          <a className="rounded-full border border-[var(--border)] px-3 py-1.5 text-sm"
            href={`${prefix}/settings`}>
            管理事件权限
          </a>
        </div>
      </section>

      <section className="space-y-2 border-t border-[var(--border)] pt-3">
        <h3 className="font-medium">事件权限与访问记录</h3>
        {access.isPending ? (
          <p className="text-xs text-[var(--foreground-muted)]">正在读取…</p>
        ) : access.isError ? (
          <p className="text-xs text-[var(--foreground-muted)]">当前版本没有提供事件记录接口。</p>
        ) : (
          <>
            <div>
              <p className="text-xs text-[var(--foreground-muted)]">生效中的读取授权</p>
              {access.data?.grants?.length ? (
                <ul className="mt-1 space-y-1">
                  {access.data.grants.map((grant) => (
                    <li key={`${grant.source}-${grant.expires_at}`} className="flex justify-between gap-3 text-xs">
                      <span>{SOURCE_LABELS[grant.source] || grant.source}</span>
                      <span className="text-[var(--foreground-muted)]">
                        到期 {new Date(grant.expires_at).toLocaleString()}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-xs text-[var(--foreground-muted)]">当前没有生效的读取授权。</p>
              )}
            </div>
            <div>
              <p className="text-xs text-[var(--foreground-muted)]">最近访问</p>
              {access.data?.audit?.length ? (
                <ul className="mt-1 space-y-1">
                  {access.data.audit.slice(0, 8).map((row, index) => (
                    <li key={`${row.checked_at}-${index}`} className="flex justify-between gap-3 text-xs">
                      <span>{SOURCE_LABELS[row.source] || row.source}</span>
                      <span className="text-[var(--foreground-muted)]">
                        {row.allowed ? "允许" : "拒绝"} · {new Date(row.checked_at).toLocaleString()}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-xs text-[var(--foreground-muted)]">还没有访问记录。</p>
              )}
            </div>
          </>
        )}
      </section>

      {message && <p className="text-xs text-[var(--foreground-muted)]">{message}</p>}
    </div>
  );
}
