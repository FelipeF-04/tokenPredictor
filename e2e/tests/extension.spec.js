const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const { chromium, expect, test: base } = require("@playwright/test");


const ROOT = path.resolve(__dirname, "..", "..");
const EXTENSION_PATH = path.join(ROOT, "extension");
const MOCK_HTML = fs.readFileSync(
  path.join(ROOT, "e2e", "fixtures", "mock_chatgpt.html"),
  "utf8"
);
const BACKEND_BASE_URL = "http://127.0.0.1:5000";


async function setBackendAvailability(online) {
  const response = await fetch(`${BACKEND_BASE_URL}/__e2e__/availability`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ online }),
  });
  if (!response.ok) {
    throw new Error(`Could not update E2E backend availability: ${response.status}`);
  }
}


async function waitForExtension(page) {
  await expect(page.locator("#ai-usage-widget")).toBeAttached();
  await expect(page.locator("#prompt-textarea")).toHaveAttribute(
    "data-ai-usage-attached",
    "true"
  );
}


async function getExtensionStorage(serviceWorker, keys) {
  return serviceWorker.evaluate(
    async (requestedKeys) => chrome.storage.local.get(requestedKeys),
    keys
  );
}


const test = base.extend({
  e2e: async ({}, use, testInfo) => {
    await setBackendAvailability(true);
    const profilePath = fs.mkdtempSync(path.join(os.tmpdir(), "ai-usage-browser-"));
    const context = await chromium.launchPersistentContext(profilePath, {
      channel: "chromium",
      headless: true,
      args: [
        `--disable-extensions-except=${EXTENSION_PATH}`,
        `--load-extension=${EXTENSION_PATH}`,
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-sync",
        "--no-first-run",
      ],
    });

    await context.route("**/*", async (route) => {
      const url = new URL(route.request().url());
      if (url.hostname === "chatgpt.com") {
        await route.fulfill({
          status: 200,
          contentType: "text/html; charset=utf-8",
          headers: { "Cache-Control": "no-store", "X-E2E-Fixture": "local" },
          body: MOCK_HTML,
        });
        return;
      }
      if (
        url.protocol === "chrome-extension:" ||
        url.hostname === "localhost" ||
        url.hostname === "127.0.0.1"
      ) {
        await route.continue();
        return;
      }
      await route.abort("blockedbyclient");
    });

    let serviceWorker = context.serviceWorkers()[0];
    if (!serviceWorker) {
      serviceWorker = await context.waitForEvent("serviceworker");
    }
    const extensionId = new URL(serviceWorker.url()).host;
    const page = context.pages()[0] || (await context.newPage());
    await page.goto(`https://chatgpt.com/e2e/${testInfo.testId}`);
    await waitForExtension(page);

    try {
      await use({ context, extensionId, page, serviceWorker });
    } finally {
      await setBackendAvailability(true).catch(() => {});
      await context.close();
      fs.rmSync(profilePath, { recursive: true, force: true });
    }
  },
});


test("detects the composer, positions the widget, and renders a live estimate", async ({ e2e }) => {
  const { page } = e2e;
  const composer = page.locator("#prompt-textarea");
  const widget = page.locator("#ai-usage-widget");

  await composer.fill("three token prompt");

  await expect(widget).toBeVisible();
  await expect(page.locator("#ai-usage-input")).toHaveText("3");
  await expect(page.locator("#ai-usage-output")).not.toHaveText("-");
  await expect(page.locator("#ai-usage-projected")).not.toHaveText("-");
  await expect(page.locator("#ai-usage-available-row")).toBeVisible();

  const composerBox = await composer.boundingBox();
  const widgetBox = await widget.boundingBox();
  expect(composerBox).not.toBeNull();
  expect(widgetBox).not.toBeNull();
  expect(Math.abs(widgetBox.x - composerBox.x)).toBeLessThan(2);
  const separated =
    widgetBox.y + widgetBox.height <= composerBox.y ||
    widgetBox.y >= composerBox.y + composerBox.height;
  expect(separated).toBe(true);
});


