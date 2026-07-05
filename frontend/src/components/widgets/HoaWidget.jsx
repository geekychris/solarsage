import React, { useState } from "react";
import IframeModal from "../IframeModal.jsx";

function PdfLink({ link, label, onOpen }) {
  if (!link) return null;
  return (
    <div style={{ marginBottom: 6 }}>
      <a
        href={link.url}
        className="hoa-pdf"
        onClick={(e) => {
          e.preventDefault();
          onOpen(link);
        }}
      >
        {label}: {link.label}
      </a>
    </div>
  );
}

export default function HoaWidget({ data }) {
  const [openPdf, setOpenPdf] = useState(null);
  if (!data) return <div className="muted">No HOA data yet.</div>;
  const { monthly_pdf, weekly_pdf, all_pdfs, announcements, url } = data;
  return (
    <div className="hoa">
      <PdfLink link={monthly_pdf} label="This month" onOpen={setOpenPdf} />
      <PdfLink link={weekly_pdf} label="This week" onOpen={setOpenPdf} />

      {announcements && announcements.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>
            Announcements
          </div>
          <ul style={{ margin: 0, paddingLeft: 16 }}>
            {announcements.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </div>
      )}

      {all_pdfs && all_pdfs.length > 0 && (
        <details style={{ marginTop: 10 }}>
          <summary className="muted">All PDFs ({all_pdfs.length})</summary>
          <ul style={{ marginTop: 6 }}>
            {all_pdfs.map((p, i) => (
              <li key={i}>
                <a
                  href={p.url}
                  onClick={(e) => {
                    e.preventDefault();
                    setOpenPdf(p);
                  }}
                >
                  {p.label}
                </a>
              </li>
            ))}
          </ul>
        </details>
      )}

      <div className="muted" style={{ fontSize: 11, marginTop: 10 }}>
        Source:{" "}
        <a href={url} target="_blank" rel="noreferrer">
          eldoradoranchhoa.com.mx
        </a>
      </div>

      {openPdf && (
        <IframeModal
          url={openPdf.url}
          label={openPdf.label}
          onClose={() => setOpenPdf(null)}
        />
      )}
    </div>
  );
}
