import React, { useEffect, useState } from "react";
import { api, setToken } from "../api.js";

const IS_NATIVE = typeof window !== "undefined"
  && window.Capacitor
  && window.Capacitor.isNativePlatform
  && window.Capacitor.isNativePlatform();

export default function Login({ onLoggedIn }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [status, setStatus] = useState(null);

  useEffect(() => {
    api.authStatus().then(setStatus).catch(() => {});
  }, []);

  async function submit(e) {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      const r = await api.login(username, password, remember);
      setToken(r.token);
      onLoggedIn(r);
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-screen">
      <form className="login-card" onSubmit={submit}>
        <div className="login-brand">
          <img src="/solarsage.png" alt="SolarSage" className="login-logo" />
          <div>
            <h2 style={{ margin: 0 }}>SolarSage</h2>
            <div className="muted" style={{ fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>
              Monitor · Predict · Optimize
            </div>
          </div>
        </div>
        <div className="sub" style={{ marginTop: 12 }}>
          Sign in with your{" "}
          <a href="https://monitor.eg4electronics.com" target="_blank" rel="noreferrer">
            monitor.eg4electronics.com
          </a>{" "}
          credentials.
        </div>
        {status?.credentials_persisted && (
          <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
            Saved credentials are on file — {IS_NATIVE ? "the app" : "the backend"}{" "}
            will auto-login on restart. Re-enter to overwrite, or sign out with
            "forget" to clear.
          </div>
        )}
        {err && <div className="error">{err}</div>}
        <div className="field">
          <label htmlFor="u">Username</label>
          <input
            id="u"
            autoFocus
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="p">Password</label>
          <input
            id="p"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        <label
          style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, marginBottom: 14 }}
        >
          <input
            type="checkbox"
            checked={remember}
            onChange={(e) => setRemember(e.target.checked)}
          />
          Remember me — sign in automatically next time
        </label>
        <button className="primary" type="submit" disabled={busy} style={{ width: "100%" }}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <div className="muted" style={{ fontSize: 11, marginTop: 10, lineHeight: 1.5 }}>
          {IS_NATIVE
            ? "Credentials are stored in the device Keychain. They never leave the app — sign in talks directly to monitor.eg4electronics.com."
            : "Saved credentials live in backend/credentials.json on this machine, mode 0600. Local-only app — don't expose port 8000 publicly."}
        </div>
      </form>
    </div>
  );
}
