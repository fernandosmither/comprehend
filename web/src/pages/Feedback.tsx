import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Feedback as FeedbackItem } from "../api";
import { DateStamp, ErrorBanner, Spinner } from "../ui";

export function Feedback() {
  const [items, setItems] = useState<FeedbackItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  function load() {
    api.listFeedback().then(setItems).catch((e) => setError(String(e.message)));
  }
  useEffect(load, []);

  async function toggle(f: FeedbackItem) {
    await api.setFeedbackReviewed(f.id, !f.reviewed).catch((e) => setError(String(e.message)));
    window.dispatchEvent(new Event("feedback-changed")); // refresh the nav badge
    load();
  }

  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">Pushback</span>
          <h1>Feedback</h1>
          <p>
            Points participants felt strongly enough to forward for review. These never changed
            anyone's grade — they're here for you to weigh on the interview or its rubric.
          </p>
        </div>
      </div>

      {error && <ErrorBanner message={error} />}
      {!items && !error && <Spinner />}

      {items && items.length === 0 && (
        <div className="empty">
          <h3>No feedback yet</h3>
          <p>When a participant pushes back hard and asks to send their point, it lands here.</p>
        </div>
      )}

      {items && items.length > 0 && (
        <div className="stack">
          {items.map((f) => (
            <div className={`card card-pad feedback-item${f.reviewed ? " reviewed" : ""}`} key={f.id}>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start", gap: 14 }}>
                <div className="row" style={{ gap: 9, flexWrap: "wrap" }}>
                  <Link to={`/people/${f.person_id}`} className="row-title">
                    {f.person_name}
                  </Link>
                  <span className="faint">on</span>
                  <Link to={`/interviews/${f.interview_slug}`}>{f.interview_title}</Link>
                </div>
                <div className="row" style={{ gap: 14 }}>
                  <span className="faint mono" style={{ fontSize: "0.8rem" }}>
                    <DateStamp iso={f.created_at} />
                  </span>
                  <button className="btn btn--ghost btn--sm" onClick={() => toggle(f)}>
                    {f.reviewed ? "Reviewed ✓" : "Mark reviewed"}
                  </button>
                </div>
              </div>
              <p style={{ margin: "12px 0 0", whiteSpace: "pre-wrap" }}>{f.body}</p>
              {f.context && (
                <div className="note-card" style={{ marginTop: 12 }}>
                  <span className="eyebrow">About</span>
                  <div style={{ marginTop: 5 }}>{f.context}</div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
