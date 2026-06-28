import { useState, useEffect, useRef } from "react";
import axios from "axios";

const TMDB_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJhNWU0MGMwODlmOTA0NDU3MWRjZDVjOThiMjBiZmFlMSIsIm5iZiI6MTc3ODcwOTk4Mi40ODcsInN1YiI6IjZhMDRmNWRlNTc0OWJmZmZlMTZmY2FkNCIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.lN33o5iU2l0cBkF7MOfpDPd0XO6QgDxhYT8dtF8H39A";
const TMDB = axios.create({ baseURL: "https://api.themoviedb.org/3", headers: { Authorization: `Bearer ${TMDB_TOKEN}` } });
const IMG = (p, s = "w500") => p ? `https://image.tmdb.org/t/p/${s}${p}` : null;

const TABS = ["Trending", "Movies", "TV Shows", "Crime", "Drama", "Thriller", "Downloads"];

function useDebounce(value, delay) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => { const t = setTimeout(() => setDebounced(value), delay); return () => clearTimeout(t); }, [value, delay]);
  return debounced;
}

export default function App() {
  const [tab, setTab] = useState("Trending");
  const [items, setItems] = useState([]);
  const [hero, setHero] = useState(null);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [selected, setSelected] = useState(null);
  const [downloads, setDownloads] = useState([]);
  const [downloading, setDownloading] = useState({});
  const [player, setPlayer] = useState(null);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState(null);
  const debouncedQuery = useDebounce(query, 500);
  const pollRef = useRef(null);

  const showToast = (msg, type = "info") => { setToast({ msg, type }); setTimeout(() => setToast(null), 3000); };

  // Fetch TMDB content by tab
  useEffect(() => {
    if (tab === "Downloads") { fetchDownloads(); return; }
    setLoading(true);
    const endpoints = {
      Trending: "/trending/all/week",
      Movies: "/movie/popular",
      "TV Shows": "/tv/popular",
      Crime: "/discover/movie?with_genres=80&sort_by=popularity.desc",
      Drama: "/discover/movie?with_genres=18&sort_by=popularity.desc",
      Thriller: "/discover/movie?with_genres=53&sort_by=popularity.desc",
    };
    TMDB.get(endpoints[tab]).then(r => {
      const results = r.data.results || [];
      setItems(results);
      setHero(results[Math.floor(Math.random() * Math.min(5, results.length))]);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [tab]);

  // Search magpie API
  useEffect(() => {
    if (!debouncedQuery.trim()) { setSearchResults([]); return; }
    axios.get(`/api/search?q=${encodeURIComponent(debouncedQuery)}`).then(r => setSearchResults(r.data)).catch(() => {});
  }, [debouncedQuery]);

  const fetchDownloads = () => {
    axios.get("/api/files").then(r => setDownloads(r.data)).catch(() => {});
  };

  const startDownload = async (item, season = 1, episode = 1) => {
    const key = `${item.detailPath}-s${season}e${episode}`;
    setDownloading(d => ({ ...d, [key]: { progress: 0, status: "starting" } }));
    try {
      const res = await axios.post("/api/download", {
        detailPath: item.detailPath,
        subjectId: item.subjectId,
        title: item.title,
        season, episode
      });
      setDownloading(d => ({ ...d, [key]: { progress: 100, status: "done", url: res.data.url } }));
      showToast(`Download started: ${item.title}`, "success");
      pollRef.current = setInterval(fetchDownloads, 3000);
      setTimeout(() => clearInterval(pollRef.current), 60000);
    } catch {
      setDownloading(d => ({ ...d, [key]: { status: "error" } }));
      showToast("Download failed", "error");
    }
  };

  const resolveItem = async (item) => {
    if (item.detailPath && item.subjectId && !item._fromTMDB) return item;
    showToast("Searching magpie for " + item.title + "...", "info");
    const res = await axios.get(`/api/search?q=${encodeURIComponent(item.title)}`);
    const results = res.data;
    if (!results?.length) { showToast("Not found on magpie", "error"); return null; }
    return results[0];
  };

  const playStream = async (item, season = 1, episode = 1) => {
    try {
      const resolved = await resolveItem(item);
      if (!resolved) return;
      const res = await axios.get(`/api/streams?detailPath=${resolved.detailPath}&subjectId=${resolved.subjectId}&season=${season}&episode=${episode}`);
      const streams = res.data;
      if (!streams?.length) { showToast("No streams found", "error"); return; }
      const best = streams.reduce((a, b) => parseInt(a.resolutions) > parseInt(b.resolutions) ? a : b);
      const proxyUrl = `/api/proxy?url=${encodeURIComponent(best.url)}&referer=${encodeURIComponent("https://moviebox.ph/")}`;
      setPlayer({ url: proxyUrl, title: resolved.title, season, episode });
    } catch { showToast("Could not load stream", "error"); }
  };

  const startDownloadResolved = async (item, season, episode) => {
    const resolved = await resolveItem(item);
    if (!resolved) return;
    startDownload(resolved, season, episode);
  };

  const activeSearch = debouncedQuery.trim().length > 0;

  return (
    <div style={{ background: "#0a0a0f", minHeight: "100vh", color: "#fff", fontFamily: "'Inter', sans-serif" }}>

      {/* Navbar */}
      <nav style={{ position: "fixed", top: 0, left: 0, right: 0, zIndex: 100, background: "linear-gradient(to bottom, rgba(10,10,15,0.98), transparent)", padding: "16px 40px", display: "flex", alignItems: "center", gap: 32 }}>
        <div style={{ fontSize: 22, fontWeight: 800, color: "#e50914", letterSpacing: -1 }}>🐦 MAGPIE</div>
        <div style={{ display: "flex", gap: 24 }}>
          {TABS.map(t => (
            <button key={t} onClick={() => { setTab(t); setQuery(""); setSearchResults([]); }}
              style={{ background: "none", border: "none", color: tab === t ? "#fff" : "#aaa", fontWeight: tab === t ? 700 : 400, fontSize: 14, cursor: "pointer", borderBottom: tab === t ? "2px solid #e50914" : "2px solid transparent", paddingBottom: 4 }}>
              {t}
            </button>
          ))}
        </div>
        <div style={{ marginLeft: "auto", position: "relative" }}>
          <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search to download..."
            style={{ background: "rgba(255,255,255,0.1)", border: "1px solid rgba(255,255,255,0.2)", borderRadius: 8, padding: "8px 16px", color: "#fff", width: 280, fontSize: 14, outline: "none" }} />
          {query && <button onClick={() => { setQuery(""); setSearchResults([]); }}
            style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", color: "#aaa", cursor: "pointer", fontSize: 16 }}>✕</button>}
        </div>
      </nav>

      {/* Hero */}
      {!activeSearch && hero && tab !== "Downloads" && (
        <div style={{ position: "relative", height: 520, marginTop: 0, overflow: "hidden" }}>
          <img src={IMG(hero.backdrop_path, "original")} alt="" style={{ width: "100%", height: "100%", objectFit: "cover", opacity: 0.5 }} />
          <div style={{ position: "absolute", inset: 0, background: "linear-gradient(to right, rgba(10,10,15,0.95) 40%, transparent), linear-gradient(to top, rgba(10,10,15,1) 0%, transparent 50%)" }} />
          <div style={{ position: "absolute", bottom: 80, left: 60, maxWidth: 500 }}>
            <div style={{ fontSize: 11, letterSpacing: 3, color: "#e50914", fontWeight: 700, marginBottom: 8, textTransform: "uppercase" }}>
              {hero.media_type === "tv" ? "TV Series" : "Movie"} · {(hero.release_date || hero.first_air_date || "").slice(0, 4)}
            </div>
            <h1 style={{ fontSize: 44, fontWeight: 900, margin: "0 0 12px", lineHeight: 1.1 }}>{hero.title || hero.name}</h1>
            <p style={{ fontSize: 15, color: "#ccc", lineHeight: 1.6, marginBottom: 24 }}>{(hero.overview || "").slice(0, 180)}...</p>
            <div style={{ display: "flex", gap: 12 }}>
              <button onClick={() => playStream({ detailPath: hero.title || hero.name, subjectId: hero.id, title: hero.title || hero.name, _fromTMDB: true })}
                style={{ background: "#e50914", border: "none", color: "#fff", padding: "12px 28px", borderRadius: 8, fontWeight: 700, fontSize: 15, cursor: "pointer", display: "flex", alignItems: "center", gap: 8 }}>
                ▶ Watch Now
              </button>
              <button onClick={() => setSelected({ detailPath: hero.title || hero.name, subjectId: hero.id, title: hero.title || hero.name, cover: IMG(hero.poster_path), _fromTMDB: true })}
                style={{ background: "rgba(255,255,255,0.15)", border: "1px solid rgba(255,255,255,0.3)", color: "#fff", padding: "12px 28px", borderRadius: 8, fontWeight: 700, fontSize: 15, cursor: "pointer" }}>
                + Download
              </button>
            </div>
          </div>
        </div>
      )}

      <div style={{ padding: "0 40px 40px", marginTop: activeSearch || tab === "Downloads" ? 80 : 0 }}>

        {/* Search Results */}
        {activeSearch && (
          <div>
            <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 20, color: "#aaa" }}>
              Results for <span style={{ color: "#fff" }}>"{query}"</span>
            </h2>
            {searchResults.length === 0 ? (
              <p style={{ color: "#666" }}>No results yet...</p>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 16 }}>
                {searchResults.map((item, i) => (
                  <SearchCard key={i} item={item} onSelect={setSelected} onPlay={playStream} onDownload={startDownload} downloading={downloading} />
                ))}
              </div>
            )}
          </div>
        )}

        {/* Downloads Tab */}
        {!activeSearch && tab === "Downloads" && (
          <div>
            <h2 style={{ fontSize: 24, fontWeight: 800, marginBottom: 24 }}>Downloads</h2>
            {downloads.length === 0 ? (
              <div style={{ textAlign: "center", padding: 80, color: "#444" }}>
                <div style={{ fontSize: 48, marginBottom: 16 }}>📂</div>
                <p>No downloads yet. Search for a movie or show to get started.</p>
              </div>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 16 }}>
                {downloads.map((f, i) => (
                  <div key={i} style={{ background: "rgba(255,255,255,0.05)", borderRadius: 12, padding: 20, display: "flex", alignItems: "center", gap: 16 }}>
                    <div style={{ fontSize: 32 }}>🎬</div>
                    <div style={{ flex: 1, overflow: "hidden" }}>
                      <div style={{ fontWeight: 600, fontSize: 14, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{f.name}</div>
                      <div style={{ color: "#666", fontSize: 12, marginTop: 4 }}>{f.size_mb} MB</div>
                    </div>
                    <button onClick={() => setPlayer({ url: `/api/files/${f.name}`, title: f.name })}
                      style={{ background: "#e50914", border: "none", color: "#fff", padding: "8px 14px", borderRadius: 6, cursor: "pointer", fontSize: 13, fontWeight: 600 }}>▶</button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Content Grid */}
        {!activeSearch && tab !== "Downloads" && (
          <div>
            <h2 style={{ fontSize: 22, fontWeight: 800, margin: "32px 0 20px" }}>{tab}</h2>
            {loading ? (
              <div style={{ display: "flex", justifyContent: "center", padding: 80 }}>
                <div style={{ width: 40, height: 40, border: "3px solid #333", borderTop: "3px solid #e50914", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
              </div>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 16 }}>
                {items.map((item, i) => (
                  <TMDBCard key={i} item={item} onSelect={setSelected} onPlay={playStream} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Download Modal */}
      {selected && (
        <Modal title={selected.title} cover={selected.cover} onClose={() => setSelected(null)}>
          <DownloadForm item={selected} onDownload={(s, e) => { startDownloadResolved(selected, s, e); setSelected(null); }} onPlay={(s, e) => { playStream(selected, s, e); setSelected(null); }} />
        </Modal>
      )}

      {/* Video Player */}
      {player && (
        <div style={{ position: "fixed", inset: 0, background: "#000", zIndex: 200, display: "flex", flexDirection: "column" }}>
          <div style={{ display: "flex", alignItems: "center", padding: "12px 20px", background: "rgba(0,0,0,0.8)" }}>
            <button onClick={() => setPlayer(null)} style={{ background: "none", border: "none", color: "#fff", fontSize: 20, cursor: "pointer", marginRight: 16 }}>✕</button>
            <span style={{ fontWeight: 700 }}>{player.title}</span>
            {player.season && <span style={{ color: "#aaa", marginLeft: 12, fontSize: 14 }}>S{player.season}E{player.episode}</span>}
          </div>
          <video src={player.url} controls autoPlay style={{ flex: 1, width: "100%", background: "#000" }} />
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div style={{ position: "fixed", bottom: 30, right: 30, background: toast.type === "error" ? "#c0392b" : toast.type === "success" ? "#27ae60" : "#2c3e50", color: "#fff", padding: "12px 20px", borderRadius: 10, fontWeight: 600, fontSize: 14, zIndex: 300, boxShadow: "0 4px 20px rgba(0,0,0,0.4)" }}>
          {toast.msg}
        </div>
      )}

      <style>{`
        * { box-sizing: border-box; margin: 0; padding: 0; }
        @keyframes spin { to { transform: rotate(360deg); } }
        ::-webkit-scrollbar { width: 6px; } ::-webkit-scrollbar-track { background: #111; } ::-webkit-scrollbar-thumb { background: #333; border-radius: 3px; }
      `}</style>
    </div>
  );
}

function TMDBCard({ item, onSelect, onPlay }) {
  const [hover, setHover] = useState(false);
  const title = item.title || item.name;
  const year = (item.release_date || item.first_air_date || "").slice(0, 4);
  const poster = IMG(item.poster_path);
  return (
    <div onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{ borderRadius: 10, overflow: "hidden", cursor: "pointer", position: "relative", transition: "transform 0.2s", transform: hover ? "scale(1.05)" : "scale(1)", background: "#111" }}>
      {poster ? <img src={poster} alt={title} style={{ width: "100%", aspectRatio: "2/3", objectFit: "cover", display: "block" }} /> : <div style={{ width: "100%", aspectRatio: "2/3", background: "#222", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 40 }}>🎬</div>}
      {hover && (
        <div style={{ position: "absolute", inset: 0, background: "rgba(0,0,0,0.85)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 10, padding: 12 }}>
          <div style={{ fontWeight: 700, fontSize: 13, textAlign: "center", marginBottom: 4 }}>{title}</div>
          <div style={{ fontSize: 11, color: "#aaa" }}>{year} · ⭐ {item.vote_average?.toFixed(1)}</div>
          <button onClick={() => onPlay({ detailPath: title, subjectId: item.id, title, _fromTMDB: true })}
            style={{ background: "#e50914", border: "none", color: "#fff", padding: "7px 18px", borderRadius: 6, fontWeight: 700, fontSize: 12, cursor: "pointer", width: "100%" }}>▶ Watch</button>
          <button onClick={() => onSelect({ detailPath: title, subjectId: item.id, title, cover: IMG(item.poster_path), _fromTMDB: true })}
            style={{ background: "rgba(255,255,255,0.15)", border: "1px solid rgba(255,255,255,0.3)", color: "#fff", padding: "7px 18px", borderRadius: 6, fontWeight: 700, fontSize: 12, cursor: "pointer", width: "100%" }}>⬇ Download</button>
        </div>
      )}
    </div>
  );
}

function SearchCard({ item, onSelect, onPlay, onDownload, downloading }) {
  const key = `${item.detailPath}-s1e1`;
  const status = downloading[key];
  return (
    <div style={{ borderRadius: 10, overflow: "hidden", background: "#111", cursor: "pointer" }}>
      {item.cover ? <img src={item.cover} alt={item.title} style={{ width: "100%", aspectRatio: "2/3", objectFit: "cover", display: "block" }} /> : <div style={{ width: "100%", aspectRatio: "2/3", background: "#222", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 40 }}>🎬</div>}
      <div style={{ padding: 10 }}>
        <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 4, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{item.title}</div>
        <div style={{ fontSize: 11, color: "#888", marginBottom: 8 }}>{item.year} · {item.genre} {item.hasResource ? "✓" : ""}</div>
        <div style={{ display: "flex", gap: 6 }}>
          <button onClick={() => onPlay(item)} style={{ flex: 1, background: "#e50914", border: "none", color: "#fff", padding: "6px 0", borderRadius: 6, fontSize: 12, fontWeight: 700, cursor: "pointer" }}>▶</button>
          <button onClick={() => onSelect(item)} style={{ flex: 1, background: "rgba(255,255,255,0.1)", border: "1px solid rgba(255,255,255,0.2)", color: "#fff", padding: "6px 0", borderRadius: 6, fontSize: 12, fontWeight: 700, cursor: "pointer" }}>
            {status?.status === "done" ? "✓" : status?.status === "starting" ? "..." : "⬇"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Modal({ title, cover, onClose, children }) {
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.85)", zIndex: 150, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
      <div style={{ background: "#141414", borderRadius: 16, width: "100%", maxWidth: 500, overflow: "hidden", boxShadow: "0 20px 60px rgba(0,0,0,0.8)" }}>
        {cover && <img src={cover} alt={title} style={{ width: "100%", maxHeight: 250, objectFit: "cover" }} />}
        <div style={{ padding: 24 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
            <h2 style={{ fontSize: 20, fontWeight: 800 }}>{title}</h2>
            <button onClick={onClose} style={{ background: "none", border: "none", color: "#aaa", fontSize: 20, cursor: "pointer" }}>✕</button>
          </div>
          {children}
        </div>
      </div>
    </div>
  );
}

function DownloadForm({ item, onDownload, onPlay }) {
  const [season, setSeason] = useState(1);
  const [episode, setEpisode] = useState(1);
  const input = (label, val, set) => (
    <div style={{ flex: 1 }}>
      <label style={{ display: "block", fontSize: 12, color: "#aaa", marginBottom: 6 }}>{label}</label>
      <input type="number" min={1} value={val} onChange={e => set(parseInt(e.target.value) || 1)}
        style={{ width: "100%", background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.15)", borderRadius: 8, padding: "10px 14px", color: "#fff", fontSize: 14, outline: "none" }} />
    </div>
  );
  return (
    <div>
      <div style={{ display: "flex", gap: 12, marginBottom: 20 }}>
        {input("Season", season, setSeason)}
        {input("Episode", episode, setEpisode)}
      </div>
      <div style={{ display: "flex", gap: 10 }}>
        <button onClick={() => onPlay(season, episode)}
          style={{ flex: 1, background: "rgba(255,255,255,0.1)", border: "1px solid rgba(255,255,255,0.2)", color: "#fff", padding: "12px 0", borderRadius: 8, fontWeight: 700, fontSize: 14, cursor: "pointer" }}>▶ Watch</button>
        <button onClick={() => onDownload(season, episode)}
          style={{ flex: 1, background: "#e50914", border: "none", color: "#fff", padding: "12px 0", borderRadius: 8, fontWeight: 700, fontSize: 14, cursor: "pointer" }}>⬇ Download</button>
      </div>
    </div>
  );
}
