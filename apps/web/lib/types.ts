export type Organization = { id: string; name: string; slug: string; role: string };
export type Project = {
  id: string; organization_id: string; name: string; description: string;
  status: string; version: number; created_at: string;
};
export type Task = {
  id: string; project_id: string; title: string; description: string;
  status: "todo" | "in_progress" | "review" | "done";
  priority: string; assignee_id: string | null; due_at: string | null;
  position: number; version: number; created_at: string;
};
export type Suggestion = {
  id: string; task_id: string; suggestion_type: string; content: Record<string, unknown>;
  confidence: number; rationale: string; features_used: Record<string, unknown>;
  references: Array<Record<string, unknown>>; expected_effect: string; risks: string[];
  decision: string; revised_content: Record<string, unknown> | null; inference_ms: number;
  created_at: string;
};

