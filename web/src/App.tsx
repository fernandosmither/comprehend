import { useEffect, useState } from "react";
import { Link, NavLink, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api } from "./api";
import { Mark } from "./ui";
import { Login } from "./pages/Login";
import { Interviews } from "./pages/Interviews";
import { InterviewEdit } from "./pages/InterviewEdit";
import { InterviewResults } from "./pages/InterviewResults";
import { People } from "./pages/People";
import { PersonDetail } from "./pages/PersonDetail";
import { Feedback } from "./pages/Feedback";

type Auth = boolean | null; // null = still checking

export function App() {
  const [authed, setAuthed] = useState<Auth>(null);

  useEffect(() => {
    api.me().then((r) => setAuthed(r.authenticated)).catch(() => setAuthed(false));
  }, []);

  if (authed === null) return null; // brief flash-free check

  return (
    <Routes>
      <Route
        path="/login"
        element={authed ? <Navigate to="/" replace /> : <Login onAuthed={() => setAuthed(true)} />}
      />
      <Route element={authed ? <Layout onLogout={() => setAuthed(false)} /> : <Navigate to="/login" replace />}>
        <Route index element={<Interviews />} />
        <Route path="interviews/new" element={<InterviewEdit key="new" />} />
        <Route path="interviews/:slug" element={<InterviewResults />} />
        <Route path="interviews/:slug/edit" element={<InterviewEdit />} />
        <Route path="people" element={<People />} />
        <Route path="people/:id" element={<PersonDetail />} />
        <Route path="feedback" element={<Feedback />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function Layout({ onLogout }: { onLogout: () => void }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    const refresh = () => api.feedbackCount().then(setUnread).catch(() => {});
    refresh();
    window.addEventListener("feedback-changed", refresh);
    return () => window.removeEventListener("feedback-changed", refresh);
  }, [location.pathname]);

  return (
    <div className="shell">
      <header className="masthead">
        <div className="masthead-inner">
          <Link to="/" className="wordmark" aria-label="comprehend home">
            <Mark height={21} color="#1d4b38" />
            <span className="wordmark-text">comprehend</span>
          </Link>
          <nav>
            <NavLink to="/" end className={({ isActive }) => `navlink ${isActive ? "active" : ""}`}>
              Interviews
            </NavLink>
            <NavLink to="/people" className={({ isActive }) => `navlink ${isActive ? "active" : ""}`}>
              People
            </NavLink>
            <NavLink to="/feedback" className={({ isActive }) => `navlink ${isActive ? "active" : ""}`}>
              Feedback
              {unread > 0 && <span className="nav-badge">{unread}</span>}
            </NavLink>
          </nav>
          <div className="spacer" />
          <button
            className="btn btn--ghost btn--sm"
            onClick={async () => {
              await api.logout().catch(() => {});
              onLogout();
              navigate("/login");
            }}
          >
            Sign out
          </button>
        </div>
      </header>
      <main className="rise">
        <Outlet />
      </main>
    </div>
  );
}
