import { SettingRow } from "../../components/settings/SettingRow";
import type { GameView } from "../../components/settings/useGameView";
import { useAppStore } from "../../store/useAppStore";

const PROMOTED_IDS = [
  "cs2.crosshair.xhair_style",
  "cs2.crosshair.xhair_outline",
  "cs2.crosshair.xhair_spread_limit",
  "cs2.kbmouse.silent_reload_mode",
  "cs2.game.glow_rarity",
  "cs2.video.hud_edge_x",
  "cs2.video.hud_edge_y",
];

export function PromotedTab({ view }: { view: GameView }) {
  const goToSetting = useAppStore((s) => s.goToSetting);
  const items = PROMOTED_IDS.map((id) => view.byId[id]).filter(Boolean);

  return (
    <div className="cs2-promoted" data-testid="cs2-promoted-tab">
      <div className="cs2-promoted-banner" role="note">
        <strong>New &amp; Notable CS2 Settings (Simulated)</strong>
        <p className="muted">
          Recent build 2000948 additions (Crosshair/Scopes update, Silent Reload Mode, Weapon Rarity Glow, and HUD Edge Positions) mapped directly to verified catalogue settings.
        </p>
      </div>
      <div className="cs2-rows">
        {items.map((s) =>
          s ? (
            <div key={s.id} className="cs2-promoted-row-wrap">
              <SettingRow setting={s} view={view} />
              <div className="cs2-promoted-meta">
                <span>{s.canonicalPath}</span>
                <button type="button" className="link" onClick={() => goToSetting("cs2", s.id, "search")}>
                  Open in {s.category}
                </button>
              </div>
            </div>
          ) : null,
        )}
      </div>
    </div>
  );
}
