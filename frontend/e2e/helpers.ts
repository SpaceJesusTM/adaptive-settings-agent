import type { Page } from "@playwright/test";

export async function api<T = unknown>(page: Page, path: string, method = "GET", body?: unknown): Promise<T> {
  return page.evaluate(
    async ([p, m, b]) => {
      const res = await fetch(p as string, { method: m as string, headers: { "Content-Type": "application/json" }, body: b ? JSON.stringify(b) : undefined });
      return res.json();
    },
    [path, method, body] as const,
  ) as Promise<T>;
}

export async function setup(page: Page, opts: { scenario?: string; condition?: "baseline" | "adaptive"; game?: "valorant" | "cs2"; aiMode?: "local" | "fallback" }) {
  await page.goto("/");
  await page.waitForSelector(".studybar");
  await api(page, "/api/admin/reset", "POST", { scenario: opts.scenario ?? "default", mode: "full" });
  await api(page, "/api/session", "PUT", {
    condition: opts.condition ?? "baseline",
    selectedGame: opts.game ?? "valorant",
    aiMode: opts.aiMode ?? "fallback",
  });
  await page.reload();
  await page.waitForSelector(".studybar");
  await page.waitForSelector("[data-setting-id]");
}

export async function value(page: Page, game: string, settingId: string): Promise<unknown> {
  const state = await api<{ values: Record<string, { value: unknown }> }>(page, `/api/games/${game}/state`);
  return state.values[settingId]?.value;
}

export async function openTab(page: Page, tab: string, subtab?: string) {
  await page.getByRole("tab", { name: new RegExp(`^${tab}$`, "i") }).first().click();
  if (subtab) await page.getByRole("tab", { name: new RegExp(`^${subtab}$`, "i") }).first().click();
}

export function row(page: Page, settingId: string) {
  return page.locator(`[data-setting-id="${settingId}"]`);
}

export async function rowOrder(page: Page): Promise<string[]> {
  return page.locator("[data-setting-id]").evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.settingId ?? ""));
}

export async function askAssistant(page: Page, text: string) {
  await page.getByLabel("Message the assistant").fill(text);
  await page.getByRole("button", { name: "Send" }).click();
  await page.locator(".msg-assistant").last().waitFor({ timeout: 150_000 });
}
