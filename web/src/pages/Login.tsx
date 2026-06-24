import { useState } from "react";
import { api, ApiError } from "../api";
import { ErrorBanner, Mark } from "../ui";

export function Login({ onAuthed }: { onAuthed: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.login(password);
      onAuthed();
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? "That password didn't match." : "Something went wrong.");
      setBusy(false);
    }
  }

  return (
    <div className="gate">
      <form className="card card-pad gate-card rise" onSubmit={submit}>
        <div className="seal"><Mark height={46} color="#1d4b38" /></div>
        <span className="eyebrow">Redwood Research</span>
        <h1>comprehend</h1>
        <p className="sub">Sign in to review interviews and how your people are doing.</p>
        <div className="stack">
          {error && <ErrorBanner message={error} />}
          <div className="field" style={{ textAlign: "left" }}>
            <label htmlFor="pw">Admin password</label>
            <input
              id="pw"
              type="password"
              autoFocus
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <button className="btn btn--accent" type="submit" disabled={busy || !password}>
            {busy ? "Checking…" : "Enter"}
          </button>
        </div>
      </form>
    </div>
  );
}
