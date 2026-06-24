// Thin fetch wrapper. Same-origin in prod and via the Vite dev proxy, so the signed
// session cookie rides along automatically — no token juggling in JS.

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    credentials: "same-origin",
    headers: opts.body ? { "Content-Type": "application/json" } : {},
    ...opts,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-json error body */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return null as T;
  return res.json() as Promise<T>;
}

const body = (data: unknown) => ({ body: JSON.stringify(data) });

// ---- types ----
export interface OverviewRow {
  slug: string;
  title: string;
  status: "draft" | "published";
  participants: number;
  attempts: number;
  passed: number;
  pass_rate: number | null;
  avg_score_pct: number | null;
  avg_time_spent_seconds: number | null;
}

export interface Interview {
  slug: string;
  title: string;
  description: string;
  material: string;
  takes: string;
  rubric: string;
  always_probe: string;
  conduct_instructions: string | null;
  seed_questions: string[] | null;
  pass_threshold: number;
  num_questions: number;
  status: "draft" | "published";
  created_at: string;
  updated_at: string;
}

export interface ParticipantRow {
  person_id: number;
  name: string;
  email: string | null;
  attempts: number;
  best_score: number | null;
  max_score: number;
  passed: boolean;
  last_activity: string | null;
  last_summary: Summary | null;
  last_time_spent_seconds: number | null;
}

export interface Summary {
  confusions?: string | string[];
  strengths?: string | string[];
  development?: string | string[];
}

export interface ResultsDetail {
  interview: Pick<Interview, "slug" | "title" | "description" | "status" | "pass_threshold" | "num_questions">;
  stats: OverviewRow;
  participants: ParticipantRow[];
}

export interface Person {
  id: number;
  name: string;
  email: string | null;
  active: boolean;
  profile_note: string | null;
  connector_url: string;
}

export interface PersonHistory {
  person: Person;
  history: {
    interview_slug: string | null;
    interview_title: string | null;
    started_at: string;
    submitted_at: string | null;
    score: number | null;
    max_score: number | null;
    passed: boolean | null;
    time_spent_seconds: number | null;
    summary: Summary | null;
  }[];
}

export type InterviewInput = Partial<Omit<Interview, "created_at" | "updated_at" | "status">> & {
  title: string;
};

export interface Feedback {
  id: number;
  person_id: number;
  person_name: string;
  interview_id: number;
  interview_title: string;
  interview_slug: string;
  body: string;
  context: string | null;
  reviewed: boolean;
  created_at: string;
}

export const api = {
  me: () => req<{ authenticated: boolean }>("/api/me"),
  login: (password: string) => req<{ ok: true }>("/api/login", { method: "POST", ...body({ password }) }),
  logout: () => req<{ ok: true }>("/api/logout", { method: "POST" }),

  listInterviews: () => req<{ interviews: OverviewRow[] }>("/api/interviews").then((r) => r.interviews),
  getInterview: (slug: string) => req<Interview>(`/api/interviews/${slug}`),
  createInterview: (data: InterviewInput) => req<Interview>("/api/interviews", { method: "POST", ...body(data) }),
  updateInterview: (slug: string, data: Partial<InterviewInput>) =>
    req<Interview>(`/api/interviews/${slug}`, { method: "PUT", ...body(data) }),
  setStatus: (slug: string, status: "draft" | "published") =>
    req<Interview>(`/api/interviews/${slug}/status`, { method: "POST", ...body({ status }) }),
  results: (slug: string) => req<ResultsDetail>(`/api/results/${slug}`),

  listPeople: () => req<{ people: Person[] }>("/api/people").then((r) => r.people),
  createPerson: (name: string, email?: string) =>
    req<{ id: number; name: string; email: string | null; connector_url: string }>("/api/people", {
      method: "POST",
      ...body({ name, email }),
    }),
  setPersonActive: (id: number, active: boolean) =>
    req<{ ok: true }>(`/api/people/${id}/active`, { method: "POST", ...body({ active }) }),
  getPerson: (id: number) => req<PersonHistory>(`/api/people/${id}`),

  listFeedback: () => req<{ feedback: Feedback[] }>("/api/feedback").then((r) => r.feedback),
  feedbackCount: () => req<{ unreviewed: number }>("/api/feedback/count").then((r) => r.unreviewed),
  setFeedbackReviewed: (id: number, reviewed: boolean) =>
    req<{ ok: true }>(`/api/feedback/${id}/reviewed`, { method: "POST", ...body({ reviewed }) }),
};
