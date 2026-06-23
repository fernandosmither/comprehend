import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type PersonHistory } from "../api";
import { CopyField, ErrorBanner, PassPill, Spinner, asLines, fmtDate, fmtDuration } from "../ui";

export function PersonDetail() {
  const { id } = useParams();
  const [data, setData] = useState<PersonHistory | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api.getPerson(Number(id)).then(setData).catch((e) => setError(String(e.message)));
  }, [id]);

  if (error) return <ErrorBanner message={error} />;
  if (!data) return <Spinner />;

  const { person, history } = data;

  return (
    <>
      <div className="page-head">
        <div>
          <Link to="/people" className="backlink muted">
            ← all people
          </Link>
          <h1 style={{ marginTop: 8 }}>{person.name}</h1>
          {person.email && <p>{person.email}</p>}
        </div>
        {!person.active && <span className="pill fail">disabled</span>}
      </div>

      <div className="stack" style={{ marginBottom: 26 }}>
        {person.profile_note && (
          <div className="note-card">
            <span className="eyebrow">Rolling profile</span>
            <div style={{ marginTop: 6 }}>{person.profile_note}</div>
          </div>
        )}
        <div className="field">
          <label>Connector link</label>
          <CopyField value={person.connector_url} />
        </div>
      </div>

      <h2 style={{ marginBottom: 14 }}>History</h2>
      {history.length === 0 ? (
        <div className="empty">
          <h3>No attempts yet</h3>
          <p>{person.name} hasn't taken any interviews.</p>
        </div>
      ) : (
        <div className="stack">
          {history.map((h, i) => (
            <div className="card card-pad" key={i}>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <div className="row" style={{ gap: 12 }}>
                  {h.interview_slug ? (
                    <Link to={`/interviews/${h.interview_slug}`} className="row-title">
                      {h.interview_title}
                    </Link>
                  ) : (
                    <span className="row-title">{h.interview_title ?? "—"}</span>
                  )}
                  <PassPill passed={h.passed} />
                </div>
                <div className="row faint mono" style={{ fontSize: "0.8rem", gap: 16 }}>
                  <span>
                    {h.score === null ? "—" : `${h.score}/${h.max_score}`}
                  </span>
                  <span>{fmtDuration(h.time_spent_seconds)}</span>
                  <span>{fmtDate(h.submitted_at ?? h.started_at)}</span>
                </div>
              </div>
              {h.summary && (
                <div className="grid" style={{ gridTemplateColumns: "1fr 1fr 1fr", marginTop: 14, gap: 16 }}>
                  <SummaryCol title="Confused by" value={asLines(h.summary.confusions)} />
                  <SummaryCol title="Strong on" value={asLines(h.summary.strengths)} />
                  <SummaryCol title="To develop" value={asLines(h.summary.development)} />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}

function SummaryCol({ title, value }: { title: string; value: string }) {
  return (
    <div>
      <span className="eyebrow">{title}</span>
      <p className="muted" style={{ margin: "6px 0 0", fontSize: "0.9rem" }}>
        {value || "—"}
      </p>
    </div>
  );
}
