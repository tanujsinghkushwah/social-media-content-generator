// ============================================================
//  Buffer Post Scheduler — Google Apps Script  v8
//
//  Sheet columns (PER-CHANNEL STATUS):
//    A = Date (IST)
//    B = Topic/Keywords
//    C = X Post content
//    D = Instagram Post content
//    E = LinkedIn Post content
//    F = Image URL  (=HYPERLINK("url","View Image") or plain URL)
//    G = Status X          (PENDING → COMPLETED / FAILED / SKIPPED)
//    H = Status Instagram  (PENDING → COMPLETED / FAILED / NO IMAGE / SKIPPED)
//    I = Status LinkedIn   (PENDING → COMPLETED / FAILED / SKIPPED)
//
//  - Each channel is processed independently.
//  - Picks up to 3 rows per channel where that channel's status is not terminal.
//  - Terminal statuses (never retried): COMPLETED, FAILED, NO IMAGE, SKIPPED.
//  - User backfills missed posts manually via postChannelNow(rowIndex, platform).
// ============================================================

// ─────────────────────────────────────────────────────────────
//  CONFIGURATION
// ─────────────────────────────────────────────────────────────
const CONFIG = {
  BUFFER_API_KEY: os.getenv("BUFFER_API_KEY"),  // ← your Buffer API key

  CHANNELS: [
    { platform: "twitter",   id: "69e72c5f031bfa423c27a512", contentCol: 3, statusCol: 7 },  // C → G
    { platform: "instagram", id: "69e72c2d031bfa423c27a4a5", contentCol: 4, statusCol: 8 },  // D → H
    { platform: "linkedin",  id: "69e72c82031bfa423c27a560", contentCol: 5, statusCol: 9 },  // E → I
  ],

  SHEET_NAME:     "Sheet1",
  SPREADSHEET_ID: "xxxxxxxx",

  COL_IMAGE: 6,  // F — Image URL

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

// Statuses that mean "do not retry this row for this channel".
const TERMINAL_STATUSES = new Set(["COMPLETED", "FAILED", "NO IMAGE", "SKIPPED"]);

// ─────────────────────────────────────────────────────────────
//  MAIN FUNCTION — run manually or via daily trigger
//  Each channel scans the sheet independently and posts up to 3 rows
//  whose own per-channel status is not yet terminal.
// ─────────────────────────────────────────────────────────────
function schedulePostsToBuffer() {
  const sheet = SpreadsheetApp
    .openById(CONFIG.SPREADSHEET_ID)
    .getSheetByName(CONFIG.SHEET_NAME);
  if (!sheet) { Logger.log("❌ Sheet not found: " + CONFIG.SHEET_NAME); return; }

  const data = sheet.getDataRange().getValues();
  const now  = new Date();

  // Determine weekday vs weekend in IST (0 = Sun, 6 = Sat)
  const istNow    = new Date(now.getTime() + CONFIG.IST_OFFSET_MINUTES * 60000);
  const dayOfWeek = istNow.getUTCDay();
  const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;
  const slots     = isWeekend ? CONFIG.SCHEDULE_SLOTS_WEEKEND : CONFIG.SCHEDULE_SLOTS_WEEKDAY;
  Logger.log(`📅 Day: ${["Sun","Mon","Tue","Wed","Thu","Fri","Sat"][dayOfWeek]} IST → using ${isWeekend ? "weekend" : "weekday"} slots`);

  CONFIG.CHANNELS.forEach(ch => {
    Logger.log(`\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);
    Logger.log(`▶️  Processing channel: ${ch.platform.toUpperCase()}`);

    const picks = [];
    for (let i = 1; i < data.length && picks.length < 3; i++) {
      const row = data[i];
      if (looksLikeHeaderRow_(row)) {
        Logger.log(`⚠️  Skipping row ${i + 1} — looks like a duplicate header row.`);
        continue;
      }
      const status = String(row[ch.statusCol - 1] || "").trim().toUpperCase();
      if (TERMINAL_STATUSES.has(status)) continue;
      picks.push({ rowIndex: i + 1, row });
    }

    if (picks.length === 0) {
      Logger.log(`ℹ️  Nothing to schedule for ${ch.platform.toUpperCase()}.`);
      return;
    }

    Logger.log(`📋 Found ${picks.length} row(s) to post on ${ch.platform.toUpperCase()}.`);

    picks.forEach(({ rowIndex, row }, idx) => {
      const slot     = slots[idx];
      const dueAt    = buildDueAt_(now, slot);
      const imageUrl = extractHyperlinkUrl_(sheet, rowIndex, CONFIG.COL_IMAGE);
      const outcome  = postChannelForRow_(ch, rowIndex, row, imageUrl, dueAt, slot.label);
      sheet.getRange(rowIndex, ch.statusCol).setValue(outcome);
      Logger.log(`   📌 Row ${rowIndex} ${ch.platform.toUpperCase()} → ${outcome}`);
      Utilities.sleep(400);
    });
  });

  Logger.log(`\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);
  Logger.log("🎉 Done! → publish.buffer.com/schedule");
}

// ─────────────────────────────────────────────────────────────
//  Per-channel posting helper used by both the scheduler and postNow.
//  Returns the per-channel status string to write back to the sheet.
// ─────────────────────────────────────────────────────────────
function postChannelForRow_(ch, rowIndex, row, imageUrl, dueAt, slotLabel) {
  const content = String(row[ch.contentCol - 1] || "").trim();

  if (!content) {
    Logger.log(`   ⚠️  ${ch.platform.toUpperCase()} row ${rowIndex}: empty content — SKIPPED.`);
    return "SKIPPED";
  }

  if (ch.platform === "instagram" && !imageUrl) {
    Logger.log(`   ⚠️  INSTAGRAM row ${rowIndex}: no image URL — NO IMAGE.`);
    return "NO IMAGE";
  }

  Logger.log(`   📤 ${ch.platform.toUpperCase()} row ${rowIndex} → ${slotLabel || dueAt}`);
  Logger.log(`      Text: ${content.substring(0, 80)}…`);

  const success = createBufferPost_(content, dueAt, imageUrl, ch.id, ch.platform);
  return success ? "COMPLETED" : "FAILED";
}

// ─────────────────────────────────────────────────────────────
//  Detect duplicate header rows so we don't post header text as content.
// ─────────────────────────────────────────────────────────────
const HEADER_SENTINELS_ = new Set([
  "date (ist)", "topic/keywords", "x post", "instagram post", "linkedin post",
]);
function looksLikeHeaderRow_(row) {
  const dateVal  = String(row[0] || "").trim().toLowerCase();
  const xPostVal = String(row[2] || "").trim().toLowerCase();
  return HEADER_SENTINELS_.has(dateVal) || HEADER_SENTINELS_.has(xPostVal);
}

// ─────────────────────────────────────────────────────────────
//  POST NOW — instantly publishes a single row to all 3 channels,
//  but only for channels whose per-channel status is non-terminal.
//  Set TARGET_ROW below, then run postNow().
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
  const dueAt    = new Date(Date.now() + 60 * 1000).toISOString();

  Logger.log(`🚀 Posting row ${rowIndex} immediately…`);
  Logger.log(`   Image : ${imageUrl || "none"}`);
  Logger.log(`   Due   : ${dueAt}\n`);

  CONFIG.CHANNELS.forEach(ch => {
    const status = String(row[ch.statusCol - 1] || "").trim().toUpperCase();
    if (TERMINAL_STATUSES.has(status)) {
      Logger.log(`   ⏭️  ${ch.platform.toUpperCase()} row ${rowIndex}: status ${status} — skipping.`);
      return;
    }
    const outcome = postChannelForRow_(ch, rowIndex, row, imageUrl, dueAt, "now");
    sheet.getRange(rowIndex, ch.statusCol).setValue(outcome);
    Logger.log(`   📌 Row ${rowIndex} ${ch.platform.toUpperCase()} → ${outcome}`);
    Utilities.sleep(400);
  });

  Logger.log("🎉 postNow() done!");
}

// ─────────────────────────────────────────────────────────────
//  MANUAL BACKFILL — re-fire a single channel for a single row,
//  ignoring its current per-channel status. Use this to manually
//  recover from a FAILED / NO IMAGE / SKIPPED entry.
//
//  Usage from the GAS editor:  postChannelNow(7, "instagram")
// ─────────────────────────────────────────────────────────────
function postChannelNow(rowIndex, platform) {
  const ch = CONFIG.CHANNELS.find(c => c.platform === String(platform).toLowerCase());
  if (!ch) { Logger.log(`❌ Unknown platform: ${platform}`); return; }

  const sheet = SpreadsheetApp
    .openById(CONFIG.SPREADSHEET_ID)
    .getSheetByName(CONFIG.SHEET_NAME);
  if (!sheet) { Logger.log("❌ Sheet not found."); return; }

  const row = sheet.getDataRange().getValues()[rowIndex - 1];
  if (!row) { Logger.log(`❌ Row ${rowIndex} not found.`); return; }

  const imageUrl = extractHyperlinkUrl_(sheet, rowIndex, CONFIG.COL_IMAGE);
  const dueAt    = new Date(Date.now() + 60 * 1000).toISOString();

  Logger.log(`🔁 Manual backfill: ${ch.platform.toUpperCase()} row ${rowIndex}`);
  const outcome = postChannelForRow_(ch, rowIndex, row, imageUrl, dueAt, "now");
  sheet.getRange(rowIndex, ch.statusCol).setValue(outcome);
  Logger.log(`📌 Row ${rowIndex} ${ch.platform.toUpperCase()} → ${outcome}`);
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
