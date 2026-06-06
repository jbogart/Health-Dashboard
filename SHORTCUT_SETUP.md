# Apple Health Auto-Sync — iPhone Shortcut Setup

## What it does
Runs every night at 11 PM, reads key metrics from Apple Health,
and POSTs them to your Cloudflare Worker so the dashboard updates automatically.

## Metrics synced
- Resting heart rate
- HRV (heart rate variability)
- VO₂ max
- Weight
- Steps (today)
- Active calories (today)
- Sleep duration (last night)
- Mindful minutes

---

## Build the Shortcut

Open the **Shortcuts** app on your iPhone and tap **+** to create a new shortcut.
Name it **"Sync Health to Dashboard"**.

Add these actions in order:

---

### Action 1 — Get Resting Heart Rate
- Search for: **Find Health Samples**
- Type: **Resting Heart Rate**
- Sort by: **Start Date** (newest first)
- Limit: **1**
- Save result as variable: `rhrSample`

### Action 2 — Get HRV
- Search for: **Find Health Samples**
- Type: **Heart Rate Variability**
- Sort by: **Start Date** (newest first)
- Limit: **1**
- Save result as variable: `hrvSample`

### Action 3 — Get VO₂ Max
- Search for: **Find Health Samples**
- Type: **VO2 Max**
- Sort by: **Start Date** (newest first)
- Limit: **1**
- Save result as variable: `vo2Sample`

### Action 4 — Get Weight
- Search for: **Find Health Samples**
- Type: **Body Mass**
- Sort by: **Start Date** (newest first)
- Limit: **1**
- Save result as variable: `weightSample`

### Action 5 — Get Steps (today)
- Search for: **Find Health Samples**
- Type: **Step Count**
- Filter: Start Date is today
- Save result as variable: `stepSamples`

### Action 6 — Sum Steps
- Search for: **Calculate Statistics**
- Input: `stepSamples`
- Statistic: **Sum**
- Save result as variable: `totalSteps`

### Action 7 — Get Active Calories (today)
- Search for: **Find Health Samples**
- Type: **Active Energy Burned**
- Filter: Start Date is today
- Save result as variable: `calSamples`

### Action 8 — Sum Calories
- Search for: **Calculate Statistics**
- Input: `calSamples`
- Statistic: **Sum**
- Save result as variable: `totalCals`

### Action 9 — Get Sleep (last night)
- Search for: **Find Health Samples**
- Type: **Sleep Analysis**
- Filter: Start Date is yesterday
- Save result as variable: `sleepSamples`

### Action 10 — Sum Sleep Duration
- Search for: **Calculate Statistics**
- Input: `sleepSamples`
- Statistic: **Sum**
- Save result as variable: `totalSleepMin`

### Action 11 — Build JSON Dictionary
- Search for: **Dictionary**
- Add these key/value pairs:
  - `resting_hr` → Number → value from `rhrSample` (tap variable, select Value)
  - `hrv` → Number → value from `hrvSample`
  - `vo2max` → Number → value from `vo2Sample`
  - `weight_lb` → Number → value from `weightSample`
  - `steps` → Number → `totalSteps`
  - `active_calories` → Number → `totalCals`
  - `sleep_minutes` → Number → `totalSleepMin`
- Save as variable: `healthPayload`

### Action 12 — POST to Cloudflare Worker
- Search for: **Get Contents of URL**
- URL: `https://health-proxy.jbogart.workers.dev/health`
- Method: **POST**
- Headers:
  - `Content-Type` → `application/json`
  - `X-API-Key` → `a62ba4d439f7eed590834c2cfca7dedd6f80dc35d94e4935d5b1e78e00a1ee3b`
- Request Body: **JSON** → select `healthPayload`

### Action 13 — (Optional) Show notification
- Search for: **Show Notification**
- Title: `Health Sync`
- Body: `Metrics sent to dashboard ✓`

---

## Schedule it to run nightly

1. In the Shortcuts app, go to **Automation** tab
2. Tap **+** → **Personal Automation**
3. Choose **Time of Day** → set to **11:00 PM** → **Daily**
4. Add action: **Run Shortcut** → select **Sync Health to Dashboard**
5. Turn OFF **Ask Before Running**
6. Save

---

## Worker URL
`https://health-proxy.jbogart.workers.dev/health`

## Write Key (keep this secret)
`a62ba4d439f7eed590834c2cfca7dedd6f80dc35d94e4935d5b1e78e00a1ee3b`

## Test it manually
Run the shortcut once manually to confirm data is flowing.
Then check: https://health-proxy.jbogart.workers.dev/health
You should see your metrics as JSON.
