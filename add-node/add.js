"use strict";

const puppeteer = require("puppeteer");
const fs = require("fs");
const path = require("path");

// ─────────────────────────────────────────────
//  CONFIGURATION
// ─────────────────────────────────────────────
const DELAY_BETWEEN_LINKS_MS = 30 * 1000; // 30s between each node link

const CHROMIUM_PATH = puppeteer.executablePath();

const DIR = __dirname;
const INPUT_FILE = path.join(DIR, "input-links.txt");
const COOKIE_FILE = path.join(DIR, "cookies", "account1.json");
const RESULT_FILE = path.join(DIR, "result.txt");

const EARNAPP_DASHBOARD = "https://earnapp.com";

console.log(`Chromium: ${CHROMIUM_PATH}`);

// ─────────────────────────────────────────────
//  HELPERS
// ─────────────────────────────────────────────
function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Read earnapp links — one per line, ignore comments and empty lines */
function readLinks() {
  const content = fs.readFileSync(INPUT_FILE, "utf-8");
  return content
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith("#"))
    .map((l) => {
      // Strip timestamp prefix if present: "03/10/26 22:10:08 https://..."
      const match = l.match(/(https:\/\/earnapp\.com\/r\/\S+)/);
      return match ? match[1] : l;
    });
}

function loadCookies() {
  const raw = fs.readFileSync(COOKIE_FILE, "utf-8");
  return JSON.parse(raw);
}

/** Normalize sameSite value to Puppeteer-accepted format */
function normalizeSameSite(value) {
  if (!value) return undefined;
  const map = { strict: "Strict", lax: "Lax", no_restriction: "None" };
  return map[value.toLowerCase()] ?? undefined;
}

/** Set cookies and navigate to earnapp dashboard, verify login */
async function loginWithCookies(page, cookies) {
  await page.goto(EARNAPP_DASHBOARD, { waitUntil: "networkidle2", timeout: 30000 });

  const mapped = cookies.map((c) => ({
    name: c.name,
    value: c.value,
    domain: c.domain,
    path: c.path,
    secure: c.secure,
    httpOnly: c.httpOnly,
    sameSite: normalizeSameSite(c.sameSite),
    ...(c.expirationDate ? { expires: Math.floor(c.expirationDate) } : {}),
  }));

  await page.setCookie(...mapped);
  await page.goto(EARNAPP_DASHBOARD, { waitUntil: "networkidle2", timeout: 30000 });

  try {
    await page.waitForSelector('a.btn_sign_in[role="button"]', { timeout: 10000 });
    console.log("Login verified — Dashboard button found.");
  } catch {
    throw new Error("Login failed — Dashboard button not found. Check cookie JSON.");
  }
}

/**
 * Visit an earnapp node link to add/register the node to the logged-in account.
 * @returns {{ success: boolean, reason: string }}
 */
async function addNode(page, earnappLink) {
  await page.goto(earnappLink, { waitUntil: "networkidle2", timeout: 30000 });

  try {
    await Promise.race([
      page.waitForSelector('a[href="/dashboard/me/passive-income"]', { timeout: 20000 }),
      page.waitForFunction(
        () => document.body.innerText.includes("already linked"),
        { timeout: 20000 }
      ),
    ]);
  } catch {
    return { success: false, reason: "Link page: confirmation element not found" };
  }

  const alreadyLinked = await page.evaluate(() =>
    document.body.innerText.includes("already linked")
  );

  if (alreadyLinked) {
    return { success: true, reason: "Already linked to this account" };
  }

  return { success: true, reason: "Node added successfully" };
}

/** Append one result line to result.txt */
function writeResult(link, success, reason) {
  const status = success ? "[OK  ]" : "[FAIL]";
  const line = `${status} ${link} | ${reason}\n`;
  fs.appendFileSync(RESULT_FILE, line);
  console.log(line.trim());
}

// ─────────────────────────────────────────────
//  MAIN
// ─────────────────────────────────────────────
async function main() {
  const links = readLinks();
  if (links.length === 0) {
    console.error("No links found in input-links.txt — aborting.");
    process.exit(1);
  }

  const cookies = loadCookies();
  console.log(`Loaded ${links.length} links.`);

  // Init result file
  const header = [
    `Add-node started: ${new Date().toISOString()}`,
    `Total links: ${links.length}`,
    "=".repeat(70),
    "",
  ].join("\n");
  fs.writeFileSync(RESULT_FILE, header);

  const browser = await puppeteer.launch({
    executablePath: CHROMIUM_PATH,
    headless: false,
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--start-maximized"],
    defaultViewport: null,
  });

  const page = await browser.newPage();
  await loginWithCookies(page, cookies);

  const results = { success: [], fail: [] };

  for (let i = 0; i < links.length; i++) {
    const link = links[i];
    const label = `[${i + 1}/${links.length}]`;
    console.log(`\n${"─".repeat(60)}`);
    console.log(`${label} ${link}`);

    let success = false;
    let reason = "";

    try {
      const result = await addNode(page, link);
      success = result.success;
      reason = result.reason;
    } catch (err) {
      success = false;
      reason = err.message;
      console.error(`Error: ${err.message}`);
    }

    writeResult(link, success, reason);
    (success ? results.success : results.fail).push(link);

    if (i < links.length - 1) {
      console.log(`Waiting ${DELAY_BETWEEN_LINKS_MS / 1000}s before next link...`);
      await sleep(DELAY_BETWEEN_LINKS_MS);
    }
  }

  // Summary
  const summary = [
    "",
    "=".repeat(70),
    "SUMMARY",
    "=".repeat(70),
    `Success (${results.success.length}):`,
    results.success.length ? results.success.join("\n") : "  (none)",
    "",
    `Fail (${results.fail.length}):`,
    results.fail.length ? results.fail.join("\n") : "  (none)",
    "",
    `Finished: ${new Date().toISOString()}`,
  ].join("\n");

  fs.appendFileSync(RESULT_FILE, summary + "\n");
  console.log(summary);

  await browser.close();
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
