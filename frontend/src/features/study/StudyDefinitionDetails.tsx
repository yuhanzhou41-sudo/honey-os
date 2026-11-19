import type { StudyFlexSlot, StudyTaskDefinition } from "../../api/study";

const priorities = { must: "必做", standard: "标准", optional: "选做" };
const kinds = { study: "学习", review: "复习", quiz: "测验", flashcard: "闪卡" };

export function TaskDefinitionDetails({ task }: { task: StudyTaskDefinition }) {
  if (!task.priority && !task.kind) return null;
  return <span className="text-xs text-[var(--foreground-muted)]">
    {priorities[task.priority ?? "standard"]} · {kinds[task.kind ?? "study"]}
    {task.minimum_required ? " · 保底任务" : ""}
  </span>;
}

export function FlexSlotList({ slots = [] }: { slots?: StudyFlexSlot[] }) {
  if (!slots.length) return null;
  return <ul aria-label="机动时间" className="my-2 space-y-1 text-sm text-[var(--foreground-muted)]">
    {slots.map(slot => <li key={slot.id}>
      {slot.scheduled_date} · 机动时间 {slot.planned_minutes} 分钟
    </li>)}
  </ul>;
}
