import React, { useEffect, useState } from "react";
import Login from "./components/Login.jsx";
import Dashboard from "./components/Dashboard.jsx";
import { api, getToken, setToken } from "./api.js";

export default function App() {
  const [session, setSession] = useState(null);
  const [bootChecked, setBootChecked] = useState(false);

  useEffect(() => {
    async function check() {
      const t = getToken();
      // 1. Try existing token first
      if (t) {
        try {
          const r = await api.inverters();
          setSession({ username: "you", inverter_count: r.inverters.length });
          setBootChecked(true);
          return;
        } catch {
          setToken(null);
        }
      }
      // 2. Fall back to the auto-login session if creds are persisted
      try {
        const status = await api.authStatus();
        if (status.credentials_persisted && status.active_sessions > 0) {
          const claimed = await api.useSaved();
          setToken(claimed.token);
          setSession({
            username: claimed.username,
            inverter_count: claimed.inverter_count,
          });
        }
      } catch {
        /* no saved session — show login */
      } finally {
        setBootChecked(true);
      }
    }
    check();
  }, []);

  if (!bootChecked) return null;
  if (!session) {
    return <Login onLoggedIn={(s) => setSession(s)} />;
  }
  return <Dashboard session={session} onLoggedOut={() => setSession(null)} />;
}
