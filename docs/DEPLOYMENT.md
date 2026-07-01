# Pi deployment guide

This guide covers the SolarSage-on-a-Raspberry-Pi setup that ships with
the repo. The one-liner `install.sh` at the repo root handles the
generic case; this doc covers the Pi-specific bits + operations.

## Recommended hardware

* Raspberry Pi 4 or 5, 4 GB+
* 32 GB+ SD card (Class 10) or SSD
* Ethernet (Wi-Fi works but the poller likes stable connectivity)
* Powered speaker on an HDMI/audio-out for reminders (optional but fun)

Any Linux box works — no Pi-specific code. The install script picks
between apt / brew / pacman based on what it finds.

## Fresh install

```bash
curl -fsSL https://raw.githubusercontent.com/geekychris/solarsage/main/install.sh | bash
```

This creates `~/solarsage`, installs Python + Node deps, seeds
`backend/.env` with a fresh API key, and drops a `solarsage` command
on your PATH.

Then run:

```bash
solarsage start
```

and browse to <http://127.0.0.1:5173>.

## Optional: run as systemd services

For a Pi that stays on 24/7, register systemd units so the app comes
back after a reboot:

```bash
cd ~/solarsage/scripts
./install-systemd.sh          # writes /etc/systemd/system/solarsage-{backend,frontend}.service
sudo systemctl enable --now solarsage-backend.service solarsage-frontend.service
```

Check status:

```bash
systemctl status solarsage-backend.service
```

## Optional: TTS speaker service

If you want reminder voice-outs through the Pi's speaker:

```bash
sudo cp ~/tts_speaker.py /home/chris/tts_speaker.py
sudo cp ~/solarsage/scripts/tts-speaker.service /etc/systemd/system/
sudo systemctl enable --now tts-speaker.service
```

The service listens on `http://localhost:5006/say` and shells out to
`ffplay` with Google Translate TTS mp3. Reminders auto-target it via
`POST /api/tts/say`.

## Optional: HTTPS via Apache

Local network only, self-signed cert. If you already run an
`indi-allsky` or similar site, add a name-based vhost for
solarsage so it lives alongside:

See `docs/apache-solarsage.conf.example` — copy to
`/etc/apache2/sites-available/` and:

```bash
sudo a2enmod proxy_wstunnel proxy_http rewrite ssl
sudo a2ensite solarsage
sudo systemctl reload apache2
```

Then browse to `https://<pi-hostname>/`.

## Optional: Google Sheets sync

See [`docs/SHEETS.md`](SHEETS.md) — 15-minute setup, enables editing
lists (contacts / shopping / todo / border log / bookmarks) from any
device.

## Passwordless service restart for automation

Add a scoped sudoers rule so scripts and CI can restart the backend
without prompting:

```bash
echo 'chris ALL=(ALL) NOPASSWD: /bin/systemctl restart solarsage-backend.service, /bin/systemctl reload solarsage-backend.service, /bin/systemctl status solarsage-backend.service, /bin/systemctl restart solarsage-frontend.service' \
  | sudo tee /etc/sudoers.d/solarsage-restart
sudo chmod 440 /etc/sudoers.d/solarsage-restart
sudo visudo -c
```

Only these specific commands are unlocked — everything else still
prompts.

## Deploying updates

Once a Pi is running, use the helper:

```bash
cd ~/solarsage
./scripts/deploy.sh
```

That pulls the latest code, refreshes Python deps (`pip install -r
backend/requirements.txt`), and restarts the backend. The frontend is
Vite dev-mode by default, so it hot-reloads on file changes without a
service bounce.

For a one-liner from your laptop:

```bash
ssh chris@pi-sf.hitorro.com 'cd ~/solarsage && ./scripts/deploy.sh'
```

## Backups

The SQLite DB holds solar history, widget config, translations,
events, and the news archive. Back it up:

```bash
./scripts/backup.sh
```

Writes a timestamped copy to `~/solarsage-backups/`. Restore with:

```bash
./scripts/restore.sh ~/solarsage-backups/eg4_history_2026-06-30_10-00-00.db
```

For long-term retention, cron a nightly job:

```
0 3 * * * /home/chris/solarsage/scripts/backup.sh >/dev/null 2>&1
```

## Health checks

```bash
curl -sS http://localhost:8000/api/health
```

Returns `{"ok": true, "base_url": "...", "poll_interval": 60}`.

For widget health:

```bash
curl -sS -H "X-API-Key: <key>" http://localhost:8000/api/widgets \
  | jq '.widgets[] | select(.error != null) | {id, error}'
```

Prints any widget that failed its last fetch.

## Logs

```bash
sudo journalctl -u solarsage-backend.service -f
```

Or `-e --no-pager` for the last few hundred lines.

## Environment variables

All in `backend/.env`:

| Variable | Default | Purpose |
|---|---|---|
| `EG4_BASE_URL` | `https://monitor.eg4electronics.com` | EG4 portal endpoint |
| `EG4_DB_PATH` | `./eg4_history.db` | SQLite location |
| `EG4_POLL_INTERVAL` | `60` | Seconds between EG4 polls |
| `EG4_DISABLE_VERIFY_SSL` | `0` | Set to `1` to bypass TLS verify for EG4 |
| `EG4_API_KEY` | (required) | Read-only API key for `X-API-Key` header |
| `EG4_USERNAME` / `EG4_PASSWORD` | (optional) | For auto-login without the UI |
| `WORLDTIDES_API_KEY` | (optional) | For the tide widget |
| `GOOGLE_APPLICATION_CREDENTIALS` | (optional) | Path to Sheets service-account JSON |
| `SOLARSAGE_SHEET_ID` | (optional) | Google Sheets workbook ID |
| `TTS_URL` | `http://localhost:5006/say` | Local TTS service |
