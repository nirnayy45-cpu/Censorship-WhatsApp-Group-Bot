/**
 * WhatsApp URL/keyword auto-delete bridge.
 *
 * This process owns the WhatsApp connection. The Telegram control bot writes
 * JSON files in this same directory and this bridge watches those files.
 */

const fs = require("fs");
const path = require("path");
const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
} = require("@whiskeysockets/baileys");
const pino = require("pino");

const DATA_DIR = __dirname;
const AUTH_FOLDER = path.join(DATA_DIR, "auth");
const GROUPS_FILE = path.join(DATA_DIR, "groups.json");
const FILTERS_FILE = path.join(DATA_DIR, "filters.json");
const QR_FILE = path.join(DATA_DIR, "whatsapp_pairing_qr.png");

const URL_REGEX =
  /(https?:\/\/\S+|www\.\S+|\b\S+\.(com|in|net|org|xyz|io|co)\b)/i;
const DEFAULT_FILTERS = {
  enabled_groups: [],
  url_filter: true,
  keywords: [],
};

let reconnectScheduled = false;

function readJsonSafe(filePath, fallback) {
  try {
    if (!fs.existsSync(filePath)) return fallback;
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch (error) {
    console.warn(`Could not read ${path.basename(filePath)}: ${error.message}`);
    return fallback;
  }
}

function writeJson(filePath, data) {
  const temporaryPath = `${filePath}.tmp`;
  fs.writeFileSync(temporaryPath, JSON.stringify(data, null, 2), "utf8");
  fs.renameSync(temporaryPath, filePath);
}

function getMessageText(message) {
  if (!message) return "";
  return (
    message.conversation ||
    message.extendedTextMessage?.text ||
    message.imageMessage?.caption ||
    message.videoMessage?.caption ||
    message.documentMessage?.caption ||
    ""
  );
}

function shouldDelete(text, filters) {
  if (!text) return false;
  if (filters.url_filter && URL_REGEX.test(text)) return true;
  const keywords = Array.isArray(filters.keywords) ? filters.keywords : [];
  const lowerText = text.toLowerCase();
  return keywords.some((keyword) =>
    lowerText.includes(String(keyword).toLowerCase()),
  );
}

async function exportGroups(sock) {
  try {
    const groupsMap = await sock.groupFetchAllParticipating();
    const groups = Object.values(groupsMap).map((group) => ({
      name: group.subject,
      jid: group.id,
    }));
    writeJson(GROUPS_FILE, groups);
    console.log(`Exported ${groups.length} group(s) to groups.json`);
  } catch (error) {
    console.error("Failed to export groups:", error.message);
  }
}

async function startSock() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_FOLDER);
  const { version } = await fetchLatestBaileysVersion();
  const sock = makeWASocket({
    version,
    auth: state,
    logger: pino({ level: "silent" }),
    browser: ["URL-Filter-Bridge", "Chrome", "1.0.0"],
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr && !state.creds.registered) {
      try {
        await require("qrcode").toFile(QR_FILE, qr, {
          width: 640,
          margin: 2,
          errorCorrectionLevel: "M",
        });
        console.log("WhatsApp QR code is ready in whatsapp_pairing_qr.png");
      } catch (error) {
        console.error("Failed to render WhatsApp QR code:", error.message);
      }
      console.log("WhatsApp QR code is ready; scan it from Telegram with /link.");
    }

    if (connection === "open") {
      reconnectScheduled = false;
      fs.rmSync(QR_FILE, { force: true });
      console.log("WhatsApp connected.");
      await exportGroups(sock);
    }

    if (connection === "close") {
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

      if (!shouldReconnect) {
        fs.rmSync(AUTH_FOLDER, { recursive: true, force: true });
        console.log(
          "WhatsApp session was logged out or pairing failed; session reset. Send /link again.",
        );
      }

      if (!reconnectScheduled) {
        reconnectScheduled = true;
        console.log("WhatsApp connection closed; reconnecting...");
        setTimeout(() => {
          startSock().catch((error) => {
            console.error("Reconnect failed:", error.message);
          });
        }, 3000);
      }
    }
  });

  sock.ev.on("messages.upsert", async ({ messages }) => {
    const filters = readJsonSafe(FILTERS_FILE, DEFAULT_FILTERS);
    const enabledGroups = Array.isArray(filters.enabled_groups)
      ? filters.enabled_groups
      : [];

    for (const message of messages) {
      const remoteJid = message.key.remoteJid;
      if (!remoteJid?.endsWith("@g.us")) continue;
      if (!enabledGroups.includes(remoteJid)) continue;
      if (message.key.fromMe) continue;

      const text = getMessageText(message.message);
      if (!shouldDelete(text, filters)) continue;

      try {
        await sock.sendMessage(remoteJid, { delete: message.key });
        console.log(
          `[${new Date().toISOString()}] Deleted message in ${remoteJid}: "${text.slice(0, 60)}"`,
        );
      } catch (error) {
        console.warn(
          `[${new Date().toISOString()}] Could not delete in ${remoteJid}; is the bridge an admin? ${error.message}`,
        );
      }
    }
  });
}

if (!fs.existsSync(FILTERS_FILE)) {
  writeJson(FILTERS_FILE, DEFAULT_FILTERS);
}

startSock().catch((error) => {
  console.error("WhatsApp bridge failed to start:", error);
  process.exitCode = 1;
});