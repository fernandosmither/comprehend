import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type InterviewInput, type Interview } from "../api";
import { ErrorBanner, Spinner, StatusPill } from "../ui";

const BLANK: InterviewInput = {
  title: "",
  description: "",
  material: "",
  takes: "",
  rubric: "",
  always_probe: "",
  conduct_instructions: "",
  pass_threshold: 7,
  num_questions: 10,
};

export function InterviewEdit() {
  const { slug } = useParams();
  const editing = Boolean(slug);
  const navigate = useNavigate();

  const [form, setForm] = useState<InterviewInput>(BLANK);
  const [seedText, setSeedText] = useState("");
  const [status, setStatus] = useState<"draft" | "published">("draft");
  const [loading, setLoading] = useState(editing);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!slug) return;
    api
      .getInterview(slug)
      .then((iv: Interview) => {
        setForm({
          title: iv.title,
          description: iv.description,
          material: iv.material,
          takes: iv.takes,
          rubric: iv.rubric,
          always_probe: iv.always_probe,
          conduct_instructions: iv.conduct_instructions ?? "",
          pass_threshold: iv.pass_threshold,
          num_questions: iv.num_questions,
        });
        setSeedText((iv.seed_questions ?? []).join("\n"));
        setStatus(iv.status);
        setLoading(false);
      })
      .catch((e) => {
        setError(String(e.message));
        setLoading(false);
      });
  }, [slug]);

  function set<K extends keyof InterviewInput>(key: K, value: InterviewInput[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const payload: InterviewInput = {
      ...form,
      seed_questions: seedText
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean),
    };
    try {
      const saved = editing ? await api.updateInterview(slug!, payload) : await api.createInterview(payload);
      navigate(`/interviews/${saved.slug}`);
    } catch (e2) {
      setError(String((e2 as Error).message));
      setBusy(false);
    }
  }

  async function togglePublish() {
    if (!slug) return;
    const next = status === "published" ? "draft" : "published";
    const saved = await api.setStatus(slug, next).catch((e) => {
      setError(String(e.message));
      return null;
    });
    if (saved) setStatus(saved.status);
  }

  if (loading) return <Spinner />;

  return (
    <>
      <div className="page-head">
        <div>
          <Link to={editing ? `/interviews/${slug}` : "/"} className="backlink muted">
            ← back
          </Link>
          <h1 style={{ marginTop: 8 }}>{editing ? "Edit interview" : "New interview"}</h1>
        </div>
        {editing && (
          <div className="row">
            <StatusPill status={status} />
            <button type="button" className="btn btn--ghost btn--sm" onClick={togglePublish}>
              {status === "published" ? "Unpublish" : "Publish"}
            </button>
          </div>
        )}
      </div>

      {error && <ErrorBanner message={error} />}

      <form className="stack" onSubmit={save} style={{ marginTop: 18 }}>
        <div className="card card-pad stack">
          <Field label="Title">
            <input type="text" value={form.title} onChange={(e) => set("title", e.target.value)} required />
          </Field>
          <Field label="Description" hint="One line shown to participants when they list interviews.">
            <input type="text" value={form.description} onChange={(e) => set("description", e.target.value)} />
          </Field>
        </div>

        <div className="card card-pad stack">
          <Field label="Material" hint="The source content to internalize (markdown).">
            <textarea className="material" value={form.material} onChange={(e) => set("material", e.target.value)} rows={10} />
          </Field>
          <Field label="Your takes" hint="The opinionated framing & cruxes the interview should center on.">
            <textarea value={form.takes} onChange={(e) => set("takes", e.target.value)} rows={5} />
          </Field>
          <Field label="Rubric" hint="The key points understanding is graded against.">
            <textarea value={form.rubric} onChange={(e) => set("rubric", e.target.value)} rows={4} />
          </Field>
          <Field label="Always probe" hint="Anything every participant should always be pushed on.">
            <input type="text" value={form.always_probe} onChange={(e) => set("always_probe", e.target.value)} />
          </Field>
        </div>

        <div className="card card-pad stack">
          <div className="grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <Field label="Questions" hint="Target count.">
              <input
                type="number"
                min={1}
                value={form.num_questions}
                onChange={(e) => set("num_questions", Number(e.target.value))}
              />
            </Field>
            <Field label="Pass threshold" hint="Points needed to pass.">
              <input
                type="number"
                min={1}
                value={form.pass_threshold}
                onChange={(e) => set("pass_threshold", Number(e.target.value))}
              />
            </Field>
          </div>
          <Field label="Seed questions" hint="Optional, one per line. Claude still varies them.">
            <textarea value={seedText} onChange={(e) => setSeedText(e.target.value)} rows={4} />
          </Field>
          <Field label="Conduct override" hint="Leave blank to use the default Socratic conduct guide.">
            <textarea
              value={form.conduct_instructions ?? ""}
              onChange={(e) => set("conduct_instructions", e.target.value)}
              rows={4}
            />
          </Field>
        </div>

        <div className="row">
          <button className="btn btn--accent" type="submit" disabled={busy || !form.title}>
            {busy ? "Saving…" : editing ? "Save changes" : "Create draft"}
          </button>
          <Link to={editing ? `/interviews/${slug}` : "/"} className="btn btn--ghost">
            Cancel
          </Link>
        </div>
      </form>
    </>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="field">
      <label>
        {label}
        {hint && <span className="hint"> — {hint}</span>}
      </label>
      {children}
    </div>
  );
}
