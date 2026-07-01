import React, { useEffect, useState } from "react";
import Login from "./components/Login.jsx";
import Dashboard from "./components/Dashboard.jsx";
import MobileApp from "./components/MobileApp.jsx";
import { api, getToken, setToken } from "./api.js";

const MOBILE_KEY = "eg4.mobile";

function resolveInitialMobile() {
  if (typeof window === "undefined") return false;
  const params = new URLSearchParams(window.location.search);
  const q = params.get("view");
  if (q === "mobile") return true;
  if (q === "desktop") return false;
  const stored = localStorage.getItem(MOBILE_KEY);
  if (stored === "1") return true;
  if (stored === "0") return false;
  // Auto: touch-capable narrow viewport
  const narrow = window.matchMedia("(max-width: 768px)").matches;
  const touch = navigator.maxTouchPoints > 0;
  return narrow && touch;
}

export default function App() {
  const [session, setSession] = useState(null);
  const [bootChecked, setBootChecked] = useState(false);
  const [mobile, setMobile] = useState(() => resolveInitialMobile());

  const switchToMobile = () => {
    setMobile(true);
    localStorage.setItem(MOBILE_KEY, "1");
  };
  const switchToDesktop = () => {
    setMobile(false);
    localStorage.setItem(MOBILE_KEY, "0");
  };

  useEffect(() => {
    async function check() {
      const t = getToken();
      if (t) {
        try {
          const r = await api.inverters();
          setSession({
            username: r.username || "—",
            inverter_count: r.inverters.length,
          });
          setBootChecked(true);
          return;
        } catch {
          setToken(null);
        }
      }
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
  if (mobile) {
    return (
      <MobileApp
        session={session}
        onLoggedOut={() => setSession(null)}
        onExitMobile={switchToDesktop}
      />
    );
  }
  return (
    <Dashboard
      session={session}
      onLoggedOut={() => setSession(null)}
      onSwitchMobile={switchToMobile}
    />
  );
}
