import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { GameId, Setting, Value } from "../../api/types";
import { keyName, mouseName, wheelName } from "../../lib/keys";

interface ControlProps {
  game: GameId;
  setting: Setting;
  value: Value | undefined;
  disabled?: boolean;
  onChange: (value: Value) => void;
  labelId: string;
}

export function Segmented({ setting, value, disabled, onChange, labelId }: ControlProps) {
  const options = setting.validOptions ?? [];
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const idx = Math.max(0, options.findIndex((o) => o.value === String(value)));
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (disabled) return;
    const dir = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!dir) return;
    e.preventDefault();
    const next = (idx + dir + options.length) % options.length;
    onChange(options[next].value);
    refs.current[next]?.focus();
  };
  return (
    <div className="ctl-segmented" role="radiogroup" aria-labelledby={labelId} aria-disabled={disabled || undefined} onKeyDown={onKey}
      style={{ gridTemplateColumns: `repeat(${options.length}, 1fr)` }}>
      {options.map((o, i) => {
        const selected = o.value === String(value);
        return (
          <button key={o.value} ref={(el) => { refs.current[i] = el; }} type="button" role="radio" aria-checked={selected}
            tabIndex={selected ? 0 : -1} disabled={disabled} className={`seg ${selected ? "is-selected" : ""}`}
            onClick={() => !selected && onChange(o.value)}>
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export function Dropdown({ setting, value, disabled, onChange, labelId }: ControlProps) {
  const options = setting.validOptions ?? [];
  const isPreset = setting.controlType === "preset";
  return (
    <div className="ctl-dropdown">
      <select aria-labelledby={labelId} value={String(value ?? "")} disabled={disabled}
        onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          <option key={o.value} value={o.value} disabled={isPreset && o.value === "custom"}>
            {o.label}
          </option>
        ))}
      </select>
      <span className="ctl-dropdown-arrow" aria-hidden>▾</span>
    </div>
  );
}

function toDisplayNumber(setting: Setting, v: number): number {
  return setting.display === "percent" ? Math.round(v * 100) : v;
}

export function SliderControl({ setting, value, disabled, onChange, labelId }: ControlProps) {
  const percent = setting.display === "percent";
  const min = percent ? 0 : setting.min ?? 0;
  const max = percent ? Math.round((setting.max ?? 1) * 100) : setting.max ?? 100;
  const step = percent ? 1 : setting.step ?? 1;
  const dec = percent ? 0 : setting.precision ?? 2;
  const committed = toDisplayNumber(setting, Number(value ?? min));
  const [local, setLocal] = useState<number>(committed);
  const [text, setText] = useState<string>(committed.toFixed(dec));
  const dirty = useRef(false);

  useEffect(() => {
    if (!dirty.current) {
      setLocal(committed);
      setText(committed.toFixed(dec));
    }
  }, [committed, dec]);

  const commit = (n: number) => {
    dirty.current = false;
    if (Number.isNaN(n)) {
      setText(committed.toFixed(dec));
      return;
    }
    const clamped = Math.min(max, Math.max(min, n));
    const actual = percent ? clamped / 100 : clamped;
    setLocal(clamped);
    setText(clamped.toFixed(dec));
    if (Math.abs(clamped - committed) > 1e-9) onChange(Number(actual.toFixed(percent ? 2 : Math.max(dec, 3))));
  };

  return (
    <div className="ctl-slider" data-unverified={!setting.rangeVerified || undefined}>
      <input className="ctl-slider-value" type="text" inputMode="decimal" aria-labelledby={labelId}
        aria-label={`${setting.exactLabel} value`} value={text} disabled={disabled}
        onChange={(e) => { dirty.current = true; setText(e.target.value); }}
        onBlur={() => commit(Number(text))}
        onKeyDown={(e) => { if (e.key === "Enter") commit(Number(text)); }} />
      <input className="ctl-slider-range" type="range" min={min} max={max} step={step} value={local} disabled={disabled}
        aria-labelledby={labelId}
        style={{ ["--fill" as string]: `${((local - min) / (max - min || 1)) * 100}%` }}
        onChange={(e) => { dirty.current = true; setLocal(Number(e.target.value)); setText(Number(e.target.value).toFixed(dec)); }}
        onPointerUp={(e) => commit(Number((e.target as HTMLInputElement).value))}
        onKeyUp={(e) => commit(Number((e.target as HTMLInputElement).value))}
        onBlur={(e) => dirty.current && commit(Number(e.target.value))} />
      {percent ? <span className="ctl-slider-suffix">%</span> : setting.unit && setting.unit !== "%" ? <span className="ctl-slider-suffix">{setting.unit}</span> : null}
      {!setting.rangeVerified && (
        <span className="ctl-unverified" title="The game's exact range for this slider is not documented; these bounds are prototype values.">≈</span>
      )}
    </div>
  );
}

export function KeybindControl({ game, setting, value, disabled, onChange, labelId }: ControlProps) {
  const [capturing, setCapturing] = useState(false);
  const btn = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!capturing) return;
    const finish = (name: string | null) => {
      setCapturing(false);
      if (name !== null) onChange(name);
      btn.current?.focus();
    };
    const onKey = (e: globalThis.KeyboardEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (e.code === "Escape" && !e.shiftKey) return finish(null); // Esc cancels (Shift+Esc binds Escape)
      const name = keyName(game, e.code === "Escape" ? "Escape" : e.code);
      finish(name);
    };
    const onMouse = (e: MouseEvent) => {
      if (e.target === btn.current && e.button === 0) return;
      e.preventDefault();
      finish(mouseName(game, e.button));
    };
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      finish(wheelName(game, e.deltaY));
    };
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("mousedown", onMouse, true);
    window.addEventListener("wheel", onWheel, { capture: true, passive: false });
    return () => {
      window.removeEventListener("keydown", onKey, true);
      window.removeEventListener("mousedown", onMouse, true);
      window.removeEventListener("wheel", onWheel, true);
    };
  }, [capturing, game, onChange]);

  return (
    <div className="ctl-keybind">
      <button ref={btn} type="button" className={`key-cell ${capturing ? "is-capturing" : ""}`} disabled={disabled}
        aria-labelledby={labelId} aria-describedby={capturing ? `${labelId}-hint` : undefined}
        onClick={() => setCapturing(true)}>
        {capturing ? "Press a key…" : value ? String(value) : "–"}
      </button>
      <span className="key-cell key-cell-alt" title="Alternate bindings are not simulated">–</span>
      {capturing && <span id={`${labelId}-hint`} className="sr-only">Press a key or mouse button. Escape cancels.</span>}
      {!capturing && value ? (
        <button type="button" className="key-clear" title={`Unbind ${setting.exactLabel}`} aria-label={`Unbind ${setting.exactLabel}`}
          disabled={disabled} onClick={() => onChange("")}>×</button>
      ) : (
        <span className="key-clear" aria-hidden />
      )}
    </div>
  );
}

