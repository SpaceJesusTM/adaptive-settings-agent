// Maps browser key/mouse events to each game's key names (must match backend app/domain/values.py).
import type { GameId } from "../api/types";

const PUNCT: Record<string, string> = {
  Backquote: "`", Minus: "-", Equal: "=", BracketLeft: "[", BracketRight: "]", Backslash: "\\",
  Semicolon: ";", Quote: "'", Comma: ",", Period: ".", Slash: "/",
};

const CS2: Record<string, string> = {
  Space: "SPACE", ShiftLeft: "SHIFT", ShiftRight: "RSHIFT", ControlLeft: "CTRL", ControlRight: "RCTRL",
  AltLeft: "ALT", AltRight: "RALT", Tab: "TAB", Escape: "ESCAPE", Enter: "ENTER", Backspace: "BACKSPACE",
  CapsLock: "CAPSLOCK", Insert: "INS", Delete: "DEL", Home: "HOME", End: "END", PageUp: "PGUP", PageDown: "PGDN",
  ArrowUp: "UPARROW", ArrowDown: "DOWNARROW", ArrowLeft: "LEFTARROW", ArrowRight: "RIGHTARROW", NumpadEnter: "KP_ENTER",
};

const VAL: Record<string, string> = {
  Space: "Space Bar", ShiftLeft: "Left Shift", ShiftRight: "Right Shift", ControlLeft: "Left Ctrl", ControlRight: "Right Ctrl",
  AltLeft: "Left Alt", AltRight: "Right Alt", Tab: "Tab", Escape: "Escape", Enter: "Enter", Backspace: "Backspace",
  CapsLock: "Caps Lock", Insert: "Insert", Delete: "Delete", Home: "Home", End: "End", PageUp: "Page Up", PageDown: "Page Down",
  ArrowUp: "Up", ArrowDown: "Down", ArrowLeft: "Left", ArrowRight: "Right",
};

export function keyName(game: GameId, code: string): string | null {
  if (/^Key[A-Z]$/.test(code)) return code.slice(3);
  if (/^Digit[0-9]$/.test(code)) return code.slice(5);
  if (/^F([1-9]|1[0-2])$/.test(code)) return code;
  if (PUNCT[code]) return PUNCT[code];
  const num = /^Numpad([0-9])$/.exec(code);
  if (num) return game === "cs2" ? `KP_${num[1]}` : `Num ${num[1]}`;
  return (game === "cs2" ? CS2 : VAL)[code] ?? null;
}

export function mouseName(game: GameId, button: number): string | null {
  const cs2 = ["MOUSE1", "MOUSE3", "MOUSE2", "MOUSE4", "MOUSE5"];
  const val = ["Left Mouse Button", "Middle Mouse Button", "Right Mouse Button", "Thumb Mouse Button", "Thumb Mouse Button 2"];
  return (game === "cs2" ? cs2 : val)[button] ?? null;
}

export function wheelName(game: GameId, deltaY: number): string {
  if (game === "cs2") return deltaY < 0 ? "MWHEELUP" : "MWHEELDOWN";
  return deltaY < 0 ? "Mouse Wheel Up" : "Mouse Wheel Down";
}
