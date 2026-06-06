"""
generate_dashboard.py
Fetches latest Strava data, merges with static Apple Health baselines,
and writes a fresh index.html to the repo root.
"""

import os, json, requests
from datetime import datetime, timezone, timedelta, date
from collections import defaultdict

# ── Strava OAuth ───────────────────────────────────────────────────────────────

def get_access_token():
    resp = requests.post("https://www.strava.com/oauth/token", data={
        "client_id":     os.environ["STRAVA_CLIENT_ID"],
        "client_secret": os.environ["STRAVA_CLIENT_SECRET"],
        "refresh_token": os.environ["STRAVA_REFRESH_TOKEN"],
        "grant_type":    "refresh_token",
    })
    resp.raise_for_status()
    return resp.json()["access_token"]


def get_athlete_zones(token):
    r = requests.get("https://www.strava.com/api/v3/athlete/zones",
                     headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.json()


def get_activities(token, months=3):
    after = int((datetime.now(timezone.utc) - timedelta(days=months * 30)).timestamp())
    activities, page = [], 1
    while True:
        r = requests.get("https://www.strava.com/api/v3/athlete/activities",
                         headers={"Authorization": f"Bearer {token}"},
                         params={"after": after, "per_page": 100, "page": page})
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        activities.extend(batch)
        page += 1
    return activities


# ── Helpers ────────────────────────────────────────────────────────────────────

def fmt_date(iso):
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%b %-d")
    except Exception:
        return iso[:10]

def fmt_min(sec):
    if not sec:
        return "—"
    h, m = divmod(int(sec) // 60, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"

def fmt_pace(speed_ms, sport):
    """Convert m/s to readable pace/speed."""
    if not speed_ms or speed_ms == 0:
        return "—"
    if sport in ("Ride", "GravelRide", "VirtualRide"):
        return f"{speed_ms * 3.6:.1f} km/h"
    if sport in ("Run",):
        pace = 1000 / (speed_ms * 60)
        m, s = divmod(int(pace * 60), 60)
        return f"{m}:{s:02d} /km"
    return "—"

def sport_icon(t):
    icons = {
        "Ride": "🚲", "VirtualRide": "🚲", "GravelRide": "🚲",
        "Run": "🏃", "Walk": "🚶", "Hike": "🥾",
        "Pickleball": "🏓", "Tennis": "🎾", "Swim": "🏊",
        "WeightTraining": "🏋️", "Workout": "💪", "Elliptical": "〰️",
        "Yoga": "🧘", "Soccer": "⚽",
    }
    return icons.get(t, "⚡")

def sport_label(t):
    labels = {
        "GravelRide": "Gravel Ride", "VirtualRide": "Virtual Ride",
        "WeightTraining": "Weight Training",
    }
    return labels.get(t, t)

def activity_color(sport):
    colors = {
        "Ride": "#378ADD", "GravelRide": "#378ADD", "VirtualRide": "#378ADD",
        "Run": "#E24B4A", "Walk": "#EF9F27", "Hike": "#1D9E75",
        "Pickleball": "#7F77DD",
    }
    return colors.get(sport, "#aaa")


# ── Weekly planner logic ───────────────────────────────────────────────────────

def build_week_plan(activities):
    """
    Generate a smart weekly fitness plan based on:
    - What has already been done this week
    - Recent training load vs 8-week baseline
    - VO2 max goal (target 42+)
    - Sport mix and recovery needs
    """
    now = datetime.now(timezone.utc)
    today = now.date()

    # Week boundaries (Mon–Sun)
    week_start = today - timedelta(days=today.weekday())  # Monday
    week_end   = week_start + timedelta(days=6)           # Sunday

    # Activities done this week already
    this_week = [
        a for a in activities
        if a.get("start_date_local", a.get("start_date",""))[:10] >= week_start.isoformat()
    ]

    done_sports = [a.get("sport_type", a.get("type","")) for a in this_week]
    done_re     = sum(int(a.get("suffer_score") or 0) for a in this_week)
    done_cal    = sum(int(a.get("calories") or 0) for a in this_week)
    done_days   = set(a.get("start_date_local", a.get("start_date",""))[:10] for a in this_week)

    # 8-week avg weekly RE for baseline
    eight_weeks_ago = today - timedelta(weeks=8)
    recent_acts = [a for a in activities
                   if a.get("start_date_local", a.get("start_date",""))[:10] >= eight_weeks_ago.isoformat()]
    avg_weekly_re = sum(int(a.get("suffer_score") or 0) for a in recent_acts) / 8

    # Days of the week remaining (not including today if already have activities)
    all_days = [week_start + timedelta(days=i) for i in range(7)]
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    has_cycling   = any(s in ("Ride","GravelRide","VirtualRide") for s in done_sports)
    has_pickleball = any(s == "Pickleball" for s in done_sports)
    has_strength   = any(s in ("WeightTraining","Workout") for s in done_sports)
    has_run        = any(s in ("Run",) for s in done_sports)

    # Build plan for each remaining day
    plan = []
    for i, d in enumerate(all_days):
        day_iso = d.isoformat()
        day_name = day_names[i]
        is_today = d == today
        is_past  = d < today
        is_done  = day_iso in done_days

        if is_past and not is_done:
            plan.append({
                "day": day_name, "date": d.strftime("%-d %b"),
                "status": "missed", "title": "Rest / unlogged",
                "desc": "No activity logged.", "icon": "—",
                "badge": "", "badge_color": "",
            })
            continue

        if is_done:
            acts = [a for a in this_week
                    if a.get("start_date_local", a.get("start_date",""))[:10] == day_iso]
            names = ", ".join(a.get("name","Activity") for a in acts)
            cals  = sum(int(a.get("calories") or 0) for a in acts)
            re    = sum(int(a.get("suffer_score") or 0) for a in acts)
            plan.append({
                "day": day_name, "date": d.strftime("%-d %b"),
                "status": "done", "title": names,
                "desc": f"{cals} kcal · RE {re}",
                "icon": sport_icon(acts[0].get("sport_type","") if acts else ""),
                "badge": "✓ Done", "badge_color": "#3b6d11",
            })
            continue

        # Future days — assign workouts intelligently
        # Priority: VO2 max needs aerobic work; missing strength; pickleball is anchor
        weekday = d.weekday()  # 0=Mon

        if weekday == 0:  # Monday
            if not has_strength:
                plan.append({
                    "day": day_name, "date": d.strftime("%-d %b"),
                    "status": "planned", "icon": "🏋️",
                    "title": "Strength training — 30–45 min",
                    "desc": "Bodyweight or gym. Focus on legs + core: squats, lunges, planks, deadlifts. Missing from your log — add 2×/week.",
                    "badge": "Strength", "badge_color": "#854f0b",
                })
            else:
                plan.append({
                    "day": day_name, "date": d.strftime("%-d %b"),
                    "status": "planned", "icon": "🚶",
                    "title": "Active recovery — 20–30 min walk",
                    "desc": "Easy pace, HR under 120 bpm. Flush the legs after the weekend.",
                    "badge": "Recovery", "badge_color": "#185fa5",
                })
        elif weekday == 1:  # Tuesday
            plan.append({
                "day": day_name, "date": d.strftime("%-d %b"),
                "status": "planned", "icon": "🚲",
                "title": "Zone 2 ride — 45–60 min",
                "desc": "Keep HR 121–150 bpm, power 97–131 W. This is your primary VO₂ max builder. Target 2× per week to get back above 42.",
                "badge": "Z2 Aerobic", "badge_color": "#185fa5",
            })
        elif weekday == 2:  # Wednesday
            plan.append({
                "day": day_name, "date": d.strftime("%-d %b"),
                "status": "planned", "icon": "🏓",
                "title": "Pickleball — evening session",
                "desc": "Your most consistent sport. Aim for 90+ min. Good cardio and agility work. Counts toward weekly active calorie goal.",
                "badge": "Cardio", "badge_color": "#7F77DD",
            })
        elif weekday == 3:  # Thursday
            plan.append({
                "day": day_name, "date": d.strftime("%-d %b"),
                "status": "planned", "icon": "🏋️",
                "title": "Strength training — 30–45 min",
                "desc": "Upper body + core focus. Push-ups, rows, shoulder press, planks. Pair with a 15-min easy walk afterward.",
                "badge": "Strength", "badge_color": "#854f0b",
            })
        elif weekday == 4:  # Friday
            plan.append({
                "day": day_name, "date": d.strftime("%-d %b"),
                "status": "planned", "icon": "🚶",
                "title": "Rest or easy walk — 20 min",
                "desc": "Active rest before weekend efforts. Keep steps above 8k but no structured workout needed.",
                "badge": "Rest", "badge_color": "#aaa",
            })
        elif weekday == 5:  # Saturday
            plan.append({
                "day": day_name, "date": d.strftime("%-d %b"),
                "status": "planned", "icon": "🚲",
                "title": "Gravel ride — 25–35 km",
                "desc": "Your strongest activity (20+ PRs on recent rides). Push Z3–Z4 on climbs, Z2 on flats. Target 500+ kcal. Great VO₂ stimulus.",
                "badge": "Endurance", "badge_color": "#378ADD",
            })
        else:  # Sunday
            plan.append({
                "day": day_name, "date": d.strftime("%-d %b"),
                "status": "planned", "icon": "🧘",
                "title": "Rest + mobility — 15 min stretching",
                "desc": "Full rest day. Hip flexors, hamstrings, thoracic spine. Helps HRV recovery — consistent rest days push your baseline higher.",
                "badge": "Recovery", "badge_color": "#1D9E75",
            })

    return plan, {
        "done_re": done_re,
        "done_cal": done_cal,
        "done_count": len(this_week),
        "avg_weekly_re": round(avg_weekly_re),
        "week_start": week_start.strftime("%b %-d"),
        "week_end": week_end.strftime("%b %-d"),
    }


# ── Data aggregators ───────────────────────────────────────────────────────────

def monthly_calories(activities):
    by_month = defaultdict(lambda: defaultdict(float))
    for a in activities:
        m = a.get("start_date", "")[:7]
        sport = a.get("sport_type", a.get("type", "Other"))
        cal = a.get("calories") or 0
        bucket = ("Cycling" if sport in ("Ride","GravelRide","VirtualRide")
                  else "Pickleball" if sport == "Pickleball"
                  else "Run/Hike" if sport in ("Run","Walk","Hike")
                  else "Other")
        by_month[m][bucket] += cal
    return by_month


def recent_rows(activities, n=10):
    rows = []
    for a in sorted(activities, key=lambda x: x.get("start_date",""), reverse=True)[:n]:
        sport = a.get("sport_type", a.get("type", "?"))
        dist  = a.get("distance", 0)
        speed = a.get("average_speed") or a.get("avg_speed") or 0
        elev  = a.get("total_elevation_gain") or a.get("elevation_gain") or 0
        rows.append({
            "icon":  sport_icon(sport),
            "color": activity_color(sport),
            "name":  a.get("name", "Activity"),
            "sport": sport_label(sport),
            "date":  fmt_date(a.get("start_date", a.get("start_date_local",""))),
            "time":  fmt_min(a.get("moving_time")),
            "dist":  f"{dist/1000:.1f} km" if dist > 0 else "—",
            "pace":  fmt_pace(speed, sport),
            "elev":  f"{int(elev)}m" if elev > 0 else "—",
            "cal":   int(a.get("calories") or 0),
            "re":    int(a.get("suffer_score") or 0),
            "prs":   int(a.get("pr_count") or 0),
        })
    return rows


def summary_stats(activities):
    total_cal = sum(int(a.get("calories") or 0) for a in activities)
    total_re  = sum(int(a.get("suffer_score") or 0) for a in activities)
    sports    = defaultdict(int)
    for a in activities:
        sports[a.get("sport_type", a.get("type", "Other"))] += 1
    top_sport = max(sports, key=sports.get) if sports else "—"
    return {
        "count":     len(activities),
        "total_cal": total_cal,
        "top_sport": sport_label(top_sport),
        "top_count": sports.get(top_sport, 0),
        "total_re":  total_re,
    }


def hr_zone_rows(zones_data):
    labels = ["Z1 Recovery","Z2 Aerobic","Z3 Tempo","Z4 Threshold","Z5 Max"]
    colors = ["#1D9E75","#378ADD","#EF9F27","#D85A30","#E24B4A"]
    widths = [15, 45, 25, 12, 3]
    rows = []
    for i, z in enumerate(zones_data.get("heart_rate_zones", [])[:5]):
        lo, hi = z.get("min", 0), z.get("max")
        rows.append({
            "label": labels[i] if i < len(labels) else f"Z{i+1}",
            "range": f"{lo}–{hi} bpm" if hi else f"{lo}+ bpm",
            "color": colors[i] if i < len(colors) else "#888",
            "width": widths[i] if i < len(widths) else 10,
        })
    return rows, zones_data.get("functional_threshold_power"), zones_data.get("power_zones", [])


# ── HTML render ────────────────────────────────────────────────────────────────

def render(stats, recent, hr_rows, ftp, pwr_zones, monthly, week_plan, week_meta):
    updated = datetime.now(timezone.utc).strftime("%-d %b %Y · %H:%M UTC")

    # Recent activities HTML
    act_html = ""
    for a in recent:
        pr_badge = f'<span style="font-size:10px;background:#faeeda;color:#854f0b;padding:1px 6px;border-radius:99px;margin-left:4px">🏆 {a["prs"]} PR{"s" if a["prs"]!=1 else ""}</span>' if a["prs"] > 0 else ""
        details = " · ".join(x for x in [a["dist"], a["pace"], a["elev"]] if x != "—")
        act_html += f"""
        <div class="act-row">
          <div class="act-dot" style="background:{a['color']}">{a['icon']}</div>
          <div style="flex:1;min-width:0">
            <div class="act-name">{a['name']}{pr_badge}</div>
            <div class="act-meta">{a['date']} · {a['sport']} · {a['time']}{(' · ' + details) if details else ''}</div>
          </div>
          <div class="act-stat">{a['cal']} kcal<br><span class="dim">RE {a['re']}</span></div>
        </div>"""

    # Weekly planner HTML
    plan_html = ""
    for day in week_plan:
        status = day["status"]
        if status == "done":
            bg = "#f0faf0"; border = "#1D9E75"; badge_bg = "#eaf3de"; badge_fg = "#3b6d11"
        elif status == "missed":
            bg = "#fafafa"; border = "#ddd"; badge_bg = "#f5f5f0"; badge_fg = "#aaa"
        else:
            bg = "#fff"; border = "#e0e0d8"; badge_bg = "#e6f1fb"; badge_fg = "#185fa5"

        badge_html = f'<span style="font-size:10px;padding:2px 8px;border-radius:99px;background:{badge_bg};color:{badge_fg};font-weight:500">{day["badge"]}</span>' if day["badge"] else ""

        plan_html += f"""
        <div style="background:{bg};border:0.5px solid {border};border-radius:10px;padding:.85rem 1rem;margin-bottom:8px;display:flex;gap:12px;align-items:flex-start">
          <div style="min-width:44px;text-align:center">
            <div style="font-size:10px;font-weight:600;color:#aaa;text-transform:uppercase">{day['day']}</div>
            <div style="font-size:12px;color:#666">{day['date']}</div>
            <div style="font-size:22px;margin-top:4px">{day['icon']}</div>
          </div>
          <div style="flex:1">
            <div style="font-size:13px;font-weight:500;color:#1a1a18;margin-bottom:3px">{day['title']}</div>
            <div style="font-size:12px;color:#888;line-height:1.5">{day['desc']}</div>
            <div style="margin-top:6px">{badge_html}</div>
          </div>
        </div>"""

    # HR zone bars
    zone_html = ""
    for z in hr_rows:
        zone_html += f"""
        <div class="zone-wrap">
          <div class="zone-lbl"><span>{z['label']}</span><span>{z['range']}</span></div>
          <div class="zone-track"><div class="zone-fill" style="width:{z['width']}%;background:{z['color']}"></div></div>
        </div>"""

    # Power zones
    pwr_labels = ["Z1 Active rec","Z2 Endurance","Z3 Tempo","Z4 Threshold","Z5 VO₂ max","Z6 Anaerobic","Z7 Neuro"]
    pwr_html = ""
    for i, p in enumerate(pwr_zones[:7]):
        lo, hi = p.get("min", 0), p.get("max")
        rng = f"{lo}–{hi} W" if hi else f"{lo}+ W"
        pwr_html += f'<div class="pbox"><span class="dim">{pwr_labels[i] if i < len(pwr_labels) else f"Z{i+1}"}</span><br><strong>{rng}</strong></div>'

    # Chart data
    all_months  = sorted(monthly.keys())[-12:]
    month_labels = json.dumps([m[5:] + "/" + m[2:4] for m in all_months])
    ride_data   = json.dumps([round(monthly[m].get("Cycling", 0))    for m in all_months])
    pb_data     = json.dumps([round(monthly[m].get("Pickleball", 0)) for m in all_months])
    run_data    = json.dumps([round(monthly[m].get("Run/Hike", 0))   for m in all_months])

    ftp_display = ftp if ftp else "—"
    load_pct    = min(100, round((week_meta['done_re'] / max(week_meta['avg_weekly_re'], 1)) * 100))
    load_color  = "#1D9E75" if load_pct >= 80 else "#EF9F27" if load_pct >= 40 else "#E24B4A"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Health Dashboard · jbogart</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f5f0;color:#1a1a18;padding:1.5rem}}
.dash{{max-width:900px;margin:0 auto}}
.header{{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;margin-bottom:.5rem}}
.title{{font-size:20px;font-weight:500}}
.subtitle{{font-size:12px;color:#888;margin-top:2px}}
.badge{{display:inline-flex;align-items:center;gap:4px;font-size:10px;background:#fff;border:0.5px solid #0f6e56;border-radius:99px;padding:2px 10px;color:#0f6e56;margin-right:4px}}
.sl{{font-size:10px;font-weight:500;letter-spacing:.08em;color:#aaa;text-transform:uppercase;margin:1.5rem 0 .75rem}}
.mg{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px}}
.mc{{background:#ece9e0;border-radius:8px;padding:.9rem 1rem}}
.ml{{font-size:12px;color:#666;margin-bottom:4px}}
.mv{{font-size:22px;font-weight:500}}
.mu{{font-size:13px;font-weight:400;color:#888}}
.ms{{font-size:11px;color:#aaa;margin-top:3px}}
.mt{{display:inline-block;font-size:10px;padding:2px 7px;border-radius:99px;margin-top:5px}}
.tg{{background:#eaf3de;color:#3b6d11}}
.tw{{background:#faeeda;color:#854f0b}}
.ti{{background:#e6f1fb;color:#185fa5}}
.cc{{background:#fff;border:0.5px solid rgba(0,0,0,0.1);border-radius:12px;padding:1rem 1.25rem;margin-bottom:10px}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.rc{{background:#fff;border:0.5px solid rgba(0,0,0,0.1);border-radius:12px;padding:1rem 1.25rem}}
.rr{{display:flex;align-items:flex-start;gap:10px;padding:8px 0;border-bottom:0.5px solid rgba(0,0,0,0.08)}}
.rr:last-child{{border-bottom:none;padding-bottom:0}}
.ri{{font-size:16px;color:#185fa5;margin-top:1px;flex-shrink:0;width:22px}}
.rt{{font-size:13px;line-height:1.5;font-weight:500}}
.rsub{{font-size:11px;color:#aaa;margin-top:2px;font-weight:400}}
.act-row{{display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:0.5px solid rgba(0,0,0,0.07);font-size:13px}}
.act-row:last-child{{border-bottom:none}}
.act-dot{{width:34px;height:34px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0;opacity:0.85}}
.act-name{{font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.act-meta{{font-size:11px;color:#aaa;margin-top:2px}}
.act-stat{{margin-left:auto;text-align:right;font-size:12px;color:#666;flex-shrink:0}}
.dim{{color:#aaa}}
.zone-wrap{{margin-bottom:8px}}
.zone-lbl{{display:flex;justify-content:space-between;font-size:11px;color:#666;margin-bottom:3px}}
.zone-track{{background:#ece9e0;border-radius:99px;height:8px;overflow:hidden}}
.zone-fill{{height:100%;border-radius:99px}}
.pbox{{padding:5px 7px;background:#f5f5f0;border-radius:6px;font-size:11px}}
.pwr-grid{{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-top:8px}}
.stat-row{{display:flex;gap:20px;margin-top:8px;font-size:12px;color:#888;flex-wrap:wrap}}
.stat-row strong{{color:#1a1a18}}
.blood-grid{{display:grid;grid-template-columns:1fr 1fr;gap:0 1.5rem}}
.brow{{display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:0.5px solid rgba(0,0,0,0.08);font-size:13px}}
.brow:last-child{{border-bottom:none}}
.bval-good{{font-weight:500;color:#3b6d11}}
.bval-warn{{font-weight:500;color:#854f0b}}
.leg{{display:flex;flex-wrap:wrap;gap:12px;margin-top:10px;font-size:11px;color:#666}}
.leg span{{display:flex;align-items:center;gap:4px}}
.leg-dot{{width:10px;height:10px;border-radius:2px}}
.load-bar-track{{background:#ece9e0;border-radius:99px;height:10px;overflow:hidden;margin:8px 0 4px}}
.load-bar-fill{{height:100%;border-radius:99px;transition:width .3s}}
footer{{margin-top:2rem;font-size:11px;color:#bbb;text-align:center;line-height:1.8}}
@media(max-width:600px){{.two{{grid-template-columns:1fr}}.blood-grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<div class="dash">

  <div class="header">
    <div>
      <div class="title">Health Dashboard</div>
      <div class="subtitle">Last updated {updated}</div>
    </div>
  </div>
  <div style="margin:.5rem 0 1.25rem">
    <span class="badge">● Strava (live)</span>
    <span class="badge">● Apple Health</span>
  </div>

  <div class="sl">Activity summary — last 90 days</div>
  <div class="mg">
    <div class="mc"><div class="ml">Activities</div><div class="mv">{stats['count']}</div><div class="ms">last 90 days</div><span class="mt ti">All sports</span></div>
    <div class="mc"><div class="ml">Calories burned</div><div class="mv">{stats['total_cal']:,} <span class="mu">kcal</span></div><div class="ms">active calories</div><span class="mt ti">Strava</span></div>
    <div class="mc"><div class="ml">Top sport</div><div class="mv" style="font-size:16px">{stats['top_sport']}</div><div class="ms">{stats['top_count']} sessions</div><span class="mt tg">Most frequent</span></div>
    <div class="mc"><div class="ml">Training load</div><div class="mv">{stats['total_re']}</div><div class="ms">total relative effort</div><span class="mt ti">Strava</span></div>
    <div class="mc"><div class="ml">Resting HR</div><div class="mv">57 <span class="mu">bpm</span></div><div class="ms">30-day avg · Apple Watch</div><span class="mt tg">Excellent</span></div>
    <div class="mc"><div class="ml">VO₂ max</div><div class="mv">38.6 <span class="mu">ml/kg</span></div><div class="ms">Apple Watch · Jun 3</div><span class="mt tw">Fair — target 42+</span></div>
  </div>

  <!-- WEEKLY PLANNER -->
  <div class="sl">This week's fitness plan — {week_meta['week_start']} to {week_meta['week_end']}</div>
  <div class="cc" style="padding:1rem 1.25rem 1rem">

    <!-- Weekly load progress -->
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.5rem">
      <div style="font-size:12px;color:#666">Weekly training load</div>
      <div style="font-size:12px;color:#666"><strong style="color:#1a1a18">{week_meta['done_re']}</strong> / ~{week_meta['avg_weekly_re']} RE avg &nbsp;·&nbsp; {week_meta['done_count']} activities &nbsp;·&nbsp; {week_meta['done_cal']:,} kcal</div>
    </div>
    <div class="load-bar-track">
      <div class="load-bar-fill" style="width:{load_pct}%;background:{load_color}"></div>
    </div>
    <div style="font-size:10px;color:#aaa;margin-bottom:1rem">{load_pct}% of your typical weekly load</div>

    {plan_html}
  </div>

  <!-- RECENT ACTIVITIES -->
  <div class="sl">Recent activities — last 10</div>
  <div class="cc" style="padding:.75rem 1.25rem">
    {act_html}
  </div>

  <div class="sl">Monthly calorie volume — last 12 months</div>
  <div class="cc">
    <div style="position:relative;width:100%;height:200px"><canvas id="volChart"></canvas></div>
    <div class="leg">
      <span><span class="leg-dot" style="background:#378ADD"></span>Cycling / Gravel</span>
      <span><span class="leg-dot" style="background:#E24B4A"></span>Pickleball</span>
      <span><span class="leg-dot" style="background:#1D9E75"></span>Run / Hike</span>
    </div>
  </div>

  <div class="two">
    <div>
      <div class="sl">Heart rate zones</div>
      <div class="cc" style="margin-bottom:0">
        {zone_html}
        <div style="font-size:11px;color:#aaa;margin-top:8px">Max HR source · Connect HR monitor for time-in-zone</div>
      </div>
    </div>
    <div>
      <div class="sl">Cycling power — FTP</div>
      <div class="cc" style="margin-bottom:0;text-align:center">
        <div style="font-size:42px;font-weight:500;padding:.5rem 0">{ftp_display} <span style="font-size:18px;font-weight:400;color:#888">W</span></div>
        <div style="font-size:11px;color:#aaa;margin-bottom:6px">Estimated FTP · 7 power zones</div>
        <div class="pwr-grid">{pwr_html}</div>
      </div>
    </div>
  </div>

  <div class="sl">VO₂ max — 3 year trend (Apple Watch)</div>
  <div class="cc">
    <div style="position:relative;width:100%;height:200px"><canvas id="vo2Chart"></canvas></div>
    <div class="stat-row">
      <span>Current: <strong>38.6</strong></span>
      <span>Peak: <strong style="color:#3b6d11">43.2</strong> (Dec 2024)</span>
      <span>Good for age 44M: <strong>42.5+</strong></span>
      <span style="color:#854f0b">↓ 4.6 from peak</span>
    </div>
  </div>

  <div class="sl">Apple Health — Resting HR &amp; HRV</div>
  <div class="two">
    <div class="cc" style="margin-bottom:0">
      <div style="font-size:12px;color:#666;margin-bottom:4px">Resting Heart Rate · 30-day avg</div>
      <div style="font-size:36px;font-weight:500">57 <span style="font-size:16px;color:#888;font-weight:400">bpm</span></div>
      <div style="font-size:11px;color:#aaa;margin-top:4px">Range: 47–69 bpm · Excellent for age 44</div>
    </div>
    <div class="cc" style="margin-bottom:0">
      <div style="font-size:12px;color:#666;margin-bottom:4px">HRV (SDNN) · 30-day avg</div>
      <div style="font-size:36px;font-weight:500">46 <span style="font-size:16px;color:#888;font-weight:400">ms</span></div>
      <div style="font-size:11px;color:#aaa;margin-top:4px">Peak: 71 ms (May 27) · Target: 55–65 ms baseline</div>
    </div>
  </div>

  <div class="sl">Blood diagnostics — annual (Jan 2026)</div>
  <div class="cc">
    <div class="blood-grid">
      <div>
        <div class="brow"><span style="color:#666">Glucose</span><span class="bval-good">91 mg/dL</span></div>
        <div class="brow"><span style="color:#666">Total cholesterol</span><span class="bval-good">178 mg/dL</span></div>
        <div class="brow"><span style="color:#666">LDL</span><span class="bval-good">102 mg/dL</span></div>
        <div class="brow"><span style="color:#666">HDL</span><span class="bval-good">58 mg/dL</span></div>
      </div>
      <div>
        <div class="brow"><span style="color:#666">Triglycerides</span><span class="bval-warn">148 mg/dL</span></div>
        <div class="brow"><span style="color:#666">HbA1c</span><span class="bval-good">5.2%</span></div>
        <div class="brow"><span style="color:#666">Ferritin</span><span class="bval-warn">18 ng/mL</span></div>
        <div class="brow"><span style="color:#666">Vitamin D</span><span class="bval-warn">28 ng/mL</span></div>
      </div>
    </div>
    <div style="margin-top:10px;font-size:11px;color:#aaa">Next annual draw: Jan 2027 · <span style="color:#854f0b">3 markers to watch: Triglycerides, Ferritin, Vitamin D</span></div>
  </div>

  <div class="sl">Recommendations</div>
  <div class="rc">
    <div class="rr"><div class="ri">↑</div><div><div class="rt">VO₂ max 4.6 pts below your Dec 2024 peak — 2× Zone 2 rides per week will reverse this</div><div class="rsub">Target: back above 42 by end of summer. Your gravel rides are your best VO₂ stimulus.</div></div></div>
    <div class="rr"><div class="ri">🏋️</div><div><div class="rt">Strength training missing — add 2× per week</div><div class="rsub">Cycling + pickleball cover cardio well. Strength is the missing pillar for longevity at 44. Even 30 min bodyweight sessions count.</div></div></div>
    <div class="rr"><div class="ri">〜</div><div><div class="rt">HRV of 46 ms — consistent sleep timing is the highest-leverage fix</div><div class="rsub">Your ceiling is 71 ms. Regular bedtime + limiting alcohol pushes baseline to 55–65 ms range.</div></div></div>
    <div class="rr"><div class="ri">♥</div><div><div class="rt">Resting HR 57 bpm — excellent for 44, top ~15% for your age</div><div class="rsub">Protect it by keeping 2 aerobic sessions per week minimum. Don't let the base erode further.</div></div></div>
    <div class="rr"><div class="ri">☀</div><div><div class="rt">Vitamin D (28) and ferritin (18) are low-normal — discuss supplementation with your doctor</div><div class="rsub">Both affect energy and recovery on hard efforts. Worth addressing before next annual blood draw.</div></div></div>
  </div>

  <footer>
    jbogart · Health Dashboard · Murrieta CA<br>
    Strava refreshes every 6 hours via GitHub Actions · Apple Health data from last manual export<br>
    Not medical advice · Always consult your doctor
  </footer>
</div>

<script>
const grid='rgba(0,0,0,0.06)',tick='rgba(0,0,0,0.4)';

new Chart(document.getElementById('volChart'),{{
  type:'bar',
  data:{{
    labels:{month_labels},
    datasets:[
      {{label:'Cycling',data:{ride_data},backgroundColor:'rgba(55,138,221,0.75)',stack:'s',borderRadius:3}},
      {{label:'Pickleball',data:{pb_data},backgroundColor:'rgba(226,75,74,0.75)',stack:'s',borderRadius:3}},
      {{label:'Run/Hike',data:{run_data},backgroundColor:'rgba(29,158,117,0.75)',stack:'s',borderRadius:3}}
    ]
  }},
  options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}},
    scales:{{y:{{stacked:true,ticks:{{color:tick,font:{{size:10}},callback:v=>v?v+' kcal':''}},grid:{{color:grid}}}},
             x:{{stacked:true,ticks:{{color:tick,font:{{size:10}}}},grid:{{color:'transparent'}}}}}}}}
}});

const vo2Labels=["Jun'23","Jul'23","Aug'23","Sep'23","Oct'23","Nov'23","Dec'23","Jan'24","Feb'24","Mar'24","Apr'24","May'24","Jun'24","Jul'24","Aug'24","Sep'24","Oct'24","Nov'24","Dec'24","Feb'25","Mar'25","May'25","Jun'25","Jul'25","Oct'25","Jan'26","Feb'26","Mar'26","May'26","Jun'26"];
const vo2Vals=[41.8,41.8,39.3,41.0,42.0,41.9,41.1,38.7,39.2,40.6,37.0,39.5,39.9,40.0,37.5,36.3,38.1,40.2,43.2,42.4,39.5,38.2,38.0,39.8,40.9,37.1,37.6,38.1,38.5,38.6];
new Chart(document.getElementById('vo2Chart'),{{
  type:'line',
  data:{{labels:vo2Labels,datasets:[{{label:'VO₂ max',data:vo2Vals,borderColor:'#1D9E75',backgroundColor:'rgba(29,158,117,0.08)',borderWidth:2,pointRadius:3,pointBackgroundColor:'#1D9E75',fill:true,tension:0.3}}]}},
  options:{{responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:ctx=>` ${{ctx.raw}} ml/kg/min`}}}}}},
    scales:{{y:{{min:34,max:46,ticks:{{color:tick,font:{{size:10}}}},grid:{{color:grid}}}},
             x:{{ticks:{{color:tick,font:{{size:10}},maxRotation:45,maxTicksLimit:12}},grid:{{color:'transparent'}}}}}}}}
}});
</script>
</body>
</html>"""


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("🔑 Getting Strava access token...")
    token = get_access_token()

    print("📊 Fetching athlete zones...")
    zones_data = get_athlete_zones(token)

    print("🏃 Fetching recent activities (last 90 days)...")
    activities = get_activities(token, months=3)
    print(f"   Found {len(activities)} activities")

    print("📅 Fetching 12-month history for volume chart...")
    activities_12m = get_activities(token, months=12)

    stats            = summary_stats(activities)
    recent           = recent_rows(activities, n=10)
    hr_rows, ftp, pwr_zones = hr_zone_rows(zones_data)
    monthly          = monthly_calories(activities_12m)
    week_plan, week_meta = build_week_plan(activities)

    print("🏗️  Rendering HTML...")
    html = render(stats, recent, hr_rows, ftp, pwr_zones, monthly, week_plan, week_meta)

    out = os.path.join(os.path.dirname(__file__), "..", "index.html")
    with open(out, "w") as f:
        f.write(html)
    print(f"✅ Written to index.html ({len(html):,} bytes)")
