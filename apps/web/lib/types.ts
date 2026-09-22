export type Organization = { id: string; name: string; slug: string; role: string };
export type Project = {
  id: string; organization_id: string; name: string; description: string;
  objective: string; success_criteria: string; start_date: string | null; due_date: string | null;
  status: string; version: number; created_at: string;
};
export type ProjectSummary = Project & {
  my_role: "project_admin" | "editor" | "viewer"; task_count: number;
  status_counts: Record<string, number>; completion_rate: number; unread_count: number;
};
export type ProjectMember = {
  id: string; user_id: string; display_name: string; email: string;
  organization_role: string; role: "project_admin" | "editor" | "viewer";
  invitation_status: "pending" | "accepted" | "declined" | "revoked";
  invited_at: string; joined_at: string | null; version: number;
  project_name?: string | null;
};
export type InviteCandidate = {
  user_id: string; display_name: string; email: string; organization_role: string;
  membership_status: string | null;
};
export type ProjectMessage = {
  id: string; project_id: string; author_id: string; author_name: string; body: string; created_at: string;
};
export type ProjectAISuggestion = {
  id: string; project_id: string | null; suggestion_type: string;
  proposed_values: Partial<Project>; confidence: number; rationale: string;
  evidence: Array<Record<string, unknown>>; assumptions: string[]; risks: string[];
  expected_effect: string; provider: string; model_id: string | null;
  model_version: string | null; inference_ms: number; decision: string; created_at: string;
};
export type Task = {
  id: string; project_id: string; title: string; description: string; notes: string;
  status: TaskStatus;
  priority: string; assignee_id: string | null; due_at: string | null;
  position: number; version: number; created_at: string;
};
export type TaskStatus = "todo" | "in_progress" | "on_hold" | "done";
export type TaskDraft = {
  client_id: string; title: string; description: string; notes: string;
  priority: "low" | "medium" | "high" | "urgent"; due_at: string;
  source: "manual" | "ai"; selected: boolean; rationale?: string;
  confidence?: number; assumptions?: string[];
};
export type Suggestion = {
  id: string; task_id: string; suggestion_type: string; content: Record<string, unknown>;
  confidence: number; rationale: string; features_used: Record<string, unknown>;
  references: Array<Record<string, unknown>>; expected_effect: string; risks: string[];
  decision: string; revised_content: Record<string, unknown> | null; inference_ms: number;
  created_at: string;
};

