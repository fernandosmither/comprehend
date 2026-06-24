import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type OverviewRow } from "../api";
import { Bar, ErrorBanner, Spinner, StatusPill, fmtDuration } from "../ui";

export function Interviews() {
  const [rows, setRows] = useState<OverviewRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listInterviews().then(setRows).catch((e) => setError(String(e.message)));
  }, []);

  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">Registry</span>
          <h1>Interviews</h1>
          <p>Material you want people to internalize. Create one here, or author it from your own Claude via the owner connector.</p>
        </div>
        <Link className="btn btn--accent" to="/interviews/new">
          + New interview
        </Link>
      </div>

      {error && <ErrorBanner message={error} />}
      {!rows && !error && <Spinner />}

      {rows && rows.length === 0 && (
        <div className="empty">
          <h3>No interviews yet</h3>
          <p>Create one here, or tell your Claude: "make an interview from &lt;link&gt;".</p>
        </div>
      )}

      {rows && rows.length > 0 && (
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>Interview</th>
                <th>Status</th>
                <th className="num">People</th>
                <th>Pass rate</th>
                <th className="num">Avg score</th>
                <th className="num">Avg time</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.slug}>
                  <td>
                    <Link to={`/interviews/${r.slug}`} className="row-title">
                      {r.title}
                    </Link>
                    <div className="row-sub mono">{r.slug}</div>
                  </td>
                  <td>
                    <StatusPill status={r.status} />
                  </td>
                  <td className="num">{r.participants}</td>
                  <td>
                    <Bar value={r.pass_rate} />
                  </td>
                  <td className="num">{r.avg_score_pct === null ? "—" : `${Math.round(r.avg_score_pct * 100)}%`}</td>
                  <td className="num">{fmtDuration(r.avg_time_spent_seconds)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
