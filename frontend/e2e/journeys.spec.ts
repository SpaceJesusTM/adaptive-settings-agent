import { expect, test } from "@playwright/test";
import { api, askAssistant, openTab, row, rowOrder, setup, value } from "./helpers";

test.describe("A. Browse and change manually", () => {
  test("baseline: change a VALORANT setting, see history, undo, survive reload", async ({ page }) => {
    await setup(page, { condition: "baseline" });
    await expect(page.locator(".assistant")).toHaveCount(0);
    await expect(page.locator(".row-tools")).toHaveCount(0);
    await openTab(page, "Video", "Graphics Quality");
    const bloom = row(page, "val.video.bloom");
    await bloom.getByRole("radio", { name: "Off" }).click();
    await expect(page.locator(".toast").last()).toContainText("Bloom: On → Off");
    expect(await value(page, "valorant", "val.video.bloom")).toBe("off");

    await page.reload();
    await openTab(page, "Video", "Graphics Quality");
    await expect(row(page, "val.video.bloom").getByRole("radio", { name: "Off" })).toHaveAttribute("aria-checked", "true");

    await page.getByRole("button", { name: "History" }).click();
    const item = page.locator(".history-item").first();
    await expect(item).toContainText("Manual change");
    await expect(item).toContainText("On → Off");
    await item.getByRole("button", { name: "Undo" }).click();
    await expect.poll(() => value(page, "valorant", "val.video.bloom")).toBe("on");
  });

  test("search takes the user to the canonical row and highlights it", async ({ page }) => {
    await setup(page, { condition: "baseline" });
    await page.getByLabel("Search settings").fill("anti-aliasing");
    await page.getByRole("option", { name: /Anti-Aliasing/ }).first().click();
    const r = row(page, "val.video.anti_aliasing");
    await expect(r).toBeVisible();
    await expect(r).toHaveClass(/is-highlighted/);
    await expect(page.getByRole("tab", { name: /^graphics quality$/i })).toHaveAttribute("aria-selected", "true");
  });

  test("CS2 video edits stay pending until Apply Changes", async ({ page }) => {
    await setup(page, { condition: "baseline", game: "cs2" });
    await openTab(page, "Video", "Advanced Video");
    await row(page, "cs2.video.vsync").getByRole("combobox").selectOption({ label: "Disabled" });
    await expect(page.locator(".cs2-pending-note")).toContainText("1 unapplied change");
    expect(await value(page, "cs2", "cs2.video.vsync")).toBe("1");
    await page.getByRole("button", { name: "Apply Changes" }).click();
    await expect.poll(() => value(page, "cs2", "cs2.video.vsync")).toBe("0");
    await expect(page.locator(".cs2-pending-note")).toHaveCount(0);
  });

  test("selecting a CS2 video preset changes its member settings together", async ({ page }) => {
    await setup(page, { condition: "baseline", game: "cs2" });
    await openTab(page, "Video", "Advanced Video");
    await row(page, "cs2.video.video_preset").getByRole("combobox").selectOption({ label: "Low" });
    await expect(row(page, "cs2.video.msaa").getByRole("combobox")).toHaveValue("0");
    await page.getByRole("button", { name: "Apply Changes" }).click();
    await expect.poll(() => value(page, "cs2", "cs2.video.global_shadow_quality")).toBe("0");
  });
});

test.describe("Condition parity", () => {
  for (const [game, tab, sub] of [["valorant", "Video", "Graphics Quality"], ["cs2", "Video", "Advanced Video"]] as const) {
    test(`${game}: identical canonical rows in both conditions`, async ({ page }) => {
      await setup(page, { condition: "baseline", game });
      await openTab(page, tab, sub);
      const baseline = await rowOrder(page);
      await page.getByRole("button", { name: "B · Adaptive" }).click();
      await expect(page.locator(".assistant")).toBeVisible();
      await openTab(page, tab, sub);
      expect(await rowOrder(page)).toEqual(baseline);
    });
  }
});

