/**
 * Pi agent extension for resume-sessions.
 * After a successful git commit, extracts the commit message and uses it as the session title.
 */
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import * as fs from "node:fs";
import * as path from "node:path";

interface Session {
  titles: string[];
  created: string;
  last_updated: string;
}

interface Sessions {
  [key: string]: Session;
}

let currentSessionId: string | null = null;
let currentCwd: string | null = null;

const DEBUG_LOG = "/tmp/resume-sessions-debug.log";
function debug(msg: string) {
  fs.appendFileSync(DEBUG_LOG, `${new Date().toISOString()} ${msg}\n`);
}

function loadSessions(cwd: string): Sessions {
  const sessionsFile = path.join(cwd, ".resume-sessions", "sessions.json");
  try {
    if (fs.existsSync(sessionsFile)) {
      return JSON.parse(fs.readFileSync(sessionsFile, "utf-8"));
    }
  } catch {}
  return {};
}

function saveSessions(cwd: string, sessions: Sessions): void {
  const sessionsDir = path.join(cwd, ".resume-sessions");
  const sessionsFile = path.join(sessionsDir, "sessions.json");
  
  if (!fs.existsSync(sessionsDir)) {
    fs.mkdirSync(sessionsDir, { recursive: true });
  }
  fs.writeFileSync(sessionsFile, JSON.stringify(sessions, null, 2));
}

function updateTitle(cwd: string, sessionId: string, newTitle: string): void {
  debug(`[resume-sessions] updateTitle: cwd=${cwd}, sessionId=${sessionId}, title=${newTitle}`);
  const sessions = loadSessions(cwd);
  const now = new Date().toISOString();
  
  if (!sessions[sessionId]) {
    sessions[sessionId] = {
      titles: [],
      created: now,
      last_updated: now,
    };
  }
  
  const session = sessions[sessionId];
  const currentTitle = session.titles[session.titles.length - 1];
  
  // Only append if different
  if (newTitle !== currentTitle) {
    session.titles.push(newTitle);
  }
  session.last_updated = now;
  
  try {
    saveSessions(cwd, sessions);
    debug(`[resume-sessions] Saved to ${path.join(cwd, ".resume-sessions", "sessions.json")}`);
  } catch (e) {
    debug(`[resume-sessions] Save failed: ${e}`);
  }
  
  // Update terminal tab title
  process.stdout.write(`\x1b]0;${newTitle}\x07`);
}

function extractCommitMessage(command: string): string | null {
  // Match -m "message" or -m 'message'
  const match = command.match(/-m\s+["']([^"']+)["']/);
  return match ? match[1] : null;
}

function extractCwd(command: string, defaultCwd: string): string {
  const cdMatch = command.match(/cd\s+([^\s&;]+)/);
  if (cdMatch) {
    let targetDir = cdMatch[1];
    if (targetDir.startsWith("~")) {
      targetDir = targetDir.replace("~", process.env.HOME || "");
    }
    return path.resolve(defaultCwd, targetDir);
  }
  return defaultCwd;
}

export default function (pi: ExtensionAPI) {
  // Track session ID and cwd
  pi.on("session_start", async (event, ctx) => {
    if (ctx.sessionManager.getSessionFile()) {
      currentSessionId = path.basename(ctx.sessionManager.getSessionFile()!).replace(".jsonl", "");
      currentCwd = ctx.cwd;
      debug(`[resume-sessions] Session start: id=${currentSessionId}, cwd=${currentCwd}`);
    }
  });

  pi.on("session_switch", async (event, ctx) => {
    if (ctx.sessionManager.getSessionFile()) {
      currentSessionId = path.basename(ctx.sessionManager.getSessionFile()!).replace(".jsonl", "");
      currentCwd = ctx.cwd;
      debug(`[resume-sessions] Session switch: id=${currentSessionId}, cwd=${currentCwd}`);
    }
  });

  // Detect successful git commit and extract commit message as title
  pi.on("tool_result", async (event, ctx) => {
    if (event.toolName !== "bash") return undefined;

    const command = event.input?.command as string;
    if (!command) return undefined;
    
    debug(`[resume-sessions] Command: ${command}`);
    
    if (command.includes("git commit") && !event.isError) {
      const commitMessage = extractCommitMessage(command);
      if (!commitMessage) {
        debug(`[resume-sessions] No commit message found in command`);
        return undefined;
      }
      
      const cwd = extractCwd(command, ctx.cwd);
      debug(`[resume-sessions] Commit detected: message="${commitMessage}", cwd=${cwd}`);
      
      if (currentSessionId) {
        updateTitle(cwd, currentSessionId, commitMessage);
      }
    }
    return undefined;
  });
}
