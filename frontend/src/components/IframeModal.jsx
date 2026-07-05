import React, { useEffect } from "react";

/**
 * Full-screen iframe overlay. Keeps the app running behind it so a
 * wall/kiosk display never navigates away from the dashboard when the
 * user opens an HOA PDF, the HA UI, or any external URL. Esc,
 * backdrop-click, or the big ✕ button all close.
 *
 * Some hosts (HA itself, some PDF servers) set X-Frame-Options: DENY
 * which will show a blank iframe. The "Open in tab" fallback link
 * still lets non-kiosk browsers escape to a real tab; in kiosk mode
 * the user closes the overlay and finds another route. Keep the ✕
 * always reachable — it's the single most important element.
 */
export default function IframeModal({ url, label, onClose, embedHint }) {
  useEffect(() => {
    if (!url) return;
    function onKey(e) { if (e.key === "Escape") onClose(); }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [url, onClose]);

  if (!url) return null;

  return (
    <div className="iframe-modal-backdrop" onClick={onClose}>
      <div className="iframe-modal" onClick={(e) => e.stopPropagation()}>
        <div className="iframe-modal-head">
          <button
            type="button"
            className="iframe-modal-back"
            onClick={onClose}
            title="Back to SolarSage (Esc)"
          >
            ← Back to SolarSage
          </button>
          <div className="iframe-modal-title">{label || url}</div>
          <div className="iframe-modal-actions">
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="iframe-modal-btn"
              title="Open in a new tab (no-op in kiosk mode)"
            >
              Open in tab
            </a>
            <button
              type="button"
              className="iframe-modal-close"
              onClick={onClose}
              title="Close (Esc)"
              aria-label="Close"
            >
              ✕
            </button>
          </div>
        </div>
        {embedHint && (
          <div className="iframe-modal-hint">{embedHint}</div>
        )}
        <iframe
          className="iframe-modal-frame"
          src={url}
          title={label || "external content"}
        />
      </div>
    </div>
  );
}