export function ColorControl({ setting, value, disabled, onChange, labelId }: ControlProps) {
  const committed = /^#[0-9a-f]{6}$/i.test(String(value ?? "")) ? String(value).toUpperCase() : "#FFFFFF";
  const [hex, setHex] = useState(committed);

  useEffect(() => {
    setHex(committed);
  }, [committed]);

  const commitHex = (raw: string) => {
    let cleaned = raw.trim().toUpperCase();
    if (!cleaned.startsWith("#")) cleaned = `#${cleaned}`;
    if (/^#[0-9A-F]{3}$/.test(cleaned)) {
      cleaned = "#" + cleaned.slice(1).split("").map((c) => c + c).join("");
    }
    if (/^#[0-9A-F]{6}$/.test(cleaned)) {
      setHex(cleaned);
      if (cleaned !== committed) onChange(cleaned);
    } else {
      setHex(committed);
    }
  };

  return (
    <div className="ctl-color">
      <input
        type="color"
        className="ctl-color-picker"
        aria-labelledby={labelId}
        aria-label={`${setting.exactLabel} color picker`}
        value={committed}
        disabled={disabled}
        onChange={(e) => {
          const v = e.target.value.toUpperCase();
          setHex(v);
          onChange(v);
        }}
      />
      <input
        type="text"
        className="ctl-color-hex"
        aria-label={`${setting.exactLabel} hex value`}
        value={hex}
        maxLength={7}
        disabled={disabled}
        onChange={(e) => setHex(e.target.value)}
        onBlur={() => commitHex(hex)}
        onKeyDown={(e) => {
          if (e.key === "Enter") commitHex(hex);
        }}
      />
    </div>
  );
}

export function SettingControl(props: ControlProps) {
  switch (props.setting.controlType) {
    case "segmented":
      return <Segmented {...props} />;
    case "dropdown":
    case "preset":
      return <Dropdown {...props} />;
    case "slider":
      return <SliderControl {...props} />;
    case "keybind":
      return <KeybindControl {...props} />;
    case "color":
      return <ColorControl {...props} />;
    default:
      return null;
  }
}
