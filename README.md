# Magpie Movie Box

A headless movie and series downloader for Android. Runs on Termux via a proot Ubuntu 24.04 container with Playwright and Python. One command sets everything up from scratch.

---

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/engineermarcus/moviebox-api/main/magpie -o $PREFIX/bin/magpie && chmod +x $PREFIX/bin/magpie && magpie install
```

This installs git if missing, clones the repo, sets up Ubuntu 24.04, installs Python, Playwright and Chromium, then registers `magpie` as a global command.

---

## Commands

### `magpie install`
Sets up everything from scratch — Ubuntu container, Playwright, dependencies.

### `magpie migrate`
Enter the Ubuntu container where downloads run.

### `magpie start`
Install Python dependencies inside Ubuntu. Run this once after `magpie migrate`.

### `magpie remove`
Uninstalls everything — repo, Ubuntu container, global command, PATH entries. Run `hash -r` after to clear the shell cache.

### `magpie --mount <folder>`
Move downloaded files into `storage/movies` once a download is complete.

```bash
# Run this after magpie --download finishes
magpie --mount downloads
```

### `magpie --download`
Search and download a movie or series. Always run inside Ubuntu (`magpie migrate` first).

```bash
# Search — shows numbered results, prompts you to pick
magpie --download "Breaking Bad"

# Pick result #1 and download episode
magpie --download "Breaking Bad" --pick1 --s1 --ep3

# Pick result #1 and download multiple episodes
magpie --download "The Flash" --pick1 --s1 --ep3 --ep4 --ep5

# Pick result #1 and download a full season
magpie --download "Breaking Bad" --pick1 --s2

# Pick result #1 and download multiple seasons
magpie --download "The Flash" --pick1 --s1 --s2 --s3

# Pick result #1 and download everything
magpie --download "Breaking Bad" --pick1 -a

# Show metadata only — no download
magpie --download "Breaking Bad" --pick1 --info

# Print stream URL only — no download
magpie --download "Inception" --pick1 --url

# Upload to Internet Archive after download
magpie --download "Breaking Bad" --pick1 -a --upload
```

---

## Flags

| Flag | Description |
|------|-------------|
| `--pickN` | Pick search result N without interactive prompt e.g. `--pick1` |
| `--sN` | Season N e.g. `--s1` — stackable: `--s1 --s2 --s3` |
| `--epN` | Episode N e.g. `--ep3` — stackable: `--ep3 --ep4 --ep5` |
| `-a` | Download all seasons |
| `--info` | Show TVMaze metadata only, no download |
| `--url` | Print stream URL only, no download |
| `--json` | Output as JSON |
| `--upload` | Upload to Internet Archive after download, deletes local file |

---

## How It Works

1. Playwright loads moviebox.ph headlessly and extracts search results from the page
2. Results are scored by title match, resource availability and season — best picked automatically
3. Playwright loads the player page and intercepts the stream API response
4. The highest resolution stream is selected and downloaded via httpx in 1MB chunks
5. Full seasons are bundled into a zip archive and individual files deleted
6. With `--upload`, files stream to Internet Archive in 8MB chunks and are deleted locally after

---

## Internet Archive Upload

Add credentials to a `.env` file in the project root:

```env
IA_ACCESS_KEY=your_access_key
IA_SECRET_KEY=your_secret_key
```

Get free keys at [archive.org/account/s3.php](https://archive.org/account/s3.php)

---

## Project Structure

```
moviebox-api/
├── magpie           # CLI
├── downloader.py    # Core engine
├── setup.sh         # Ubuntu + Playwright setup
├── install.sh       # Dep installer (inside Ubuntu)
├── requirements.txt # Python dependencies
└── storage/
    └── movies/      # Downloads land here
```

---

## Requirements

- Android with [Termux](https://f-droid.org/packages/com.termux/) from F-Droid
- ~2GB free storage

---

## Disclaimer

For personal and educational use only. Respect copyright laws in your jurisdiction.

---

## License

MIT

