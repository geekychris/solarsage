import React, { useEffect } from "react";

/**
 * Full-screen PDF viewer overlay. Keeps the app running behind it so a
 * wall/kiosk display never navigates away from the dashboard when a
 * user opens an HOA PDF or similar. Esc, backdrop-click, or the ✕
 * button all close.
 *
 * The <iframe> uses the browser's native PDF viewer. Some hosts set
 * X-Frame-Options: DENY on their PDFs; the fallback "Open in a new
 * tab" link lets the user escape to a real tab if that ever bites.
 */
export default function PdfModal({ url, label, onClose }) {
  useEffect(() => {
    if (!url) return;
    function onKey(e) { if (e.key === "Escape") onClose(); }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [url, onClose]);

  if (!url) return null;

  return (
    <div className="pdf-modal-backdrop" onClick={onClose}>
      <div className="pdf-modal" onClick={(e) => e.stopPropagation()}>
        <div className="pdf-modal-head">
          <div className="pdf-modal-title">{label || "PDF"}</div>
          <div className="pdf-modal-actions">
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="pdf-modal-btn"
              title="Open in a new tab (falls back if the embed refuses to load)"
            >
              Open in tab
            </a>
            <button
              type="button"
              className="pdf-modal-close"
              onClick={onClose}
              title="Close (Esc)"
              aria-label="Close"
            >
              ✕
            </button>
          </div>
        </div>
        <iframe
          className="pdf-modal-frame"
          src={url}
          title={label || "PDF"}
        />
      </div>
    </div>
  );
}
