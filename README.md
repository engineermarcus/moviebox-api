# 🐦 Magpie Movie Box

> A headless movie & series downloader for Android (Termux) powered by Playwright and Python. One command installs everything — Ubuntu, Chromium, dependencies — and drops you into a ready shell.

---

## ✨ Features

- 🎬 Search and download movies and full TV series
- 🎯 Smart result scoring — auto picks best match or lets you choose interactively
- 📺 Season/episode scanning with up to 5 concurrent checks
- 🔍 Show metadata (genres, rating, IMDB, poster, episode counts) via TVMaze API
- 📦 Full seasons bundled into a single `.zip` archive automatically
- ☁️ Optional upload to Internet Archive — deletes local file after upload
- 🤖 Runs fully headless — no browser UI needed
- 🐧 Runs on Android via Termux + proot Ubuntu 24.04
- 🔁 One-line install from anywhere

---

## 📱 Requirements

- Android device with [Termux](https://f-droid.org/packages/com.termux/) (F-Droid only — not Google Play)
- Internet connection
- ~2GB free storage

---

## ⚡ Install

On any machine with Termux, run this single command:

```bash
curl -fsSL https://raw.githubusercontent.com/engineermarcus/moviebox-api/main/magpie -o magpie && chmod +x magpie && bash magpie install
```

This will:
1. Clone the repo into `~/moviebox-api`
2. Install `proot-distro` if missing
3. Set up Ubuntu 24.04 container
4. Install Python, Playwright and Chromium inside Ubuntu
5. Run a smoke test to confirm Playwright works
6. Add `magpie` to your PATH permanently
7. Drop you into the Ubuntu shell — ready to use

---

## 🛠️ Usage

> All `magpie --download` commands must be run **inside the Ubuntu container** — run `magpie migrate` first

### Enter the Ubuntu container
```bash
magpie migrate
```

### Install Python dependencies (run once inside Ubuntu)
```bash
magpie start
```

### Mount a folder into storage
```bash
magpie --mount downloads
```

---

## 🎬 Downloading

The basic flow is:

1. Search by title — results are listed
2. Pick a result with `--pickN`
3. Add season/episode flags as needed

### Search and pick interactively
```bash
magpie --download "Breaking Bad"
# Shows numbered results list, prompts you to pick
```

### Pick result #1 and download episode
```bash
magpie --download "Breaking Bad" --pick1 --s1 --ep3
```

### Pick result #1 and download multiple episodes
```bash
magpie --download "The Flash" --pick1 --s1 --ep3 --ep4 --ep5
```

### Pick result #1 and download a full season
```bash
magpie --download "Breaking Bad" --pick1 --s1
```

### Pick result #1 and download multiple seasons
```bash
magpie --download "The Flash" --pick1 --s1 --s2 --s3
```

### Pick result #1 and download all seasons
```bash
magpie --download "Breaking Bad" --pick1 -a
```

### Show info only — no download
```bash
magpie --download "Breaking Bad" --pick1 --info
```

### Print stream URL only — no download
```bash
magpie --download "Inception" --pick1 --url
```

### Upload to Internet Archive after download
```bash
magpie --download "Breaking Bad" --pick1 -a --upload
```

---

## 🚩 All Flags

| Flag | Description |
|------|-------------|
| `--pickN` | Pick search result #N without interactive prompt e.g. `--pick1` |
| `--sN` | Target season N e.g. `--s1` — can stack multiple `--s1 --s2 --s3` |
| `--epN` | Target episode N e.g. `--ep3` — can stack multiple `--ep3 --ep4` |
| `-a` | Download all seasons |
| `--info` | Show TVMaze metadata only, no download |
| `--url` | Print stream URL only, no download |
| `--json` | Output as JSON |
| `--upload` | Upload to Internet Archive after download, deletes local file |

---

## ⚙️ How It Works

1. **Search** — Playwright loads moviebox.ph headlessly and extracts results from the page
2. **Match** — Results are scored by title similarity, resource availability and season match
3. **Pick** — Auto selects best match or you pick manually with `--pickN`
4. **Stream** — Playwright loads the player page and intercepts the stream API response
5. **Download** — `httpx` streams the highest resolution MP4 in 1MB chunks with live progress
6. **Bundle** — Full seasons are zipped into a single archive, individual files deleted
7. **Upload** *(optional)* — Files are streamed to Internet Archive in 8MB chunks, deleted locally after

---

## 📁 Project Structure

```
moviebox-api/
├── magpie           # CLI entrypoint
├── downloader.py    # Core engine (Playwright + httpx + TVMaze)
├── setup.sh         # Ubuntu 24.04 + Playwright setup (Termux)
├── install.sh       # Python dep installer (runs inside Ubuntu)
├── migrate.sh       # Container login helper
├── mount.sh         # Storage mount helper
├── requirements.txt # Python dependencies
└── storage/
    └── movies/      # Downloaded content lands here
```

---

## ☁️ Internet Archive Upload

Set your credentials in a `.env` file at the project root:

```env
IA_ACCESS_KEY=your_access_key
IA_SECRET_KEY=your_secret_key
```

Get free keys at [archive.org/account/s3.php](https://archive.org/account/s3.php)

After upload the local file is deleted automatically to save disk space. The public URL is printed to stdout.

---

## ⚠️ Disclaimer

This project is intended for personal and educational use only. Respect copyright laws in your jurisdiction. The authors are not responsible for how this tool is used.

---

## 📄 License

MIT — free to use, modify and distribute.

---

<p align="center">Built with 🐦 by <a href="https://github.com/engineermarcus">engineermarcus</a></p>

