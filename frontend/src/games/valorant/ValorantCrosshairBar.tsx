import { useState } from "react";
import { api } from "../../api/client";
import { broadcastSync } from "../../lib/sync";
import { useAppStore } from "../../store/useAppStore";

export function ValorantCrosshairBar({ activeSubtab }: { activeSubtab: string }) {
  const profiles = useAppStore((s) => s.crosshairProfiles);
  const loadCrosshairProfiles = useAppStore((s) => s.loadCrosshairProfiles);
  const selectProfile = useAppStore((s) => s.selectCrosshairProfile);
  const createProfile = useAppStore((s) => s.createCrosshairProfile);
  const renameProfile = useAppStore((s) => s.renameCrosshairProfile);
  const deleteProfile = useAppStore((s) => s.deleteCrosshairProfile);
  const importCode = useAppStore((s) => s.importCrosshairCode);
  const exportCode = useAppStore((s) => s.exportCrosshairCode);
  const values = useAppStore((s) => s.states.valorant?.values);
  const refreshState = useAppStore((s) => s.refreshState);
  const toast = useAppStore((s) => s.toast);

  const [mode, setMode] = useState<null | "create" | "rename" | "import" | "export">(null);
  const [nameInput, setNameInput] = useState("");
  const [codeInput, setCodeInput] = useState("");
  const [exported, setExported] = useState<{ code: string; simulatedNote: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const active = profiles.find((p) => p.isActive) ?? profiles[0];

  const handleCreate = async () => {
    setError(null);
    const ok = await createProfile(nameInput.trim() || `Profile ${profiles.length + 1}`, true);
    if (ok) {
      setMode(null);
      setNameInput("");
    }
  };

  const handleRename = async () => {
    if (!active || !nameInput.trim()) return;
    await renameProfile(active.id, nameInput.trim());
    setMode(null);
    setNameInput("");
  };

  const handleImport = async () => {
    setError(null);
    const err = await importCode(codeInput.trim(), nameInput.trim() || undefined);
    if (err) {
      setError(err);
    } else {
      setMode(null);
      setCodeInput("");
      setNameInput("");
    }
  };

  const handleExport = async () => {
    if (!active) return;
    const res = await exportCode(active.id);
    if (res) {
      setExported({ code: res.code, simulatedNote: res.simulatedNote });
      setMode("export");
    }
  };

  const handleCopyPrimaryToAds = async () => {
    if (!values) return;
    const keys = [
      "color",
      "custom_color",
      "outlines",
      "outline_opacity",
      "outline_thickness",
      "center_dot",
      "center_dot_opacity",
      "center_dot_thickness",
      "override_firing_offset",
      "show_inner",
      "inner_opacity",
      "inner_length",
      "inner_v_length",
      "inner_thickness",
      "inner_offset",
      "inner_movement_error",
      "inner_firing_error",
      "show_outer",
      "outer_opacity",
      "outer_length",
      "outer_thickness",
      "outer_offset",
      "outer_movement_error",
      "outer_firing_error",
    ];
    const changes = keys
      .map((k) => {
        const src = values[`val.crosshair.primary_${k}`]?.value;
        return src !== undefined ? { settingId: `val.crosshair.ads_${k}`, value: src } : null;
      })
      .filter((x): x is { settingId: string; value: string | number } => Boolean(x));
    if (!changes.length) return;
    try {
      await api.changeBatch("valorant", changes, "Copy Primary Crosshair to ADS");
      await refreshState("valorant");
      await loadCrosshairProfiles();
      broadcastSync({ type: "state_changed", game: "valorant" });
      toast("success", "Copied Primary crosshair settings to Aim Down Sights.");
    } catch (err) {
      toast("error", err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="val-xhair-bar" data-testid="val-crosshair-bar">
      <div className="val-xhair-bar-main">
        <label className="val-xhair-profile-lbl">
          <span>Crosshair Profile</span>
          <select
            aria-label="Crosshair Profile"
            value={active?.id ?? ""}
            onChange={(e) => e.target.value && void selectProfile(e.target.value)}
          >
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <div className="val-xhair-profile-btns">
          <button
            type="button"
            className="val-mini-btn"
            disabled={profiles.length >= 15}
            title={profiles.length >= 15 ? "Maximum 15 profiles reached" : "Create new profile"}
            onClick={() => {
              setError(null);
              setNameInput(`Profile ${profiles.length + 1}`);
              setMode("create");
            }}
          >
            + New ({profiles.length}/15)
          </button>
          <button
            type="button"
            className="val-mini-btn"
            disabled={!active}
            onClick={() => {
              setError(null);
              setNameInput(active?.name ?? "");
              setMode("rename");
            }}
          >
            Rename
          </button>
          <button
            type="button"
            className="val-mini-btn"
            disabled={!active || profiles.length <= 1}
            onClick={() => active && void deleteProfile(active.id)}
          >
            Delete
          </button>
          <button
            type="button"
            className="val-mini-btn"
            disabled={profiles.length >= 15}
            onClick={() => {
              setError(null);
              setCodeInput("");
              setNameInput("");
              setMode("import");
            }}
          >
            Import Code
          </button>
          <button type="button" className="val-mini-btn" disabled={!active} onClick={() => void handleExport()}>
            Export Code
          </button>
          {activeSubtab === "aim_down_sights" ? (
            <button type="button" className="val-mini-btn" onClick={() => void handleCopyPrimaryToAds()}>
              Copy Primary Crosshair
            </button>
          ) : null}
        </div>
      </div>

      {mode === "create" || mode === "rename" ? (
        <div className="val-xhair-modal" role="dialog" aria-label={mode === "create" ? "Create crosshair profile" : "Rename crosshair profile"}>
          <input
            type="text"
            value={nameInput}
            maxLength={40}
            aria-label="Profile name"
            placeholder="Profile name"
            onChange={(e) => setNameInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void (mode === "create" ? handleCreate() : handleRename());
            }}
          />
          <button type="button" className="val-mini-btn is-primary" onClick={() => void (mode === "create" ? handleCreate() : handleRename())}>
            Save
          </button>
          <button type="button" className="val-mini-btn" onClick={() => setMode(null)}>
            Cancel
          </button>
        </div>
      ) : null}

      {mode === "import" ? (
        <div className="val-xhair-modal" role="dialog" aria-label="Import crosshair profile code">
          <input
            type="text"
            value={codeInput}
            aria-label="Crosshair profile code"
            placeholder="0;P;c;5;h;0;0l;4;0o;2;0a;1;0f;0;1b;0"
            onChange={(e) => setCodeInput(e.target.value)}
          />
          <input
            type="text"
            value={nameInput}
            maxLength={40}
            aria-label="Imported profile name"
            placeholder="Profile name (optional)"
            onChange={(e) => setNameInput(e.target.value)}
          />
          <button type="button" className="val-mini-btn is-primary" onClick={() => void handleImport()}>
            Import
          </button>
          <button type="button" className="val-mini-btn" onClick={() => setMode(null)}>
            Cancel
          </button>
          {error ? <p className="val-xhair-err" role="alert">{error}</p> : null}
        </div>
      ) : null}

      {mode === "export" && exported ? (
        <div className="val-xhair-modal" role="dialog" aria-label="Exported crosshair code">
          <input type="text" readOnly value={exported.code} aria-label="Exported crosshair profile code" />
          <button
            type="button"
            className="val-mini-btn is-primary"
            onClick={() => {
              void navigator.clipboard?.writeText(exported.code);
              toast("success", "Crosshair code copied.");
            }}
          >
            Copy
          </button>
          <button type="button" className="val-mini-btn" onClick={() => setMode(null)}>
            Close
          </button>
          <small className="val-xhair-note">{exported.simulatedNote}</small>
        </div>
      ) : null}
    </div>
  );
}
