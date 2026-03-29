const BASE = "/api";

export async function fetchStatus() {
  const res = await fetch(`${BASE}/status`);
  if (!res.ok) throw new Error("Failed to fetch status");
  return res.json();
}

export async function fetchPredictions() {
  const res = await fetch(`${BASE}/predictions`);
  if (!res.ok) throw new Error("Failed to fetch predictions");
  return res.json();
}
