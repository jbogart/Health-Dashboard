# Health Dashboard — Setup Guide

## 1. Add these files to your repo

Upload the following to `jbogart/Health-Dashboard` on GitHub:

```
.github/
  workflows/
    refresh.yml          ← the GitHub Action
scripts/
  generate_dashboard.py  ← the data + HTML generator
index.html               ← your current dashboard (starting point)
```

## 2. Get your Strava API credentials

Go to https://www.strava.com/settings/api and create an app (or use your existing one).
You need three values:
- **Client ID**
- **Client Secret**
- **Refresh Token**

### Getting your Refresh Token
Your refresh token doesn't appear in the Strava UI — you need to do a one-time OAuth flow.
The easiest way:

1. Visit this URL in your browser (replace YOUR_CLIENT_ID):
   ```
   https://www.strava.com/oauth/authorize?client_id=YOUR_CLIENT_ID&response_type=code&redirect_uri=http://localhost&approval_prompt=force&scope=read,activity:read_all
   ```
2. Approve — you'll be redirected to a localhost URL with `?code=XXXXXXX` in the address bar. Copy that code.

3. Run this in your terminal (replace the placeholders):
   ```bash
   curl -X POST https://www.strava.com/oauth/token \
     -d client_id=YOUR_CLIENT_ID \
     -d client_secret=YOUR_CLIENT_SECRET \
     -d code=YOUR_CODE \
     -d grant_type=authorization_code
   ```
4. The response JSON contains `"refresh_token"` — that's what you need.

## 3. Add secrets to GitHub

In your repo: **Settings → Secrets and variables → Actions → New repository secret**

Add these three secrets exactly:

| Secret name            | Value              |
|------------------------|--------------------|
| `STRAVA_CLIENT_ID`     | your client ID     |
| `STRAVA_CLIENT_SECRET` | your client secret |
| `STRAVA_REFRESH_TOKEN` | your refresh token |

## 4. Enable GitHub Pages

**Settings → Pages → Source: Deploy from branch → Branch: main → / (root) → Save**

## 5. Run it

- It will auto-run every 6 hours.
- To trigger it manually: **Actions → Refresh Health Dashboard → Run workflow**

Your dashboard will be live at:
**https://jbogart.github.io/Health-Dashboard/**

---

## How it works

```
Every 6 hours:
  GitHub Action runs
    → Python script calls Strava API
    → Fetches latest activities, zones, calories
    → Merges with static Apple Health baselines
    → Regenerates index.html
    → Commits and pushes to main
  GitHub Pages serves the updated file
```

## Updating Apple Health data

The Apple Health baselines (resting HR, HRV, VO₂ max, blood work) are
baked into the generator script. To update them:

1. Export fresh data from the Health app
2. Share it with Claude: "Here's my new Apple Health export, please update the dashboard"
3. Claude will re-parse and update the static values in `generate_dashboard.py`
