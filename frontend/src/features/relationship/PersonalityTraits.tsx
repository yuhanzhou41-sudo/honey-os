import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fetchPersonalityTraits, savePersonalityTrait, type PersonalityTrait } from "../../api/companion";
import { Button } from "../../components/ui/Button";

const queryKey = ["companion", "personality"] as const;

export function PersonalityTraits() {
  const queryClient = useQueryClient();
  const { data, isPending, isError } = useQuery({ queryKey, queryFn: fetchPersonalityTraits });
  const [editing, setEditing] = useState<PersonalityTrait | null>(null);
  const [deleting, setDeleting] = useState(false);
  const mutation = useMutation({
    mutationFn: savePersonalityTrait,
    onSuccess: (result) => {
      queryClient.setQueryData(queryKey, result);
      setEditing(null);
      setDeleting(false);
    },
  });

  function cancel() {
    setEditing(null);
    setDeleting(false);
    mutation.reset();
  }

  return (
    <section className="mt-8 border-t border-[var(--border)] pt-6">
      <h2 className="text-base font-semibold">已形成的人格特征</h2>
      {isPending && <p className="mt-2 text-sm">正在读取</p>}
      {isError && <p className="mt-2 text-sm" role="alert">无法读取人格特征</p>}
      {data && !data.traits.length && <p className="mt-2 text-sm text-[var(--foreground-muted)]">暂时没有已形成的特征</p>}
      <ul className="mt-3 divide-y divide-[var(--border)]">
        {data?.traits.map((trait) => (
          <li key={`${trait.layer}/${trait.key}`} className="py-3">
            <p className="text-xs text-[var(--foreground-muted)]">{trait.layer === "stable_core" ? "稳定核心" : "相处方式"}</p>
            {editing?.layer === trait.layer && editing.key === trait.key ? (
              <div className="mt-2 grid gap-2">
                {deleting ? <p className="text-sm">删除这项人格特征？</p> : (
                  <textarea aria-label="人格特征描述" maxLength={280} value={editing.statement}
                    onChange={(event) => setEditing({ ...editing, statement: event.target.value })}
                    className="rounded border border-[var(--border)] bg-[var(--surface)] p-2" />
                )}
                <div className="flex gap-2">
                  <Button type="button" disabled={mutation.isPending || (!deleting && !editing.statement.trim())}
                    onClick={() => mutation.mutate({ ...editing, statement: deleting ? null : editing.statement })}>
                    {deleting ? "确认删除" : "保存"}
                  </Button>
                  {!deleting && <Button type="button" variant="ghost" disabled={mutation.isPending} onClick={() => setDeleting(true)}>删除</Button>}
                  <Button type="button" variant="ghost" disabled={mutation.isPending} onClick={cancel}>取消</Button>
                </div>
                {mutation.isError && <span role="alert" className="text-sm text-[var(--danger)]">未能保存，请重试</span>}
              </div>
            ) : (
              <div className="flex items-start justify-between gap-3">
                <p className="mt-1 whitespace-pre-wrap break-words text-sm">{trait.statement}</p>
                <Button type="button" variant="ghost" disabled={mutation.isPending}
                  onClick={() => { cancel(); setEditing(trait); }}>编辑</Button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
