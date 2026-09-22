"use client";

import {
  DndContext, DragEndEvent, KeyboardSensor, PointerSensor, closestCorners,
  useDroppable, useSensor, useSensors,
} from "@dnd-kit/core";
import { SortableContext, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical, Pencil, Sparkles } from "lucide-react";
import type { Task, TaskStatus } from "@/lib/types";

const columns: Array<[TaskStatus, string]> = [
  ["todo", "未着手"], ["in_progress", "進行中"], ["on_hold", "保留"], ["done", "終了"],
];

function SortableTask({ task, canManage, onEdit, onSuggest }: {
  task: Task; canManage: boolean; onEdit: (task: Task) => void; onSuggest: (task: Task) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: task.id, disabled: !canManage });
  return <article ref={setNodeRef} style={{ transform: CSS.Transform.toString(transform), transition }} className={`card p-4 ${isDragging ? "opacity-50 shadow-lg" : ""}`} {...attributes} {...listeners}>
    <div className="flex items-start justify-between gap-2"><div className="flex min-w-0 items-start gap-2">{canManage && <GripVertical className="mt-1 size-4 shrink-0 text-slate-400" aria-hidden="true" />}<h3 className="font-medium leading-6">{task.title}</h3></div><span className="text-xs text-slate-500">{task.priority}</span></div>
    <p className="mt-2 line-clamp-2 text-sm text-slate-600">{task.description || "概要なし"}</p>
    {task.notes && <p className="mt-2 line-clamp-2 rounded bg-slate-50 p-2 text-xs text-slate-600">補足: {task.notes}</p>}
    <div className="mt-4 flex flex-wrap items-center justify-between gap-2"><span className="text-xs text-slate-500">{task.due_at ? new Date(task.due_at).toLocaleDateString("ja-JP") : "期限なし"}</span><div className="flex gap-1">{canManage && <button className="button-secondary px-2 py-1 text-sm" onPointerDown={(e) => e.stopPropagation()} onClick={() => onEdit(task)}><Pencil className="size-4" />編集</button>}<button className="button-secondary px-2 py-1 text-sm" onPointerDown={(e) => e.stopPropagation()} onClick={() => onSuggest(task)}><Sparkles className="size-4" />AI提案</button></div></div>
  </article>;
}

function Column({ status, label, tasks, canManage, onEdit, onSuggest }: {
  status: TaskStatus; label: string; tasks: Task[]; canManage: boolean;
  onEdit: (task: Task) => void; onSuggest: (task: Task) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: `column:${status}` });
  return <section aria-labelledby={`column-${status}`}><div className="mb-3 flex items-center justify-between"><h2 id={`column-${status}`} className="font-medium">{label}</h2><span className="text-sm text-slate-500">{tasks.length}</span></div><div ref={setNodeRef} className={`min-h-40 space-y-3 rounded-xl p-2 transition ${isOver ? "bg-blue-50 ring-2 ring-blue-300" : "bg-slate-100/60"}`}><SortableContext items={tasks.map((task) => task.id)} strategy={verticalListSortingStrategy}>{tasks.map((task) => <SortableTask key={task.id} task={task} canManage={canManage} onEdit={onEdit} onSuggest={onSuggest} />)}</SortableContext>{!tasks.length && <p className="grid min-h-32 place-items-center text-sm text-slate-400">ここにドロップ</p>}</div></section>;
}

export function Kanban({ tasks, canManage, onEdit, onSuggest, onMove }: {
  tasks: Task[]; canManage: boolean; onEdit: (task: Task) => void; onSuggest: (task: Task) => void;
  onMove: (task: Task, status: TaskStatus, position: number) => void;
}) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const endDrag = ({ active, over }: DragEndEvent) => {
    if (!over || !canManage) return;
    const task = tasks.find((item) => item.id === active.id);
    if (!task) return;
    const overId = String(over.id);
    const overTask = tasks.find((item) => item.id === overId);
    const status = overId.startsWith("column:") ? overId.slice(7) as TaskStatus : overTask?.status;
    if (!status) return;
    const targetTasks = tasks.filter((item) => item.status === status).sort((a, b) => a.position - b.position);
    const targetIndex = overTask ? targetTasks.findIndex((item) => item.id === overTask.id) : targetTasks.length;
    const position = targetIndex < 0 ? targetTasks.length : targetIndex;
    if (status !== task.status || position !== task.position) onMove(task, status, position);
  };
  return <DndContext sensors={sensors} collisionDetection={closestCorners} onDragEnd={endDrag}><div className="grid gap-4 xl:grid-cols-4">{columns.map(([status, label]) => <Column key={status} status={status} label={label} tasks={tasks.filter((task) => task.status === status).sort((a, b) => a.position - b.position)} canManage={canManage} onEdit={onEdit} onSuggest={onSuggest} />)}</div></DndContext>;
}
