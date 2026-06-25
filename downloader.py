
import asyncio
import httpx
import sys
import re
import json
import zipfile
import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))
from urllib.parse import quote_plus
from playwright.async_api import async_playwright

# ── TVMaze: fetch show metadata + exact episode counts ───────────────────────
async def tvmaze_info(title: str) -> dict:
    """Returns {id, name, genres, summary, poster, imdb, seasons: {1: 12, 2: 16, ...}}"""
    import urllib.request
    try:
        url  = f"https://api.tvmaze.com/search/shows?q={urllib.parse.quote_plus(title)}"
        res  = json.loads(urllib.request.urlopen(url, timeout=10).read())
        if not res:
            return {}
        show = res[0]["show"]
        sid  = show["id"]
        seasons_raw = json.loads(urllib.request.urlopen(
            f"https://api.tvmaze.com/shows/{sid}/seasons", timeout=10
        ).read())
        seasons = {s["number"]: s["episodeOrder"] or 0 for s in seasons_raw}
        return {
            "id":      sid,
            "name":    show.get("name"),
            "genres":  show.get("genres", []),
            "summary": re.sub(r"<.*?>", "", show.get("summary") or ""),
            "poster":  (show.get("image") or {}).get("original"),
            "imdb":    (show.get("externals") or {}).get("imdb"),
            "rating":  (show.get("rating") or {}).get("average"),
            "status":  show.get("status"),
            "seasons": seasons,
        }
    except Exception as e:
        print(f"[!] TVMaze lookup failed: {e}")
        return {}

# ── Downloads folder ────────────────────────────────────────────────────────
DOWNLOADS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# ── Player URL template ───────────────────────────────────────────────────────
PLAYER_BASE = "https://netfilm.world/spa/videoPlayPage/movies/{slug}?id={id}&type=/movie/detail&detailSe={season}&detailEp={episode}&lang=en"
PLAY_API    = "https://netfilm.world/wefeed-h5api-bff/subject/play"

# ── Flag + query parser ───────────────────────────────────────────────────────
def parse_args(argv: list):
    if len(argv) < 2:
        return None, [], [], False, False, False, None, False, False

    query = argv[1]
    flags = argv[2:]

    download_all = "-a" in flags
    json_mode    = "--json" in flags
    info_mode    = "--info" in flags
    url_mode     = "--url" in flags
    upload_mode  = "--upload" in flags
    seasons      = []
    episodes     = []
    pick_index   = None

    for f in flags:
        m = re.match(r'^--s(\d+)$', f)
        if m:
            seasons.append(int(m.group(1)))
        m2 = re.match(r'^--ep(\d+)$', f)
        if m2:
            episodes.append(int(m2.group(1)))
        m3 = re.match(r'^--pick(\d+)$', f)
        if m3:
            pick_index = int(m3.group(1)) - 1

    return query, seasons, episodes, download_all, bool(seasons), json_mode, pick_index, info_mode, url_mode, upload_mode

# ── Natural language query parser ─────────────────────────────────────────────
def parse_query(query: str):
    q = query.lower()
    season, episode = 1, 1
    s = re.search(r'\b(?:season|s)\s*(\d+)', q)
    e = re.search(r'\b(?:episode|ep|e)\s*(\d+)', q)
    if s:
        season = int(s.group(1))
        q = q[:s.start()].strip()
    if e:
        episode = int(e.group(1))
    return re.sub(r'\s+', ' ', q).strip(), season, episode

# ── Search moviebox.ph via __NUXT__ ──────────────────────────────────────────
async def search_movie(title: str) -> list:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu', '--no-zygote', '--single-process'])
        page = await browser.new_page()
        search_url = f"https://moviebox.ph/web/searchResult?keyword={quote_plus(title)}"
        print(f"[→] Searching: {search_url}")
        await page.goto(search_url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)
        raw = await page.evaluate("() => JSON.stringify(window.__NUXT__ || null)")
        await browser.close()

    if not raw:
        print("[✗] window.__NUXT__ not found")
        return []

    nuxt = json.loads(raw)
    for val in (nuxt.get("data") or {}).values():
        inner = val.get("data") if isinstance(val, dict) else None
        if isinstance(inner, dict) and isinstance(inner.get("items"), list) and inner["items"]:
            print(f"[✓] Got {len(inner['items'])} results")
            return inner["items"]

    print("[✗] Could not find items in __NUXT__")
    return []

