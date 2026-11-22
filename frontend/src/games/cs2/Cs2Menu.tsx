import { NotSimulated, SettingRow } from "../../components/settings/SettingRow";
import type { GameView } from "../../components/settings/useGameView";
import type { MenuSection } from "../../api/types";
import { useAppStore } from "../../store/useAppStore";
import { CrosshairPreview } from "./CrosshairPreview";

function Section({ sec, view }: { sec: MenuSection; view: GameView }) {
  return (
    <section className="cs2-section" id={`cs2-sec-${sec.id}`} aria-label={sec.label ?? undefined}>
      {sec.label ? <h3 className="cs2-section-title">{sec.label}</h3> : null}
      <div className="cs2-rows">
        {sec.settingIds.map((id) => (view.byId[id] ? <SettingRow key={id} setting={view.byId[id]} view={view} /> : null))}
      </div>
    </section>
  );
}

export function Cs2Menu({ view, onOpenSearch }: { view: GameView; onOpenSearch: () => void }) {
  const nav = useAppStore((s) => s.nav.cs2);
  const navigate = useAppStore((s) => s.navigate);
  const applyPending = useAppStore((s) => s.applyPendingVideo);
  const discardPending = useAppStore((s) => s.discardPendingVideo);
  const catalog = view.catalog!;
  const tab = catalog.menu.find((t) => t.id === nav.tabId) ?? catalog.menu[0];
  const subtab = tab.subtabs.find((s) => s.id === nav.subtabId) ?? tab.subtabs[0];
  const pendingCount = Object.keys(view.pending).length;
  const promoted = catalog.navExtras.find((n) => n.type === "promoted");

  const scrollTo = (secId: string) => {
    document.getElementById(`cs2-sec-${secId}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const sections = tab.subtabMode === "pages" ? subtab.sections : tab.subtabs.flatMap((s) => s.sections);

  return (
    <div className="cs2-menu" data-testid="cs2-menu">
      <nav className="cs2-topnav" role="tablist" aria-label="CS2 settings tabs">
        <button type="button" className="cs2-nav-icon" aria-label="Search settings" title="Search" onClick={onOpenSearch}>
          <svg viewBox="0 0 20 20" aria-hidden><circle cx="8.5" cy="8.5" r="5.5" fill="none" stroke="currentColor" strokeWidth="2" /><line x1="12.5" y1="12.5" x2="17" y2="17" stroke="currentColor" strokeWidth="2" /></svg>
        </button>
        {promoted ? (
          <button type="button" className="cs2-tab is-unsimulated" disabled title={promoted.note ?? "Not simulated"}>{promoted.label}</button>
        ) : null}
        {catalog.menu.map((t) => (
          <button key={t.id} type="button" role="tab" aria-selected={t.id === tab.id} className={`cs2-tab ${t.id === tab.id ? "is-active" : ""}`}
            onClick={() => navigate("cs2", t.id)}>
            {t.label}
          </button>
        ))}
      </nav>
      {tab.subtabMode === "pages" ? (
        <nav className="cs2-subnav cs2-subnav-dark" role="tablist" aria-label={`${tab.label} pages`}>
          {tab.subtabs.map((s) => (
            <button key={s.id} type="button" role="tab" aria-selected={s.id === subtab.id}
              className={`cs2-subtab ${s.id === subtab.id ? "is-active" : ""} ${s.simulated ? "" : "is-unsimulated"}`}
              title={s.simulated ? undefined : s.note ?? "Not simulated"} onClick={() => navigate("cs2", tab.id, s.id)}>
              {s.label}
            </button>
          ))}
        </nav>
      ) : tab.subtabMode === "anchors" ? (
        <nav className="cs2-subnav" aria-label={`${tab.label} sections`}>
          {tab.subtabs.map((s) => (
            <button key={s.id} type="button" className="cs2-subtab" onClick={() => scrollTo(s.sections[0]?.id ?? s.id)}>{s.label}</button>
          ))}
        </nav>
      ) : null}

      <div className={`cs2-body ${tab.id === "video" && subtab.id === "advanced" ? "has-split" : ""}`} role="tabpanel"
        aria-label={`${tab.label}${tab.subtabMode === "pages" ? ` — ${subtab.label}` : ""}`}>
        {!subtab.simulated ? (
          <div className="cs2-col"><NotSimulated note={subtab.note} /></div>
        ) : tab.id === "video" && subtab.id === "advanced" ? (
          <>
            <div className="cs2-video-preview" aria-label="Advanced video preview (not simulated)">
              <div className="cs2-video-preview-scene" aria-hidden />
              <span className="cs2-video-preview-label">Drag here to change view:</span>
              <span className="cs2-video-preview-note">In CS2 this panel renders a live preview of the selected quality. Not simulated here.</span>
            </div>
            <div className="cs2-col cs2-col-scroll">
              {sections.map((sec) => <Section key={sec.id} sec={sec} view={view} />)}
            </div>
          </>
        ) : (
          <div className="cs2-col cs2-col-scroll">
            {tab.preview === "crosshair" ? <CrosshairPreview values={view.values} /> : null}
            {sections.map((sec) => <Section key={sec.id} sec={sec} view={view} />)}
          </div>
        )}
      </div>

      {tab.applyMode === "explicit" ? (
        <div className="cs2-actionbar">
          {pendingCount ? <span className="cs2-pending-note">{pendingCount} unapplied change{pendingCount > 1 ? "s" : ""}</span> : null}
          <button type="button" className="cs2-btn" disabled title="Not simulated: CS2 restores hardware-autodetected values.">Reset defaults</button>
          <button type="button" className="cs2-btn" disabled={!pendingCount} onClick={() => discardPending("cs2")}>Discard Changes</button>
          <button type="button" className="cs2-btn cs2-btn-primary" disabled={!pendingCount} onClick={() => void applyPending("cs2")}>Apply Changes</button>
        </div>
      ) : null}
    </div>
  );
}