test("records stable conversation totals once across duplicates, reload, popup, and SPA navigation", async ({ e2e }) => {
  const { context, extensionId, page, serviceWorker } = e2e;
  const composer = page.locator("#prompt-textarea");
  const actualTotal = page.locator("#ai-usage-actual");
  const syncStatus = page.locator("#ai-usage-sync-status");

  await composer.fill("Count this user message");
  await expect(page.locator("#ai-usage-input")).toHaveText("4");
  await page.getByRole("button", { name: "Send prompt" }).click();

  await expect(page.locator("[data-message-author-role='user']")).toHaveText(
    "Count this user message"
  );
  await expect(syncStatus).toContainText("Waiting for response to finish");
  await expect(actualTotal).toHaveText("4");
  await expect(page.locator("[data-message-author-role='assistant']")).toHaveText(
    "Stable assistant reply"
  );
  await expect(actualTotal).toHaveText("7", { timeout: 8_000 });
  await expect(syncStatus).toHaveText("Session synced");

  const beforeNavigation = await getExtensionStorage(serviceWorker, [
    "aiUsageActiveSessionId",
  ]);
  const sessionId = beforeNavigation.aiUsageActiveSessionId;
  expect(sessionId).toBeTruthy();

  await page.getByRole("button", { name: "Duplicate last response" }).click();
  await expect(page.locator("[data-message-author-role='assistant']")).toHaveCount(2);
  await page.waitForTimeout(500);
  await expect(actualTotal).toHaveText("7");

  const backendSession = await fetch(`${BACKEND_BASE_URL}/session/${sessionId}`).then(
    (response) => response.json()
  );
  expect(backendSession.total_tokens).toBe(7);

  await page.reload();
  await waitForExtension(page);
  await expect(page.locator("#ai-usage-actual")).toHaveText("7");

  const popup = await context.newPage();
  await popup.goto(`chrome-extension://${extensionId}/popup.html`);
  await expect(popup.locator("#sessionTokens")).toHaveText("7");
  await expect(popup.locator("#syncStatus")).toHaveText("Session synced");
  await popup.close();

  await page.getByRole("button", { name: "Navigate conversation" }).click();
  await expect(page).toHaveURL(/\/e2e\/next-conversation$/);
  await expect(page.locator("#ai-usage-actual")).toHaveText("0");
  const afterNavigation = await getExtensionStorage(serviceWorker, [
    "aiUsageActiveSessionId",
  ]);
  expect(afterNavigation.aiUsageActiveSessionId).not.toBe(sessionId);
});


test("optimizes only on demand, previews the result, and applies it to the composer", async ({ e2e }) => {
  const { page } = e2e;
  const composer = page.locator("#prompt-textarea");
  const optimize = page.getByRole("button", { name: "Optimize context" });

  await composer.fill("Keep this prompt for optimization");
  await expect(page.locator("#ai-usage-input")).toHaveText("5");
  await expect(optimize).toBeEnabled();
  await optimize.click();

  await expect(page.locator("#ai-usage-optimization")).toBeVisible();
  await page.getByRole("button", { name: "Show packed prompt" }).click();
  const preview = page.locator("#ai-usage-preview-body");
  await expect(preview).toBeVisible();
  await expect(preview).toContainText("Keep this prompt for optimization");
  const packedPrompt = await preview.textContent();

  await page.getByRole("button", { name: "Apply optimized prompt" }).click();
  await expect(composer).toHaveText(packedPrompt);
});


test("queues ledger events while unavailable and syncs them after recovery", async ({ e2e }) => {
  const { page, serviceWorker } = e2e;
  const composer = page.locator("#prompt-textarea");
  const actualTotal = page.locator("#ai-usage-actual");
  const syncStatus = page.locator("#ai-usage-sync-status");

  await setBackendAvailability(false);
  await composer.fill("queued offline message");
  await expect(page.locator("#ai-usage-live-status")).toContainText(
    "Live estimate unavailable"
  );
  await page.getByRole("button", { name: "Send prompt" }).click();

  await expect(page.locator("[data-message-author-role='assistant']")).toHaveText(
    "Stable assistant reply"
  );
  await expect(syncStatus).toHaveText("2 events queued", { timeout: 8_000 });
  await expect(actualTotal).toHaveText("0");
  const queued = await getExtensionStorage(serviceWorker, ["aiUsageLedgerQueue"]);
  expect(queued.aiUsageLedgerQueue).toHaveLength(2);

  await setBackendAvailability(true);
  await page.evaluate(() => window.dispatchEvent(new Event("online")));

  await expect(actualTotal).toHaveText("6", { timeout: 8_000 });
  await expect(syncStatus).toHaveText("Session synced");
  const recovered = await getExtensionStorage(serviceWorker, ["aiUsageLedgerQueue"]);
  expect(recovered.aiUsageLedgerQueue).toEqual([]);
});