# ── Pick best match ───────────────────────────────────────────────────────────
def pick_best(items: list, title: str, season: int = 1) -> dict | None:
    title_words = set(title.lower().split())
    scored = []
    for item in items:
        name = (item.get("name") or item.get("title") or item.get("subjectName") or "").lower()
        title_score  = len(title_words & set(re.split(r'\W+', name)))
        has_res      = 3 if item.get("hasResource") else 0
        season_match = 2 if re.search(rf'\bs{season}\b', name, re.I) else 0
        bundle_pen   = -1 if re.search(r's\d+[-–]s\d+', name, re.I) else 0
        scored.append((title_score + has_res + season_match + bundle_pen, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0][1] if scored else None
    if best:
        print(f"[✓] Best match: {best.get('title') or best.get('name')}  "
              f"slug={best.get('detailPath')}  id={best.get('subjectId')}")
    return best

# ── Build player URL ──────────────────────────────────────────────────────────
def build_player_url(item: dict, season: int, episode: int) -> str:
    slug     = item.get("detailPath") or item.get("aliasName") or item.get("alias")
    movie_id = item.get("subjectId") or item.get("id")
    return PLAYER_BASE.format(slug=slug, id=movie_id, season=season, episode=episode)

# ── Intercept stream URL from player page (Playwright) ───────────────────────
async def get_stream_url(player_url: str) -> dict:
    result = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu', '--no-zygote', '--single-process'])
        page = await browser.new_page()

        async def on_response(response):
            if "wefeed-h5api-bff/subject/play" in response.url:
                try:
                    data = await response.json()
                    print(f"[API] {str(data)[:300]}")
                    result["data"] = data
                except Exception as ex:
                    print(f"[!] Parse failed: {ex}")

        page.on("response", on_response)
        print(f"[→] Loading player: {player_url}")
        await page.goto(player_url, wait_until="domcontentloaded")
        print(f"[→] Page loaded, waiting for stream API...")
        for i in range(60):
            if "data" in result:
                print(f"[✓] Stream API intercepted at {i*0.5:.1f}s")
                break
            await asyncio.sleep(0.5)
        else:
            print(f"[✗] Stream API never fired after 30s")
        await browser.close()
    return result

# ── Fetch streams for one episode via Playwright ──────────────────────────────
async def fetch_streams_direct(slug: str, movie_id: str, season: int, episode: int) -> list:
    player_url = PLAYER_BASE.format(slug=slug, id=movie_id, season=season, episode=episode)
    result = await get_stream_url(player_url)
    return (result.get("data") or {}).get("data", {}).get("streams") or []

# ── Scan available episodes — sequential, one browser reused ─────────────────
async def scan_episodes(slug: str, movie_id: str, season: int, max_ep: int = 50) -> list:
    available = []
    sem = asyncio.Semaphore(5)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu', '--no-zygote', '--single-process'])

        async def check_ep(ep):
            async with sem:
                page  = await browser.new_page()
                event = asyncio.Event()
                found = []

                async def on_response(response, _ep=ep, _found=found, _event=event):
                    if "wefeed-h5api-bff/subject/play" in response.url:
                        try:
                            data    = await response.json()
                            streams = (data.get("data") or {}).get("streams") or []
                            if streams:
                                _found.append(_ep)
                        except:
                            pass
                        finally:
                            _event.set()

                page.on("response", on_response)
                player_url = PLAYER_BASE.format(slug=slug, id=movie_id, season=season, episode=ep)
                try:
                    await page.goto(player_url, wait_until="domcontentloaded", timeout=20000)
                    await asyncio.wait_for(event.wait(), timeout=5)
                except:
                    pass
                await page.close()
                return found[0] if found else None

        tasks   = [asyncio.create_task(check_ep(ep)) for ep in range(1, max_ep + 1)]
        results = await asyncio.gather(*tasks)
        await browser.close()

    for ep, result in enumerate(results, 1):
        if result is not None:
            print(f"    S{season:02d}E{ep:02d} ✓")
            available.append(ep)
        else:
            print(f"    S{season:02d}E{ep:02d} ✗")

    return available

# ── Download one video file ───────────────────────────────────────────────────
async def download(url: str, output: str, referer: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/147.0.0.0 Safari/537.36",
        "Referer": referer,
        "Range": "bytes=0-",
    }
    print(f"[→] Downloading → {output}")
    async with httpx.AsyncClient(headers=headers, timeout=300, follow_redirects=True) as client:
        async with client.stream("GET", url) as r:
            total = int(r.headers.get("content-length", 0))
            done  = 0
            with open(output, "wb") as f:
                async for chunk in r.aiter_bytes(chunk_size=1024 * 1024):
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        print(f"\r[↓] {done/total*100:.1f}%  ({done//1048576}MB / {total//1048576}MB)", end="", flush=True)
    print(f"\n[✓] Saved: {output}")


# ── Upload to Internet Archive S3 ────────────────────────────────────────────
async def upload_to_archive(filepath: str, title: str) -> str | None:
    import secrets as _sec
    access = os.environ.get("IA_ACCESS_KEY", "519485iDXPo2XjhG")
    secret = os.environ.get("IA_SECRET_KEY", "a2OI2iEdx5mEgFGg")
    if not access or not secret:
        print("[✗] Missing env vars: IA_ACCESS_KEY and IA_SECRET_KEY")
        return None
    filename   = os.path.basename(filepath)
    _safe = re.sub(r"[^\w-]", "-", title.lower())[:40]
    identifier = f"cybernetics-{_safe}-{_sec.token_hex(4)}"
    file_size  = os.path.getsize(filepath)
    upload_url = f"https://s3.us.archive.org/{identifier}/{filename}"
    headers = {
        "Authorization":              f"LOW {access}:{secret}",
        "x-archive-meta-title":       title,
        "x-archive-meta-mediatype":   "movies",
        "x-archive-auto-make-bucket": "1",
        "Content-Length":             str(file_size),
        "Content-Type":               "video/mp4",
    }
    print(f"[→] Uploading → archive.org  [{file_size // 1048576}MB]")

    async def streamer():
        done = 0
        with open(filepath, "rb") as fh:
            while chunk := fh.read(8 * 1024 * 1024):   # 8 MB chunks — zero RAM bloat
                done += len(chunk)
                print(f"\r[↑] {done / file_size * 100:.1f}%  ({done // 1048576}MB / {file_size // 1048576}MB)", end="", flush=True)
                yield chunk

    async with httpx.AsyncClient(timeout=900) as client:
        r = await client.put(upload_url, content=streamer(), headers=headers)
    print()
    if r.status_code in (200, 201):
        url = f"https://archive.org/download/{identifier}/{filename}"
        print(f"[✓] Stream URL : {url}")
        os.remove(filepath)
        print(f"[✓] Disk cleared: {filename}")
        return url
    print(f"[✗] Upload failed {r.status_code}: {r.text[:200]}")
    return None

# ── Download one episode (with fallback to nearest available) ─────────────────
async def download_episode(movie: dict, title: str, season: int, episode: int, explicit: bool = False, upload: bool = False):
    slug     = movie["detailPath"]
    movie_id = movie["subjectId"]
    safe     = re.sub(r'[^\w-]', '', title.replace(' ', '-'))

    streams = await fetch_streams_direct(slug, movie_id, season, episode)

    if not streams:
        if explicit:
            print(f"[✗] Episode {episode} not available")
            return
        print(f"[✗] S{season:02d}E{episode:02d} has no streams — scanning season {season}...")
        available = await scan_episodes(slug, movie_id, season)
        if not available:
            print(f"[✗] Season {season} has no available episodes on this site.")
            return
        print(f"[✓] Available episodes in S{season:02d}: {available}")
        episode = available[0]
        print(f"[→] Falling back to episode {episode}")
        streams = await fetch_streams_direct(slug, movie_id, season, episode)

    best     = max(streams, key=lambda s: int(s["resolutions"]))
    size_mb  = int(best["size"]) // 1048576
    referer  = build_player_url(movie, season, episode)
    output   = os.path.join(DOWNLOADS_DIR, f"{safe}-s{season:02d}e{episode:02d}.mp4")
    print(f"[✓] {best['resolutions']}p | {size_mb}MB")
    await download(best["url"], output, referer=referer)
    if upload:
        await upload_to_archive(output, title)

# ── Scan and display all available seasons/episodes (no download) ─────────────
async def scan_all_seasons_info(movie: dict, title: str):
    import urllib.request, urllib.parse
    name = movie.get("title") or movie.get("name") or title
    try:
        res  = json.loads(urllib.request.urlopen(
            f"https://api.tvmaze.com/search/shows?q={urllib.parse.quote_plus(title)}", timeout=10
        ).read())
        show = res[0]["show"] if res else {}
        sid  = show.get("id")
        seasons_raw = json.loads(urllib.request.urlopen(
            f"https://api.tvmaze.com/shows/{sid}/seasons", timeout=10
        ).read()) if sid else []
        poster  = (show.get("image") or {}).get("original")
        genres  = ", ".join(show.get("genres") or [])
        rating  = (show.get("rating") or {}).get("average")
        summary = re.sub(r"<.*?>", "", show.get("summary") or "")
        imdb    = (show.get("externals") or {}).get("imdb")
        status  = show.get("status")
        print(f"\n[i] {name}")
        print(f"    Genres : {genres}")
        print(f"    Rating : {rating}")
        print(f"    Status : {status}")
        print(f"    IMDB   : {imdb}")
        print(f"    Poster : {poster}")
        print(f"    Summary: {summary[:150]}...")
        print(f"\n    Seasons:")
        for s in seasons_raw:
            print(f"      S{s['number']:02d} → {s['episodeOrder']} episodes")
        print(f"\n[✓] Done.")
    except Exception as e:
        print(f"[!] TVMaze lookup failed: {e}")

# ── Download a full season ────────────────────────────────────────────────────
async def download_season(movie: dict, title: str, season: int, upload: bool = False) -> list | bool:
    slug     = movie["detailPath"]
    movie_id = movie["subjectId"]
    safe     = re.sub(r'[^\w-]', '', title.replace(' ', '-'))

    print(f"\n[→] Scanning season {season}...")
    available = await scan_episodes(slug, movie_id, season)

    if not available:
        print(f"[i] Season {season} — not released yet or not available on this site.")
        return False

    print(f"[✓] Season {season} has {len(available)} episode(s): {available}")
    downloaded = []
    for ep in available:
        streams = await fetch_streams_direct(slug, movie_id, season, ep)
        if not streams:
            print(f"[!] S{season:02d}E{ep:02d} — no streams, skipping")
            continue
        best    = max(streams, key=lambda s: int(s["resolutions"]))
        size_mb = int(best["size"]) // 1048576
        referer = build_player_url(movie, season, ep)
        output  = os.path.join(DOWNLOADS_DIR, f"{safe}-s{season:02d}e{ep:02d}.mp4")
        print(f"[✓] S{season:02d}E{ep:02d} — {best['resolutions']}p | {size_mb}MB")
        await download(best["url"], output, referer=referer)
        if upload:
            url = await upload_to_archive(output, title)
            if url:
                downloaded.append(url)
            continue
        downloaded.append(output)
    if not upload:
        bundle_videos(downloaded, os.path.join(DOWNLOADS_DIR, f"{safe}-s{season:02d}"))
    return downloaded

# ── Download all seasons ──────────────────────────────────────────────────────
async def download_all_seasons(movie: dict, title: str, upload: bool = False):
    safe      = re.sub(r'[^\w-]', '', title.replace(' ', '-'))
    all_files = []
    season    = 1
    while True:
        result = await download_season(movie, title, season, upload=upload)
        if result is False:
            print(f"[✓] No more seasons after season {season - 1}. Done.")
            break
        if isinstance(result, list):
            all_files.extend(result)
        season += 1
    bundle_videos(all_files, os.path.join(DOWNLOADS_DIR, safe))

# ── Bundle downloaded videos into a zip ───────────────────────────────────────
def bundle_videos(files: list, archive_name: str):
    if len(files) < 2:
        return
    zip_path = f"{archive_name}.zip"
    print(f"\n[→] Bundling {len(files)} files → {zip_path}")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
        for f in files:
            if os.path.exists(f):
                zf.write(f, arcname=os.path.basename(f))
                print(f"    + {f}")
    total_mb = os.path.getsize(zip_path) // 1048576
    print(f"[✓] Archive ready: {zip_path} ({total_mb}MB)")
    for f in files:
        if os.path.exists(f):
            os.remove(f)
            print(f"    - deleted {os.path.basename(f)}")

# ── Display results list + prompt user to pick ───────────────────────────────
def show_results(items: list):
    print()
    for i, item in enumerate(items):
        title   = item.get("title") or item.get("name") or "Unknown"
        year    = (item.get("releaseDate") or "")[:4]
        country = item.get("countryName") or ""
        genre   = item.get("genre") or ""
        cover   = (item.get("cover") or {}).get("url") or ""
        rating  = item.get("imdbRatingValue") or ""
        has_res = "✓" if item.get("hasResource") else "✗"
        print(f"  [{i+1}] {has_res} {title} ({year}) | {country} | {genre}")
        if rating:
            print(f"       IMDB: {rating}")
        if cover:
            print(f"       Cover: {cover}")
        print()

def prompt_pick(items: list, best: dict) -> dict:
    show_results(items)
    best_idx = items.index(best) + 1
    try:
        raw = input(f"Pick a number [Enter = auto best match #{best_idx}]: ").strip()
        if not raw:
            return best
        idx = int(raw) - 1
        if 0 <= idx < len(items):
            return items[idx]
        print(f"[!] Invalid choice, using best match #{best_idx}")
        return best
    except (ValueError, EOFError):
        return best

# ── Help text ────────────────────────────────────────────────────────────────
def print_help():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║                     Movie Downloader CLI                         ║
╚══════════════════════════════════════════════════════════════════╝

USAGE:
  python downloader.py "<title>" [flags]

SEARCH & SELECTION:
  --json          Dump search results as JSON and exit (for AI tool use)
  --pickN         Select result #N without interactive prompt (e.g. --pick1)

DOWNLOAD MODES:
  (no flags)      Single movie or episode parsed from title
  -a              Download ALL seasons and episodes
  --sN            Download full season N (e.g. --s1, --s3)
  --sN --epM      Download specific episode M of season N
  --sN --epM --epK  Download multiple episodes from one season
  --s1 --s2 --s3  Download multiple full seasons

RULES:
  ✓  Multiple --ep flags require exactly one --s flag
  ✗  Multiple --s + multiple --ep is not allowed (ambiguous)

EXAMPLES:
  python downloader.py "suits"
  python downloader.py "suits season 9 episode 1"
  python downloader.py "the flash" --json
  python downloader.py "the flash" --pick1 --s1
  python downloader.py "the flash" --pick1 --s1 --ep3 --ep4 --ep5
  python downloader.py "the flash" --pick1 --s1 --s2 --s3
  python downloader.py "the flash" --pick1 -a
  python downloader.py "the flash" --pick1 --info

OUTPUT:
  Downloads saved to: ./downloads/
  2+ episodes are auto-zipped and source files deleted.
""")

# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    if len(sys.argv) < 2 or "--help" in sys.argv or "-h" in sys.argv:
        print_help()
        sys.exit(0)

    query, seasons, episodes, dl_all, dl_season, json_mode, pick_index, info_mode, url_mode, upload_mode = parse_args(sys.argv)

    known = {"-a", "--json", "--info", "--url", "--upload"}
    for f in sys.argv[2:]:
        if f.startswith("-") and f not in known:
            if not re.match(r'^--(s\d+|ep\d+|pick\d+)$', f):
                print(f"[✗] Unknown flag: {f}")
                print("    Run with --help to see usage.")
                sys.exit(1)

    if len(seasons) > 1 and len(episodes) > 1:
        print("[✗] Can't combine multiple --s flags with multiple --ep flags.")
        print("    Use multiple --s for full seasons, or one --s with multiple --ep.")
        print("    Run with --help to see usage.")
        sys.exit(1)

    title, q_season, q_episode = parse_query(query)

    if not seasons:
        seasons = [q_season]
    if not episodes:
        episodes = [q_episode]

    print(f"[i] Title={title!r}")

    items = await search_movie(title)
    if not items:
        sys.exit(1)

    if json_mode:
        out = []
        for item in items:
            out.append({
                "title":       item.get("title") or item.get("name"),
                "year":        (item.get("releaseDate") or "")[:4],
                "country":     item.get("countryName"),
                "genre":       item.get("genre"),
                "imdb":        item.get("imdbRatingValue"),
                "description": item.get("description"),
                "hasResource": item.get("hasResource"),
                "detailPath":  item.get("detailPath"),
                "subjectId":   item.get("subjectId"),
                "cover":       (item.get("cover") or {}).get("url"),
            })
        print(json.dumps(out, indent=2, ensure_ascii=False))
        sys.exit(0)
    if url_mode:
        best = pick_best(items, title, seasons[0])
        if pick_index is not None:
            movie = items[pick_index] if 0 <= pick_index < len(items) else best
        else:
            movie = best
        streams = await fetch_streams_direct(movie["detailPath"], movie["subjectId"], seasons[0], episodes[0])
        if not streams:
            print(json.dumps({"error": "No streams found"}))
            sys.exit(1)
        best_stream = max(streams, key=lambda s: int(s["resolutions"]))
        print(json.dumps({"url": best_stream["url"], "resolution": best_stream["resolutions"], "size": best_stream["size"], "title": movie.get("title"), "referer": build_player_url(movie, seasons[0], episodes[0])}))
        sys.exit(0)

    best = pick_best(items, title, seasons[0])
    if not best:
        print("[✗] No matching title found in results")
        sys.exit(1)

    if pick_index is not None:
        movie = items[pick_index] if 0 <= pick_index < len(items) else best
    else:
        movie = prompt_pick(items, best)
    print(f"[✓] Selected: {movie.get('title') or movie.get('name')}")

    if info_mode:
        await scan_all_seasons_info(movie, title)
        return

    if dl_all:
        print(f"[i] Mode: ALL seasons")
        await download_all_seasons(movie, title, upload=upload_mode)

    elif dl_season and len(episodes) == 1 and episodes[0] == q_episode and not any(f.startswith("--ep") for f in sys.argv[2:]):
        print(f"[i] Mode: full season(s) {seasons}")
        for s in seasons:
            await download_season(movie, title, s, upload=upload_mode)

    elif dl_season and len(seasons) == 1 and len(episodes) >= 1:
        s    = seasons[0]
        safe = re.sub(r'[^\w-]', '', title.replace(' ', '-'))
        print(f"[i] Mode: S{s:02d} episodes {episodes}")
        downloaded = []
        for ep in episodes:
            await download_episode(movie, title, s, ep, explicit=True, upload=upload_mode)
            output = os.path.join(DOWNLOADS_DIR, f"{safe}-s{s:02d}e{ep:02d}.mp4")
            if os.path.exists(output):
                downloaded.append(output)
        bundle_videos(downloaded, os.path.join(DOWNLOADS_DIR, f"{safe}-s{s:02d}"))

    else:
        s, ep = seasons[0], episodes[0]
        print(f"[i] Mode: S{s:02d}E{ep:02d}")
        await download_episode(movie, title, s, ep, explicit=True, upload=upload_mode)

# ── Flask API server ──────────────────────────────────────────────────────────
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import threading

app = Flask(__name__)
CORS(app)

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

@app.route("/api/search", methods=["GET"])
def api_search():
    title = request.args.get("q", "").strip()
    if not title:
        return jsonify({"error": "Missing ?q="}), 400
    items = run_async(search_movie(title))
    out = [{"title": i.get("title") or i.get("name"), "year": (i.get("releaseDate") or "")[:4], "country": i.get("countryName"), "genre": i.get("genre"), "imdb": i.get("imdbRatingValue"), "description": i.get("description"), "hasResource": i.get("hasResource"), "detailPath": i.get("detailPath"), "subjectId": i.get("subjectId"), "cover": (i.get("cover") or {}).get("url")} for i in items]
    return jsonify(out)

@app.route("/api/streams", methods=["GET"])
def api_streams():
    detail_path = request.args.get("detailPath")
    subject_id  = request.args.get("subjectId")
    season      = int(request.args.get("season", 1))
    episode     = int(request.args.get("episode", 1))
    if not detail_path or not subject_id:
        return jsonify({"error": "Missing detailPath or subjectId"}), 400
    streams = run_async(fetch_streams_direct(detail_path, subject_id, season, episode))
    if not streams:
        return jsonify({"error": "No streams found"}), 404
    return jsonify(streams)

@app.route("/api/download", methods=["POST"])
def api_download():
    body        = request.get_json() or {}
    detail_path = body.get("detailPath")
    subject_id  = body.get("subjectId")
    title       = body.get("title", "unknown")
    season      = int(body.get("season", 1))
    episode     = int(body.get("episode", 1))
    upload      = bool(body.get("upload", False))
    if not detail_path or not subject_id:
        return jsonify({"error": "Missing detailPath or subjectId"}), 400
    streams = run_async(fetch_streams_direct(detail_path, subject_id, season, episode))
    if not streams:
        return jsonify({"error": "No streams found"}), 404
    best    = max(streams, key=lambda s: int(s["resolutions"]))
    movie   = {"detailPath": detail_path, "subjectId": subject_id}
    referer = build_player_url(movie, season, episode)
    if upload:
        safe   = re.sub(r"[^\w-]", "", title.replace(" ", "-"))
        output = os.path.join(DOWNLOADS_DIR, f"{safe}-s{season:02d}e{episode:02d}.mp4")
        def bg():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(download(best["url"], output, referer=referer))
            loop.run_until_complete(upload_to_archive(output, title))
            loop.close()
        threading.Thread(target=bg, daemon=True).start()
        return jsonify({"status": "downloading+uploading", "resolution": best["resolutions"]})
    return jsonify({"url": best["url"], "referer": referer, "resolution": best["resolutions"], "size_mb": int(best["size"]) // 1048576, "title": title, "season": season, "episode": episode})

@app.route("/api/info", methods=["GET"])
def api_info():
    title = request.args.get("q", "").strip()
    if not title:
        return jsonify({"error": "Missing ?q="}), 400
    return jsonify(run_async(tvmaze_info(title)))

@app.route("/api/files", methods=["GET"])
def api_files():
    files = [{"name": f, "size_mb": os.path.getsize(os.path.join(DOWNLOADS_DIR, f)) // 1048576} for f in os.listdir(DOWNLOADS_DIR) if os.path.isfile(os.path.join(DOWNLOADS_DIR, f))]
    return jsonify(files)

@app.route("/api/proxy", methods=["GET"])
def api_proxy():
    url     = request.args.get("url")
    referer = request.args.get("referer", "https://netfilm.world/")
    if not url:
        return jsonify({"error": "Missing ?url="}), 400
    import httpx
    from flask import Response
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/147.0.0.0 Safari/537.36",
        "Referer": referer,
        "Range": request.headers.get("Range", "bytes=0-"),
    }
    def generate():
        with httpx.stream("GET", url, headers=headers, timeout=300, follow_redirects=True) as r:
            for chunk in r.iter_bytes(chunk_size=1024 * 1024):
                yield chunk
    with httpx.stream("GET", url, headers=headers, timeout=10, follow_redirects=True) as r:
        status = r.status_code
        resp_headers = {
            "Content-Type": r.headers.get("Content-Type", "video/mp4"),
            "Content-Length": r.headers.get("Content-Length", ""),
            "Accept-Ranges": "bytes",
            "Content-Range": r.headers.get("Content-Range", ""),
        }
    return Response(generate(), status=status, headers=resp_headers, direct_passthrough=True)

@app.route("/api/files/<filename>", methods=["GET"])
def api_serve_file(filename):
    fp = os.path.join(DOWNLOADS_DIR, filename)
    if not os.path.exists(fp):
        return jsonify({"error": "File not found"}), 404
    return send_file(fp, as_attachment=True)

if __name__ == "__main__":
    if "--server" in sys.argv:
        print("[Flask] Starting on http://0.0.0.0:5000")
        app.run(host="0.0.0.0", port=5000, debug=False)
    else:
        asyncio.run(main())