test.describe("B/D. Goal-driven assistance with explicit approval (offline fallback mode)", () => {
  test("suggestions do nothing until staged and applied; applied changes are undoable", async ({ page }) => {
    await setup(page, { condition: "adaptive", aiMode: "fallback" });
    const before = await api<{ values: Record<string, { value: unknown }> }>(page, "/api/games/valorant/state");
    await askAssistant(page, "I'm getting frame drops in VALORANT and want smoother competitive play. What should I change?");
    const msg = page.locator(".msg-assistant").last();
    await expect(msg.locator(".msg-prov")).toContainText("Offline fallback — rule-based, not AI-generated");
    const cards = msg.locator(".rec-card");
    expect(await cards.count()).toBeGreaterThan(0);
    const firstLabel = (await cards.first().locator(".rec-title strong").textContent()) ?? "";

    await cards.first().getByRole("button", { name: "Show in settings" }).click();
    await expect(page.locator(".setting-row.is-highlighted")).toContainText(firstLabel);

    const stageAll = msg.getByRole("button", { name: /Stage all/ });
    if (await stageAll.count()) await stageAll.click();
    else await cards.first().getByRole("button", { name: "Stage for review" }).click();
    await expect(page.locator(".tray.is-open .tray-item").first()).toBeVisible();
    const afterStage = await api<{ values: Record<string, { value: unknown }> }>(page, "/api/games/valorant/state");
    expect(afterStage.values).toEqual(before.values); // invariant: staging is not applying

    await page.getByRole("button", { name: /^Apply selected changes/ }).click();
    await expect(page.locator(".toast").last()).toContainText("Applied");
    await page.getByRole("button", { name: "History" }).click();
    const item = page.locator(".history-item").first();
    await expect(item).toContainText("Fallback suggestion · user applied");
    await item.getByRole("button", { name: "Undo" }).click();
    await expect.poll(async () => {
      const now = await api<{ values: Record<string, { value: unknown }> }>(page, "/api/games/valorant/state");
      return Object.keys(before.values).every((k) => now.values[k]?.value === before.values[k].value);
    }).toBe(true);
  });

  test("a locked setting is never suggested and cannot be applied through a proposal", async ({ page }) => {
    await setup(page, { condition: "adaptive", aiMode: "fallback" });
    await openTab(page, "Video", "Graphics Quality");
    const vsync = row(page, "val.video.vsync");
    await vsync.hover();
    await vsync.getByRole("button", { name: /Lock VSync/ }).click();
    await expect(vsync.getByTitle(/Locked from AI changes/)).toBeVisible();
    await askAssistant(page, "I want lower input latency.");
    await expect(page.locator(".msg-assistant").last().locator(".rec-card", { hasText: "VSync" })).toHaveCount(0);
    const prop = await api<{ status: string; items: { status: string }[] }>(page, "/api/proposals", "POST",
      { game: "valorant", source: "ai", items: [{ settingId: "val.video.vsync", proposedValue: "off" }] });
    expect(prop.items[0].status).toBe("blocked");
    expect(await value(page, "valorant", "val.video.vsync")).toBe("on");
  });

  test("preference correction is only saved after confirmation, with the chosen scope", async ({ page }) => {
    await setup(page, { condition: "adaptive", aiMode: "fallback" });
    await askAssistant(page, "I prefer visibility over visual effects, just for today.");
    const suggestion = page.locator(".pref-suggest").last();
    await expect(suggestion).toBeVisible();
    let profile = await api<{ preferences: unknown[] }>(page, "/api/profile");
    expect(profile.preferences).toHaveLength(0);
    await suggestion.getByRole("button", { name: "Save preference" }).click();
    await expect.poll(async () => (await api<{ preferences: { scope: string }[] }>(page, "/api/profile")).preferences.length).toBe(1);
    profile = await api<{ preferences: { scope: string }[] }>(page, "/api/profile");
    expect((profile.preferences[0] as { scope: string }).scope).toBe("session");
  });
});

test.describe("C/E. Relevant now and cross-game transfer", () => {
  test("new CS2 player with VALORANT history gets authentic CS2 suggestions without copying values", async ({ page }) => {
    await setup(page, { scenario: "valorant_history_new_cs2", condition: "adaptive", game: "cs2", aiMode: "fallback" });
    const before = await api<{ values: Record<string, { value: unknown }> }>(page, "/api/games/cs2/state");
    const rn = page.locator(".rn");
    await expect(rn.locator(".rec-card").first()).toBeVisible();
    await expect(rn.locator(".rec-basis").first()).toContainText("in VALORANT");
    const labels = await rn.locator(".rec-title strong").allTextContents();
    expect(labels.some((l) => /Reflex|V-Sync|Boost Player Contrast|Dynamic Shadows/.test(l))).toBeTruthy();
    expect(labels).not.toContain("Mouse Sensitivity");
    const after = await api<{ values: Record<string, { value: unknown }> }>(page, "/api/games/cs2/state");
    expect(after.values).toEqual(before.values);
  });

  test("Relevant now holds its cards on reload and does not reinsert a dismissed card", async ({ page }) => {
    await setup(page, { scenario: "valorant_history_new_cs2", condition: "adaptive", game: "cs2", aiMode: "fallback" });
    const titles = () => page.locator(".rn .rec-title strong").allTextContents();
    await page.locator(".rn .rec-card").first().waitFor();
    const first = await titles();
    expect(first.length).toBeGreaterThan(0);
    await page.reload();
    await page.waitForSelector(".rn .rec-card");
    expect(await titles()).toEqual(first);
    await page.locator(".rn .rec-card").first().getByRole("button", { name: "Dismiss" }).click();
    await page.getByRole("button", { name: "Not relevant to me" }).click();
    await expect(page.locator(".rn .rec-card").first()).toHaveClass(/state-dismissed/);
    await api(page, "/api/games/cs2/relevant-now/refresh", "POST");
    await page.reload();
    await page.waitForSelector(".rn");
    expect(await titles()).not.toContain(first[0]);
  });

  test("simulated context event is labelled and populates suggestions", async ({ page }) => {
    await setup(page, { condition: "adaptive", aiMode: "fallback" });
    await page.getByRole("button", { name: "Study controls" }).click();
    await page.getByRole("button", { name: /Frame-rate dips/ }).click();
    await expect(page.locator(".rn-context")).toContainText("Simulated event");
    await expect(page.locator(".rn .rec-card").first()).toBeVisible();
  });
});
