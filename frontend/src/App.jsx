import React, { useEffect, useState } from "react";
import Login from "./components/Login.jsx";
import Dashboard from "./components/Dashboard.jsx";
import MobileApp from "./components/MobileApp.jsx";
import RotationMode from "./components/RotationMode.jsx";
import { api, getToken, setToken } from "./api.js";

const MOBILE_KEY = "eg4.mobile";
const THEME_KEY = "eg4.theme";

function applyTheme(theme) {
  if (typeof document === "undefined") return;
  if (theme === "light") document.documentElement.setAttribute("data-theme", "light");
  else document.documentElement.removeAttribute("data-theme");
}

function urlViewParam() {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("view");
}

function resolveInitialMobile() {
  if (typeof window === "undefined") return false;
  const q = urlViewParam();
  if (q === "mobile") return true;
  if (q === "desktop" || q === "rotation") return false;
  const stored = localStorage.getItem(MOBILE_KEY);
  if (stored === "1") return true;
  if (stored === "0") return false;
  const narrow = window.matchMedia("(max-width: 768px)").matches;
  const touch = navigator.maxTouchPoints > 0;
  return narrow && touch;
}

export default function App() {
  const [session, setSession] = useState(null);
  const [bootChecked, setBootChecked] = useState(false);
  const [mobile, setMobile] = useState(() => resolveInitialMobile());
  const [rotation, setRotation] = useState(() => urlViewParam() === "rotation");
  const [theme, setThemeState] = useState(() =>
    (typeof localStorage !== "undefined" && localStorage.getItem(THEME_KEY)) || "dark"
  );

  useEffect(() => { applyTheme(theme); }, [theme]);

  const toggleTheme = () => {
    const next = theme === "light" ? "dark" : "light";
    setThemeState(next);
    localStorage.setItem(THEME_KEY, next);
  };
  const switchToMobile = () => {
    setMobile(true);
    localStorage.setItem(MOBILE_KEY, "1");
  };
  const switchToDesktop = () => {
    setMobile(false);
    localStorage.setItem(MOBILE_KEY, "0");
  };
  const enterRotation = () => setRotation(true);
  const exitRotation = () => {
    setRotation(false);
    if (typeof window !== "undefined" && urlViewParam() === "rotation") {
      const url = new URL(window.location.href);
      url.searchParams.delete("view");
      window.history.replaceState({}, "", url.toString());
    }
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
  if (rotation) {
    return <RotationMode onExit={exitRotation} />;
  }
  if (mobile) {
    return (
      <MobileApp
        session={session}
        onLoggedOut={() => setSession(null)}
        onExitMobile={switchToDesktop}
        onEnterRotation={enterRotation}
        theme={theme}
        onToggleTheme={toggleTheme}
      />
    );
  }
  return (
    <Dashboard
      session={session}
      onLoggedOut={() => setSession(null)}
      onSwitchMobile={switchToMobile}
      onEnterRotation={enterRotation}
      theme={theme}
      onToggleTheme={toggleTheme}
    />
  );
}
