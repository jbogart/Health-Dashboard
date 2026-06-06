/**
 * health-worker.js
 * Cloudflare Worker — stores and serves Apple Health metrics via KV.
 *
 * GET  /health         → returns latest metrics JSON (open)
 * GET  /health/history → returns last 90 days of daily snapshots (open)
 * POST /health         → stores new metrics snapshot (requires X-API-Key header)
 */

const WRITE_KEY = "a62ba4d439f7eed590834c2cfca7dedd6f80dc35d94e4935d5b1e78e00a1ee3b";
const KV_LATEST  = "health_latest";
const KV_HISTORY = "health_history";
const MAX_HISTORY_DAYS = 90;

const cors = {
  "Access-Control-Allow-Origin":  "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, X-API-Key",
  "Content-Type": "application/json",
};

export default {
  async fetch(request, env) {
    const url  = new URL(request.url);
    const path = url.pathname;

    // CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: cors });
    }

    // ── GET /health ───────────────────────────────────────────────────────────
    if (request.method === "GET" && path === "/health") {
      const data = await env.HEALTH_DATA.get(KV_LATEST);
      return new Response(data || JSON.stringify({ error: "No data yet" }), {
        headers: cors,
      });
    }

    // ── GET /health/history ───────────────────────────────────────────────────
    if (request.method === "GET" && path === "/health/history") {
      const data = await env.HEALTH_DATA.get(KV_HISTORY);
      return new Response(data || "[]", { headers: cors });
    }

    // ── POST /health ──────────────────────────────────────────────────────────
    if (request.method === "POST" && path === "/health") {
      // Auth check
      const key = request.headers.get("X-API-Key");
      if (key !== WRITE_KEY) {
        return new Response(JSON.stringify({ error: "Unauthorized" }), {
          status: 401, headers: cors,
        });
      }

      let body;
      try {
        body = await request.json();
      } catch {
        return new Response(JSON.stringify({ error: "Invalid JSON" }), {
          status: 400, headers: cors,
        });
      }

      // Add server timestamp
      const snapshot = {
        ...body,
        recorded_at: new Date().toISOString(),
        date: new Date().toISOString().slice(0, 10),
      };

      // Save as latest
      await env.HEALTH_DATA.put(KV_LATEST, JSON.stringify(snapshot));

      // Append to history (keep last 90 days)
      const historyRaw = await env.HEALTH_DATA.get(KV_HISTORY);
      let history = historyRaw ? JSON.parse(historyRaw) : [];

      // Remove existing entry for today if present
      const today = snapshot.date;
      history = history.filter(h => h.date !== today);
      history.push(snapshot);

      // Trim to MAX_HISTORY_DAYS
      if (history.length > MAX_HISTORY_DAYS) {
        history = history.slice(-MAX_HISTORY_DAYS);
      }

      await env.HEALTH_DATA.put(KV_HISTORY, JSON.stringify(history));

      return new Response(JSON.stringify({ ok: true, date: today }), {
        headers: cors,
      });
    }

    return new Response(JSON.stringify({ error: "Not found" }), {
      status: 404, headers: cors,
    });
  },
};
