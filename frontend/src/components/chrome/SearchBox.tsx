import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import type { GameId, SearchHit } from "../../api/types";
import { useAppStore } from "../../store/useAppStore";

/** Prototype-level search (same in both conditions). Results jump to the canonical row; nothing is copied or moved. */
export function SearchBox({ game }: { game: GameId }) {
  const goToSetting = useAppStore((s) => s.goToSetting);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!q.trim()) {
      setHits([]);
      return;
    }
    const t = window.setTimeout(async () => {
      try {
        setHits(await api.search(game, q.trim()));
        setActive(0);
      } catch {
        setHits([]);
      }
    }, 140);
    return () => window.clearTimeout(t);
  }, [q, game]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const choose = (hit: SearchHit) => {
    goToSetting(game, hit.settingId, "search");
    setOpen(false);
    setQ("");
  };

  return (
    <div className="searchbox" ref={boxRef}>
      <input id="global-search" type="search" placeholder={`Search ${game === "cs2" ? "CS2" : "VALORANT"} settings…`} value={q}
        role="combobox" aria-expanded={open && hits.length > 0} aria-controls="search-results" aria-autocomplete="list"
        aria-label="Search settings"
        onChange={(e) => { setQ(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, hits.length - 1)); }
          if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
          if (e.key === "Enter" && hits[active]) choose(hits[active]);
          if (e.key === "Escape") setOpen(false);
        }} />
      {open && q.trim() ? (
        <ul id="search-results" className="search-results" role="listbox" aria-label="Search results">
          {hits.length === 0 ? <li className="search-empty">No matching settings</li> : null}
          {hits.map((h, i) => (
            <li key={h.settingId} role="option" aria-selected={i === active} className={i === active ? "is-active" : ""}
              onMouseDown={(e) => { e.preventDefault(); choose(h); }} onMouseEnter={() => setActive(i)}>
              <span className="search-label">{h.label}</span>
              <span className="search-path">{h.path}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
