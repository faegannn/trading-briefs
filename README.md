[README.md](https://github.com/user-attachments/files/27896980/README.md)
# Trading Briefs on GitHub Actions

Runs your daily Setup Scanner and weekly Weather Check on **GitHub's servers** — totally
independent of whether your PC is on, off, or you're traveling. Each brief is computed
fresh, formatted as HTML, and emailed directly to your Gmail.

## What runs

| Brief | Schedule (SGT) | UTC cron |
|---|---|---|
| 📊 Setup Scanner | Mon–Fri 8:00 PM | `0 12 * * 1-5` |
| 🌤️ Weather Check | Mon 8:00 PM | `0 12 * * 0` |

GitHub schedules may be delayed up to ~15 min during peak load — that's normal and harmless
for a pre-market brief.

## One-time setup (about 10 minutes)

### Step 1 — Create a private GitHub repo

1. Go to https://github.com/new
2. Repository name: `trading-briefs` (anything works)
3. Set to **Private**
4. Don't initialize with anything — leave all checkboxes unchecked
5. Click **Create repository**

### Step 2 — Upload all the files in this folder

The simplest way (no git knowledge required):

1. On the new empty repo page, click **uploading an existing file**
2. Drag and drop **all files and folders** from this `github_actions` directory:
   - `lib.py`
   - `setup_scanner.py`
   - `weather_check.py`
   - `requirements.txt`
   - `watchlist.txt`
   - `.github/workflows/scheduled-briefs.yml` (this folder needs to come along — GitHub's web
     uploader handles nested folders if you drag the entire `.github` folder over)
3. Scroll down → write a commit message like "initial setup" → click **Commit changes**

Verify the file tree on your repo looks like:
```
trading-briefs/
├── lib.py
├── setup_scanner.py
├── weather_check.py
├── requirements.txt
├── watchlist.txt
├── README.md           (optional)
└── .github/
    └── workflows/
        └── scheduled-briefs.yml
```

### Step 3 — Add your Gmail credentials as secrets

1. In the repo, click **Settings** (top right of the repo page)
2. Left sidebar → **Secrets and variables** → **Actions**
3. Click **New repository secret** (green button)
4. Add this secret:
   - **Name:** `GMAIL_USER`
   - **Secret:** `faegankhongz@gmail.com`
   - Click **Add secret**
5. Click **New repository secret** again, add a second:
   - **Name:** `GMAIL_APP_PASSWORD`
   - **Secret:** `mzal yqux vetu mwcn` (paste exactly — spaces OK, will be stripped)
   - Click **Add secret**

You should now see both secrets listed (values hidden — that's expected and correct).

### Step 4 — Enable Actions on the repo

1. Click the **Actions** tab at the top of the repo
2. If you see "Workflows aren't being run on this repository" → click the button to **enable** them.
3. You should now see **Scheduled Trading Briefs** in the workflow list.

### Step 5 — Test it manually before relying on the schedule

1. **Actions** tab → click **Scheduled Trading Briefs** in the left sidebar
2. Right side → click the **Run workflow** dropdown button
3. Choose which brief to run (start with `scanner` to test the daily one)
4. Click the green **Run workflow** button
5. Wait ~30 seconds → refresh the page → you'll see a run in progress
6. Click into it to watch the log live
7. **Check your Gmail inbox** — the test email should arrive within a minute

If the email shows up, you're done. The schedules will fire automatically from now on.

## Editing your watchlist

Edit `watchlist.txt` in the repo (click the file → pencil icon → edit → Commit changes).
The next scheduled run picks up the new list. No other changes needed.

## Changing schedules

Edit `.github/workflows/scheduled-briefs.yml`. The cron expressions are in **UTC**, not SGT.
Conversions you'll commonly want:

| You want it at (SGT) | Cron (UTC) |
|---|---|
| 7:00 PM | `0 11 * * ...` |
| 8:00 PM | `0 12 * * ...` |
| 9:00 PM | `0 13 * * ...` |
| 6:00 AM (next morning post-US-close digest) | `0 22 * * ...` |

Day-of-week: `0` = Sun, `1` = Mon, ... `5` = Fri, `6` = Sat. Range example: `1-5` = Mon–Fri.

## What it costs

GitHub Actions free tier on private repos: **2,000 minutes/month**. Each brief takes about
30 seconds. ~25 brief runs/month uses ~13 minutes. You'll never see a bill.

## If something breaks

- **No email arrives after Run workflow:** Open the failed run → click the failed step → read
  the log. The most common cause is the `GMAIL_APP_PASSWORD` secret has a typo or the wrong
  spaces. Re-add it cleanly.
- **Email lands in Spam:** Mark the first one as "Not spam" — Gmail learns and routes
  subsequent ones to inbox.
- **Scheduled run didn't fire:** GitHub disables scheduled workflows on repos with no recent
  activity (60+ days). Push any tiny change (edit the README, add a space, commit) to wake
  it back up.

## Safe to disable the Cowork scheduled tasks

Once you've confirmed at least one GitHub Actions email lands successfully, the Cowork-app
versions of these briefs (`daily-premarket-brief` and `weekly-weather-check`) are redundant.
Open Cowork → Scheduled section → toggle them off so you don't get duplicate emails.
