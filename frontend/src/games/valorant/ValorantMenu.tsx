import { NotSimulated, SettingRow } from "../../components/settings/SettingRow";
import type { GameView } from "../../components/settings/useGameView";
import { useAppStore } from "../../store/useAppStore";
import { ValorantCrosshairBar } from "./ValorantCrosshairBar";
import { ValorantCrosshairPreview } from "./ValorantCrosshairPreview";

/** Original line-art ornament in the spirit of the menu's centre motif (no game assets). */
function Ornament() {
  return (
    <svg className="val-ornament" viewBox="0 0 200 260" aria-hidden>
      <g fill="none" stroke="currentColor" strokeWidth="1">
        <line x1="100" y1="0" x2="100" y2="120" />
        <line x1="96" y1="0" x2="96" y2="96" />
        <line x1="104" y1="0" x2="104" y2="96" />
        <path d="M60 70 L88 98 L88 112 L100 124 L112 112 L112 98 L140 70" />
        <circle cx="100" cy="130" r="3" />
        <rect x="70" y="150" width="60" height="60" transform="rotate(45 100 180)" />
        <rect x="84" y="164" width="32" height="32" transform="rotate(45 100 180)" />
      </g>
    </svg>
  );
}

export function ValorantMenu({ view }: { view: GameView }) {
  const nav = useAppStore((s) => s.nav.valorant);
  const navigate = useAppStore((s) => s.navigate);
  const catalog = view.catalog!;
  const tab = catalog.menu.find((t) => t.id === nav.tabId) ?? catalog.menu[0];
  const subtab = tab.subtabs.find((s) => s.id === nav.subtabId) ?? tab.subtabs[0];
  const isKeybindPage = subtab.sections.some((sec) => sec.settingIds.some((id) => view.byId[id]?.controlType === "keybind"));
  const advOn = String(view.values["val.crosshair.use_advanced_options"] ?? "off") === "on";
  const advLockedSubtab = tab.id === "crosshair" && (subtab.id === "aim_down_sights" || subtab.id === "sniper_scope") && !advOn;

  return (
    <div className="val-menu" data-testid="valorant-menu">
      <div className="val-backdrop" aria-hidden>
        <Ornament />
      </div>
      <nav className="val-tabs" role="tablist" aria-label="VALORANT settings tabs">
        {catalog.menu.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={t.id === tab.id}
            className={`val-tab ${t.id === tab.id ? "is-active" : ""}`}
            onClick={() => navigate("valorant", t.id)}
          >
            {t.label}
            <span className="val-tab-diamond" aria-hidden />
          </button>
        ))}
      </nav>
      <div className="val-tabs-rule" aria-hidden />
      {tab.subtabMode === "pages" ? (
        <nav className="val-subtabs" role="tablist" aria-label={`${tab.label} sub-tabs`}>
          {tab.subtabs.map((s) => (
            <button
              key={s.id}
              type="button"
              role="tab"
              aria-selected={s.id === subtab.id}
              className={`val-subtab ${s.id === subtab.id ? "is-active" : ""} ${s.simulated ? "" : "is-unsimulated"}`}
              title={s.simulated ? undefined : "Not simulated in this prototype"}
              onClick={() => navigate("valorant", tab.id, s.id)}
            >
              {s.label}
            </button>
          ))}
        </nav>
      ) : null}
      <div className="val-content" role="tabpanel" aria-label={`${tab.label}${tab.subtabMode === "pages" ? ` — ${subtab.label}` : ""}`}>
        <div className="val-column">
          {!tab.simulated || !subtab.simulated ? (
            <NotSimulated note={subtab.note ?? tab.note} />
          ) : (
            <>
              {tab.id === "crosshair" ? (
                <>
                  <ValorantCrosshairBar activeSubtab={subtab.id} />
                  <ValorantCrosshairPreview
                    values={view.values}
                    mode={subtab.id === "aim_down_sights" ? "ads" : subtab.id === "sniper_scope" ? "sniper" : "primary"}
                  />
                  {advLockedSubtab ? (
                    <div className="val-adv-notice" role="note">
                      <span>
                        <strong>Use Advanced Options</strong> is currently Off — controls below are disabled until you turn it On under{" "}
                        <button type="button" className="link" onClick={() => navigate("valorant", "crosshair", "general")}>
                          Crosshair → General
                        </button>
                        .
                      </span>
                    </div>
                  ) : null}
                </>
              ) : null}
              {subtab.sections.map((sec) => (
                <section key={sec.id} className="val-section" aria-label={sec.label ?? undefined}>
                  {sec.label ? (
                    <h3 className="val-section-title">
                      {sec.label}
                      {sec.pathVerification === "inferred" ? (
                        <span
                          className="section-note"
                          title="Patch 12.07 (14 Apr 2026) split General > Other into User Interface, Content Filtering and Network. Riot did not publish which setting moved where, so this placement is inferred."
                        >
                          ⓘ
                        </span>
                      ) : null}
                    </h3>
                  ) : (
                    <div className="val-section-gap" />
                  )}
                  {isKeybindPage ? (
                    <div className="val-keyhead" aria-hidden>
                      <span />
                      <span>Primary Key</span>
                      <span>Alternate Key</span>
                    </div>
                  ) : null}
                  <div className="val-rows">
                    {sec.settingIds.map((id) => (view.byId[id] ? <SettingRow key={id} setting={view.byId[id]} view={view} /> : null))}
                  </div>
                </section>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
