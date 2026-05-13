// Default appliance catalog seeded into a fresh site (native build).
// Mirrors backend/app/appliances_catalog.py — keep the two in sync.

export const DEFAULT_APPLIANCES = [
  { name: "Water pump (house)",       watts: 900,  typical_minutes: 15,  can_defer: 1 },
  { name: "Clothes washer",           watts: 500,  typical_minutes: 50,  can_defer: 1, preferred_start_hour: 10, preferred_end_hour: 16 },
  { name: "Dishwasher",               watts: 1500, typical_minutes: 90,  can_defer: 1, preferred_start_hour: 11, preferred_end_hour: 15 },
  { name: "Air conditioning (boost)", watts: 2200, typical_minutes: 120, can_defer: 1, preferred_start_hour: 11, preferred_end_hour: 15 },
  { name: "Computer workstation",     watts: 350,  typical_minutes: 480, can_defer: 0 },
  { name: "Water heater (heat-up)",   watts: 4500, typical_minutes: 60,  can_defer: 1, preferred_start_hour: 10, preferred_end_hour: 15 },
  { name: "EV charger (Level 2)",     watts: 7200, typical_minutes: 180, can_defer: 1, preferred_start_hour: 10, preferred_end_hour: 16 },
  { name: "Pool pump",                watts: 1100, typical_minutes: 240, can_defer: 1, preferred_start_hour: 10, preferred_end_hour: 16, enabled: 0 },
  { name: "Clothes dryer (electric)", watts: 3000, typical_minutes: 45,  can_defer: 1, enabled: 0 },
];

export function seedForSite(siteId) {
  return DEFAULT_APPLIANCES.map((a) => ({ ...a, site_id: siteId, enabled: a.enabled ?? 1 }));
}
