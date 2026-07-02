import React, { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

// Leaflet's default marker icons ship as relative paths that don't
// survive Vite's bundling. Use the CDN copy so the marker renders.
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl:       "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl:     "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/images/marker-shadow.png",
});

/**
 * Interactive lat/lon picker. Renders a Leaflet map centered on the
 * given coords, with a draggable marker. Any drag or click updates
 * the parent via `onChange({lat, lon})`.
 */
export default function LocationPicker({ lat, lon, onChange, height = 260 }) {
  const nodeRef = useRef(null);
  const mapRef  = useRef(null);
  const markerRef = useRef(null);

  useEffect(() => {
    if (!nodeRef.current || mapRef.current) return;
    const map = L.map(nodeRef.current).setView([lat || 31.025, lon || -114.838], 8);
    L.tileLayer(
      "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      {
        maxZoom: 18,
        attribution: "© OpenStreetMap contributors",
      }
    ).addTo(map);
    const marker = L.marker([lat || 31.025, lon || -114.838], { draggable: true }).addTo(map);
    marker.on("dragend", (e) => {
      const { lat, lng } = e.target.getLatLng();
      onChange({ lat: +lat.toFixed(5), lon: +lng.toFixed(5) });
    });
    map.on("click", (e) => {
      marker.setLatLng(e.latlng);
      onChange({ lat: +e.latlng.lat.toFixed(5), lon: +e.latlng.lng.toFixed(5) });
    });
    mapRef.current = map;
    markerRef.current = marker;
    return () => {
      map.remove();
      mapRef.current = null;
      markerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Sync marker when parent updates externally (typed into input)
  useEffect(() => {
    if (!markerRef.current || !mapRef.current) return;
    const cur = markerRef.current.getLatLng();
    const nextLat = Number(lat);
    const nextLon = Number(lon);
    if (Number.isFinite(nextLat) && Number.isFinite(nextLon) &&
        (Math.abs(cur.lat - nextLat) > 1e-5 || Math.abs(cur.lng - nextLon) > 1e-5)) {
      markerRef.current.setLatLng([nextLat, nextLon]);
      mapRef.current.setView([nextLat, nextLon]);
    }
  }, [lat, lon]);

  return (
    <div
      ref={nodeRef}
      className="location-picker"
      style={{ height, borderRadius: 6, overflow: "hidden" }}
    />
  );
}
