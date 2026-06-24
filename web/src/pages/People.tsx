import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Person } from "../api";
import { CopyField, ErrorBanner, Spinner } from "../ui";

export function People() {
  const [people, setPeople] = useState<Person[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [justAdded, setJustAdded] = useState<{ name: string; url: string } | null>(null);

  function load() {
    api.listPeople().then(setPeople).catch((e) => setError(String(e.message)));
  }
  useEffect(load, []);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const p = await api.createPerson(name.trim(), email.trim() || undefined);
      setJustAdded({ name: p.name, url: p.connector_url });
      setName("");
      setEmail("");
      load();
    } catch (e2) {
      setError(String((e2 as Error).message));
    } finally {
      setBusy(false);
    }
  }

  async function toggleActive(p: Person) {
    await api.setPersonActive(p.id, !p.active).catch((e) => setError(String(e.message)));
    load();
  }

  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">Connector links</span>
          <h1>People</h1>
          <p>Each person gets a personal connector link. They add it in Claude.ai; the link is their identity.</p>
        </div>
      </div>

      {error && <ErrorBanner message={error} />}

      <div className="card card-pad" style={{ marginBottom: 24 }}>
        <form className="row" onSubmit={add} style={{ alignItems: "flex-end", gap: 14, flexWrap: "wrap" }}>
          <div className="field" style={{ flex: "1 1 200px" }}>
            <label>Name</label>
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Anna" required />
          </div>
          <div className="field" style={{ flex: "1 1 200px" }}>
            <label>Email <span className="hint">optional</span></label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="anna@…" />
          </div>
          <button className="btn btn--accent" type="submit" disabled={busy || !name.trim()}>
            {busy ? "Adding…" : "Add person"}
          </button>
        </form>

        {justAdded && (
          <div className="stack" style={{ marginTop: 18 }}>
            <div className="note-card">
              Link for <strong>{justAdded.name}</strong> — send it to them to paste into Claude.ai connectors.
            </div>
            <CopyField value={justAdded.url} />
          </div>
        )}
      </div>

      {!people && !error && <Spinner />}
      {people && people.length === 0 && (
        <div className="empty">
          <h3>No people yet</h3>
          <p>Add someone above to generate their connector link.</p>
        </div>
      )}

      {people && people.length > 0 && (
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>Person</th>
                <th>Connector link</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {people.map((p) => (
                <tr key={p.id} style={{ opacity: p.active ? 1 : 0.55 }}>
                  <td>
                    <Link to={`/people/${p.id}`} className="row-title">
                      {p.name}
                    </Link>
                    {p.email && <div className="row-sub">{p.email}</div>}
                  </td>
                  <td style={{ maxWidth: 320 }}>
                    <CopyField value={p.connector_url} />
                  </td>
                  <td>
                    {p.active ? (
                      <span className="pill pass">active</span>
                    ) : (
                      <span className="pill draft">disabled</span>
                    )}
                  </td>
                  <td className="num">
                    <button className="btn btn--ghost btn--sm" onClick={() => toggleActive(p)}>
                      {p.active ? "Disable" : "Enable"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
