# Google Sheets sync

Widgets that store user-editable lists (contacts, shopping, todo,
border crossings, bookmarks) can persist to a shared Google Sheets
workbook instead of the Pi-local SQLite. That way:

* You edit lists from any device — the Google Sheets iOS/Android app
  works, so does the web UI.
* Family members can collaborate — share the sheet like any other.
* Data survives Pi rebuilds — the workbook is the source of truth.

Setup takes ~15 minutes and needs a free Google Cloud project.

## What you'll do

1. Create a Google Sheet with one tab per widget.
2. Create a Google Cloud project + service account.
3. Share the sheet with the service account.
4. Drop the service account's JSON key on the Pi.
5. Set two environment variables in `backend/.env`.
6. Restart the backend.

## 1. Create the workbook

At <https://sheets.google.com>, create a blank sheet and name it
whatever you like (e.g. **"SolarSage Lists"**).

Rename `Sheet1` to `Contacts`, then add these five tabs (use the `+`
button in the bottom-left):

| Tab name | Row 1 headers (lowercase, exact spelling) |
|---|---|
| **Contacts** | `name` · `phone` · `email` · `location` · `tags` · `notes` |
| **Shopping** | `text` · `category` · `checked` · `notes` |
| **Todo** | `text` · `priority` · `due` · `done` · `notes` |
| **Border Log** | `date` · `direction` · `port` · `wait_min` · `purpose` · `notes` |
| **Bookmarks** | `label` · `url` · `group` |

> Tabs missing from the workbook get **auto-created** by the backend on
> first write, so if you forget one it fills itself in.

Grab the **sheet ID** from the URL — the long string between `/d/` and
`/edit`.

```
https://docs.google.com/spreadsheets/d/1UvkNRXwyAx_vyPHeZRvwzdzpqcAB1o6dGimif2Pfw7w/edit
                                       ^─────────── sheet ID ─────────────^
```

## 2. Google Cloud project + service account

At <https://console.cloud.google.com>:

1. Top-left project dropdown → **New Project** → name it (e.g.
   `solarsage`) → Create. Wait ~10 seconds for creation.
2. Left menu → **APIs & Services → Library** → search **"Google Sheets
   API"** → **Enable**.
3. Left menu → **APIs & Services → Credentials** → **+ Create
   Credentials → Service Account**.
4. Name it something memorable (e.g. `solarsage-widgets`) → **Create
   and Continue**. Skip the role step (just click Continue) → **Done**.
5. On the credentials page, click the service account you just created.
6. **Keys tab → Add Key → Create new key → JSON**. A JSON file
   downloads to your computer. **Note the service account's email
   address** — it looks like
   `solarsage-widgets@solarsage-xxxxx.iam.gserviceaccount.com`.

## 3. Share the sheet with the service account

Back in your Google Sheet, click the **Share** button (top-right):

* Paste the service account's email address
* Give it **Editor** access
* **Uncheck** "Notify people" (the service account can't read email
  anyway)
* Click Send

## 4. Upload the JSON key to the Pi

From your laptop, in a real terminal:

```bash
scp ~/Downloads/solarsage-*.json chris@pi-sf.hitorro.com:/home/chris/.config/solarsage-sheets.json
ssh chris@pi-sf.hitorro.com "chmod 600 /home/chris/.config/solarsage-sheets.json"
```

600 perms are important — the file is a credential.

## 5. Set the env vars

Add these two lines to `backend/.env` on the Pi:

```
GOOGLE_APPLICATION_CREDENTIALS=/home/chris/.config/solarsage-sheets.json
SOLARSAGE_SHEET_ID=1UvkNRXwyAx_vyPHeZRvwzdzpqcAB1o6dGimif2Pfw7w
```

## 6. Restart

```bash
sudo systemctl restart solarsage-backend.service
```

You'll see a log line like:

```
Google Sheets sync enabled
sheets connected: id=1UvkNRXwyA… tabs=['Contacts', 'Shopping', ...]
```

Add a contact through the dashboard. Refresh your Google Sheet
browser tab (Cmd-R). The row should appear.

## How it works

* Widgets that opt in declare `sheets_tab`, `sheets_list_field`,
  and `sheets_field_order` class attrs (see
  [`docs/WIDGETS.md`](WIDGETS.md)).
* On each widget refresh, the backend reads the tab's rows,
  maps columns → widget field names using row 1 as headers, and
  passes them into the widget's `fetch(config)`.
* `PUT /api/widgets/<id>/config` intercepts the `sheets_list_field`
  array and writes it back to the sheet.
* If a tab is missing, it's auto-created with the header row.
* If Sheets is ever unreachable, the widget falls back to the
  last-known SQLite copy and logs a warning — the dashboard
  keeps working.
* Booleans (`checked`, `done`) accept `TRUE`/`FALSE`/`yes`/`1`;
  list fields (`tags`) accept comma-separated values.

## Troubleshooting

**"tab not found in sheet"** — you probably added the tab after the
backend started reading the sheet. Restart the backend to refresh its
tab list, or hit `POST /api/widgets/<id>/refresh` to force a re-scan
(the auto-create path handles this too).

**"Google Sheets sync not configured"** — either env var is missing,
or the JSON key path doesn't exist on the Pi. Check permissions on
the key file (`ls -la /home/chris/.config/solarsage-sheets.json`).

**Nothing appears in the sheet after editing on the dashboard** — refresh
your Sheets browser tab (Cmd-R). Google Sheets caches; external edits
don't push live.

**"Requested entity was not found"** — the service account isn't shared
on the sheet. Re-check step 3.

**API quota errors** — Sheets API allows 100 requests / 100 seconds
per user. Each widget refresh is ~1 request per Sheets-backed widget;
plenty of headroom.
