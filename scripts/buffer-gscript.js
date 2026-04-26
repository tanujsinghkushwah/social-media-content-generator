// ============================================================
//  Buffer Post Scheduler — Google Apps Script  v7
//
//  Sheet columns (NEW STRUCTURE):
//    A = Date (IST)
//    B = Topic/Keywords
//    C = X Post content
//    D = Instagram Post content
//    E = Image URL  (=HYPERLINK("url","View Image") or plain URL)
//    F = Status  (PENDING → COMPLETED / FAILED / NO IMAGE)
//
//  - Picks up to 3 rows where Status ≠ COMPLETED
//  - Posts C to Twitter, D to Instagram + LinkedIn independently
//  - Updates col F: COMPLETED / FAILED / PARTIAL / NO IMAGE
// ============================================================

// ─────────────────────────────────────────────────────────────
//  CONFIGURATION
// ─────────────────────────────────────────────────────────────
const CONFIG = {
  BUFFER_API_KEY: os.getenv("BUFFER_API_KEY"),  // ← your Buffer API key

  CHANNELS: [
    { platform: "twitter",   id: "69e72c5f031bfa423c27a512", contentCol: 3 },  // C
    { platform: "instagram", id: "69e72c2d031bfa423c27a4a5", contentCol: 4 },  // D
    { platform: "linkedin",  id: "69e72c82031bfa423c27a560", contentCol: 4 },  // D
  ],

  SHEET_NAME:     "Sheet1",
  SPREADSHEET_ID: "xxxxxxxx",

  COL_IMAGE:   5,  // E — Image URL
  COL_STATUS:  6,  // F — Single status column

  IST_OFFSET_MINUTES: 330,  // IST = UTC+5:30
  TWITTER_MAX_CHARS:  278,  // Hard limit 280, 2-char buffer

  SCHEDULE_SLOTS_WEEKDAY: [
    { hour: 18, minute:  0, label: "6:00 PM IST"  },
    { hour: 19, minute: 30, label: "7:30 PM IST"  },
    { hour: 21, minute:  0, label: "9:00 PM IST"  },
  ],
  SCHEDULE_SLOTS_WEEKEND: [
    { hour: 11, minute:  0, label: "11:00 AM IST" },
    { hour: 13, minute:  0, label: "1:00 PM IST"  },
    { hour: 17, minute:  0, label: "5:00 PM IST"  },
  ],
};

