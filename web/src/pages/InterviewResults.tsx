import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type ResultsDetail } from "../api";
import { Bar, ErrorBanner, PassPill, Spinner, Stat, StatusPill, asLines, fmtDate, fmtDuration } from "../ui";

export function InterviewResults() {
  const { slug } = useParams();
  const [data, setData] = useState<ResultsDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    api.results(slug).then(setData).catch((e) => setError(String(e.message)));
  }, [slug]);

  if (error) return <ErrorBanner message={error} />;
  if (!data) return <Spinner />;

  const { interview, stats, participants } = data;

  return (
    <>
      <div className="page-head">
        <div>
          <Link to="/" className="backlink muted">
            ← all interviews
          </Link>
          <div className="row" style={{ marginTop: 8, gap: 14 }}>
            <h1>{interview.title}</h1>
            <StatusPill status={interview.status} />
          </div>
          {interview.description && <p>{interview.description}</p>}
        </div>
        <Link className="btn btn--ghost" to={`/interviews/${slug}/edit`}>
          Edit
        </Link>
      </div>

      <div className="statgrid" style={{ marginBottom: 28 }}>
        <Stat value={stats.participants} label="Participants" />
        <Stat value={stats.passed} label="Passed" />
        <Stat
          value={stats.pass_rate === null ? "—" : `${Math.round(stats.pass_rate * 100)}%`}
          label="Pass rate"
        />
        <Stat
          value={stats.avg_score_pct === null ? "—" : `${Math.round(stats.avg_score_pct * 100)}%`}
          label="Avg score"
        />
      </div>

      {participants.length === 0 ? (
        <div className="empty">
          <h3>No attempts yet</h3>
          <p>
            Once people take this via their connector link, their results land here.{" "}
            {interview.status === "draft" && "It's still a draft — publish it first."}
          </p>
        </div>
      ) : (
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>Person</th>
                <th>Result</th>
                <th className="num">Best</th>
                <th className="num">Attempts</th>
                <th className="num">Time</th>
                <th>Last activity</th>
              </tr>
            </thead>
            <tbody>
              {participants.map((p) => (
                <tr key={p.person_id}>
                  <td>
                    <Link to={`/people/${p.person_id}`} className="row-title">
                      {p.name}
                    </Link>
                    {p.last_summary && (
                      <div className="row-sub">
                        {asLines(p.last_summary.confusions) ? `struggled: ${asLines(p.last_summary.confusions)}` : ""}
                      </div>
                    )}
                  </td>
                  <td>
                    <PassPill passed={p.passed} />
                  </td>
                  <td className="num">
                    {p.best_score === null ? "—" : `${p.best_score}/${p.max_score}`}
                  </td>
                  <td className="num">{p.attempts}</td>
                  <td className="num">{fmtDuration(p.last_time_spent_seconds)}</td>
                  <td className="faint mono" style={{ fontSize: "0.8rem" }}>
                    {fmtDate(p.last_activity)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="row" style={{ marginTop: 22, justifyContent: "space-between" }}>
        <span className="faint" style={{ fontSize: "0.85rem" }}>
          Pass mark: {interview.pass_threshold} / {interview.num_questions}
        </span>
        <div style={{ width: 200 }}>
          <Bar value={stats.pass_rate} />
        </div>
      </div>
    </>
  );
}