// ─────────────────────────────────────────────────────────────
//  MAIN FUNCTION — run manually or via daily trigger
// ─────────────────────────────────────────────────────────────
function schedulePostsToBuffer() {
  const sheet = SpreadsheetApp
    .openById(CONFIG.SPREADSHEET_ID)
    .getSheetByName(CONFIG.SHEET_NAME);
  if (!sheet) { Logger.log("❌ Sheet not found: " + CONFIG.SHEET_NAME); return; }

  const data = sheet.getDataRange().getValues();
  const now  = new Date();

  // Determine weekday vs weekend in IST (0 = Sun, 6 = Sat)
  const istNow   = new Date(now.getTime() + CONFIG.IST_OFFSET_MINUTES * 60000);
  const dayOfWeek = istNow.getUTCDay();
  const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;
  const slots     = isWeekend ? CONFIG.SCHEDULE_SLOTS_WEEKEND : CONFIG.SCHEDULE_SLOTS_WEEKDAY;
  Logger.log(`📅 Day: ${["Sun","Mon","Tue","Wed","Thu","Fri","Sat"][dayOfWeek]} IST → using ${isWeekend ? "weekend" : "weekday"} slots`);

  // ── Collect up to 3 rows where Status ≠ COMPLETED ──
  const HEADER_SENTINELS = new Set(["date (ist)", "x post", "instagram post", "topic/keywords"]);
  const pendingRows = [];
  for (let i = 1; i < data.length; i++) {
    const row    = data[i];
    const status = String(row[CONFIG.COL_STATUS - 1]).trim().toUpperCase();
    // Skip rows that look like duplicate header rows (col A or C contains header text)
    const dateVal    = String(row[0]).trim().toLowerCase();
    const xPostVal   = String(row[2]).trim().toLowerCase();
    if (HEADER_SENTINELS.has(dateVal) || HEADER_SENTINELS.has(xPostVal)) {
      Logger.log(`⚠️  Skipping row ${i + 1} — looks like a duplicate header row.`);
      continue;
    }
    if (status !== "COMPLETED") pendingRows.push({ rowIndex: i + 1, row });
    if (pendingRows.length === 3) break;
  }

  if (pendingRows.length === 0) {
    Logger.log("ℹ️  Nothing to schedule — all rows are COMPLETED.");
    return;
  }

  Logger.log(`📋 Found ${pendingRows.length} row(s) to process.\n`);

  pendingRows.forEach(({ rowIndex, row }, idx) => {
    const imageUrl = extractHyperlinkUrl_(sheet, rowIndex, CONFIG.COL_IMAGE);
    const slot     = slots[idx];
    const dueAt    = buildDueAt_(now, slot);

    Logger.log(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);
    Logger.log(`📝 Row ${rowIndex} → ${slot.label}  (UTC: ${dueAt})`);
    Logger.log(`   Image : ${imageUrl || "none"}`);

    const results = [];  // track per-channel outcome

    CONFIG.CHANNELS.forEach(ch => {
      const content = String(row[ch.contentCol - 1]).trim();

      if (!content) {
        Logger.log(`\n   ⚠️  ${ch.platform.toUpperCase()}: empty content — skipping.`);
        results.push("SKIPPED");
        return;
      }

      if (ch.platform === "instagram" && !imageUrl) {
        Logger.log(`\n   ⚠️  INSTAGRAM skipped — no image found in row ${rowIndex}.`);
        results.push("NO IMAGE");
        return;
      }

      Logger.log(`\n   📤 Posting to ${ch.platform.toUpperCase()}…`);
      Logger.log(`   Text  : ${content.substring(0, 80)}…`);

      const success = createBufferPost_(content, dueAt, imageUrl, ch.id, ch.platform);
      results.push(success ? "COMPLETED" : "FAILED");
      Logger.log(`   ${success ? "✅" : "❌"} ${ch.platform.toUpperCase()} → ${success ? "COMPLETED" : "FAILED"}`);

      Utilities.sleep(400);
    });

    // ── Resolve single status from all channel results ──
    const finalStatus = resolveStatus_(results);
    sheet.getRange(rowIndex, CONFIG.COL_STATUS).setValue(finalStatus);
    Logger.log(`\n   📌 Row ${rowIndex} status → ${finalStatus}`);
  });

  Logger.log(`\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);
  Logger.log("🎉 Done! → publish.buffer.com/schedule");
}

// ─────────────────────────────────────────────────────────────
//  Resolve a single status string from an array of per-channel results
//  Priority: FAILED > PARTIAL > NO IMAGE > COMPLETED > SKIPPED
// ─────────────────────────────────────────────────────────────
function resolveStatus_(results) {
  if (results.every(r => r === "COMPLETED")) return "COMPLETED";
  if (results.every(r => r === "FAILED"))    return "FAILED";
  if (results.includes("FAILED"))            return "PARTIAL";
  if (results.includes("NO IMAGE"))          return "NO IMAGE";
  if (results.every(r => r === "SKIPPED"))   return "SKIPPED";
  return "PARTIAL";
}

// ─────────────────────────────────────────────────────────────
//  POST NOW — instantly publishes a single PENDING row
//  Set TARGET_ROW below, then run postNow()
// ─────────────────────────────────────────────────────────────

// ⬇️ Set this to the sheet row number you want to post immediately
const TARGET_ROW = 2; // ← change this before running

function postNow() {
  const sheet = SpreadsheetApp
    .openById(CONFIG.SPREADSHEET_ID)
    .getSheetByName(CONFIG.SHEET_NAME);
  if (!sheet) { Logger.log("❌ Sheet not found."); return; }

  const data     = sheet.getDataRange().getValues();
  const rowIndex = TARGET_ROW;
  const row      = data[rowIndex - 1];

  if (!row) { Logger.log(`❌ Row ${rowIndex} not found in sheet.`); return; }

  const imageUrl = extractHyperlinkUrl_(sheet, rowIndex, CONFIG.COL_IMAGE);

  // Post immediately — dueAt = 60 seconds from now
  const dueAt = new Date(Date.now() + 60 * 1000).toISOString();

  Logger.log(`🚀 Posting row ${rowIndex} immediately…`);
  Logger.log(`   Image : ${imageUrl || "none"}`);
  Logger.log(`   Due   : ${dueAt}\n`);

  const results = [];

  CONFIG.CHANNELS.forEach(ch => {
    const content = String(row[ch.contentCol - 1]).trim();

    if (!content) {
      Logger.log(`⚠️  ${ch.platform.toUpperCase()}: empty content — skipping.`);
      results.push("SKIPPED");
      return;
    }

    if (ch.platform === "instagram" && !imageUrl) {
      Logger.log(`⚠️  INSTAGRAM skipped — no image URL in row ${rowIndex}.`);
      sheet.getRange(rowIndex, CONFIG.COL_STATUS).setValue("NO IMAGE");
      results.push("NO IMAGE");
      return;
    }

    Logger.log(`📤 Posting to ${ch.platform.toUpperCase()}…`);
    Logger.log(`   Text  : ${content.substring(0, 80)}…`);

    const success = createBufferPost_(content, dueAt, imageUrl, ch.id, ch.platform);
    results.push(success ? "COMPLETED" : "FAILED");
    Logger.log(`${success ? "✅" : "❌"} ${ch.platform.toUpperCase()} → ${success ? "COMPLETED" : "FAILED"}\n`);

    Utilities.sleep(400);
  });

  const finalStatus = resolveStatus_(results);
  sheet.getRange(rowIndex, CONFIG.COL_STATUS).setValue(finalStatus);
  Logger.log(`📌 Row ${rowIndex} status → ${finalStatus}`);
  Logger.log("🎉 postNow() done!");
}

// ─────────────────────────────────────────────────────────────
//  Build and fire a createPost mutation
// ─────────────────────────────────────────────────────────────
function createBufferPost_(text, dueAt, imageUrl, channelId, platform) {
  const hasImage = !!imageUrl;

  let postText = text;
  if (platform === "twitter") {
    const maxLen = CONFIG.TWITTER_MAX_CHARS - (hasImage ? 24 : 0);
    if (postText.length > maxLen) {
      postText = postText.substring(0, maxLen - 1) + "…";
      Logger.log(`   ✂️  Twitter trimmed to ${postText.length} chars.`);
    }
  }

  const assetsBlock = hasImage
    ? `assets: { images: [{ url: ${JSON.stringify(imageUrl)} }] },`
    : "";

  let metadataBlock = "";
  if (platform === "instagram") {
    metadataBlock = `metadata: { instagram: { type: post, shouldShareToFeed: true } },`;
  }

  const mutation = `
    mutation CreatePost {
      createPost(input: {
        text: ${JSON.stringify(postText)},
        channelId: ${JSON.stringify(channelId)},
        schedulingType: automatic,
        mode: customScheduled,
        dueAt: ${JSON.stringify(dueAt)},
        ${metadataBlock}
        ${assetsBlock}
      }) {
        ... on PostActionSuccess {
          post { id dueAt }
        }
        ... on MutationError {
          message
        }
      }
    }
  `;

  const result = callBufferAPI_(mutation);

  if (!result) { Logger.log(`   ❌ No response from API.`); return false; }
  if (result.errors) { Logger.log(`   ❌ API Error: ${JSON.stringify(result.errors)}`); return false; }

  const outcome = result.data?.createPost;
  if (outcome?.post?.id) {
    Logger.log(`   ✅ Post ID: ${outcome.post.id} | Due: ${outcome.post.dueAt}`);
    return true;
  }
  if (outcome?.message) {
    Logger.log(`   ❌ Mutation Error: ${outcome.message}`);
    return false;
  }

  Logger.log(`   ❓ Unexpected response: ${JSON.stringify(result)}`);
  return false;
}

// ─────────────────────────────────────────────────────────────
//  Extract actual URL from =HYPERLINK("url","View Image") cell
// ─────────────────────────────────────────────────────────────
function extractHyperlinkUrl_(sheet, rowIndex, colIndex) {
  const cell    = sheet.getRange(rowIndex, colIndex);
  const formula = cell.getFormula();

  if (formula?.toUpperCase().startsWith("=HYPERLINK")) {
    const match = formula.match(/=HYPERLINK\(\s*["']([^"']+)["']/i);
    if (match?.[1]) return match[1];
  }

  try {
    for (const run of cell.getRichTextValue()?.getRuns() || []) {
      const url = run.getLinkUrl();
      if (url?.startsWith("http")) return url;
    }
  } catch (e) {}

  const value = String(cell.getValue()).trim();
  return value.startsWith("http") ? value : null;
}

// ─────────────────────────────────────────────────────────────
//  Build UTC ISO timestamp — auto-advances if slot already passed
//  Assumes GAS project timezone = Asia/Kolkata (IST):
//  setHours/getDate operate in IST, toISOString() returns UTC.
// ─────────────────────────────────────────────────────────────
function buildDueAt_(nowUtc, slot) {
  const candidate = new Date(nowUtc);
  candidate.setHours(slot.hour, slot.minute, 0, 0);  // sets IST time

  if (candidate.getTime() - nowUtc.getTime() < 5 * 60 * 1000) {
    candidate.setDate(candidate.getDate() + 1);
    Logger.log(`   ⏩ ${slot.label} already passed — pushed to tomorrow IST.`);
  }

  return candidate.toISOString();  // internally stored as correct UTC
}

// ─────────────────────────────────────────────────────────────
//  Generic Buffer GraphQL helper
// ─────────────────────────────────────────────────────────────
function callBufferAPI_(query) {
  try {
    const res = UrlFetchApp.fetch("https://api.buffer.com", {
      method:  "POST",
      headers: {
        "Content-Type":  "application/json",
        "Authorization": `Bearer ${CONFIG.BUFFER_API_KEY}`,
      },
      payload: JSON.stringify({ query }),
      muteHttpExceptions: true,
    });
    return JSON.parse(res.getContentText());
  } catch (e) {
    Logger.log("   Network error: " + e.message);
    return null;
  }
}

// ─────────────────────────────────────────────────────────────
//  Helper — list all Buffer channels (run to verify IDs)
// ─────────────────────────────────────────────────────────────
function fetchChannelId() {
  const orgResult = callBufferAPI_(`query { account { organizations { id name } } }`);
  const orgId = orgResult?.data?.account?.organizations?.[0]?.id;
  if (!orgId) { Logger.log("❌ Could not get org ID."); return; }
  const chResult = callBufferAPI_(`
    query { channels(input: { organizationId: "${orgId}" }) { id displayName service } }
  `);
  chResult?.data?.channels?.forEach(ch =>
    Logger.log(`ID: ${ch.id} | ${ch.service} | ${ch.displayName}`)
  );
}

// ─────────────────────────────────────────────────────────────
//  OPTIONAL — register a daily trigger (run once)
// ─────────────────────────────────────────────────────────────
function createDailyTrigger() {
  ScriptApp.getProjectTriggers()
    .filter(t => t.getHandlerFunction() === "schedulePostsToBuffer")
    .forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger("schedulePostsToBuffer")
    .timeBased().everyDays(1).atHour(0).create();
  Logger.log("✅ Daily trigger set for midnight IST.");
}