import { spawn } from "node:child_process";
import { resolve } from "node:path";
import process from "node:process";

const appDir = process.cwd();
const repoDir = resolve(appDir, "..");
const port = process.env.PORT || "3000";

if (!process.env.BLACKMARKET_API_TOKEN) {
  throw new Error("BLACKMARKET_API_TOKEN must be configured as a private Render environment variable.");
}
if (!process.env.DATABASE_URL) {
  throw new Error("DATABASE_URL must point to durable PostgreSQL before the hosted backend can start.");
}
if (!process.env.BLACKMARKET_WEB_PASSWORD) {
  throw new Error("BLACKMARKET_WEB_PASSWORD must be configured before the website can start.");
}
if (!process.env.BLACKMARKET_SESSION_SECRET || process.env.BLACKMARKET_SESSION_SECRET.length < 32) {
  throw new Error("BLACKMARKET_SESSION_SECRET must contain at least 32 characters.");
}

const commonEnv = {
  ...process.env,
  PYTHONPATH: [repoDir, process.env.PYTHONPATH].filter(Boolean).join(":"),
  BLACKMARKET_REMOTE_API_ENABLED: "1",
  BLACKMARKET_API_HOST: "127.0.0.1",
  BLACKMARKET_BACKEND_URL: process.env.BLACKMARKET_BACKEND_URL || "http://127.0.0.1:8765",
};

const backend = spawn(
  process.env.PYTHON_BIN || "python3",
  ["-m", "uvicorn", "src_tauri.backend.main:app", "--host", "127.0.0.1", "--port", "8765"],
  { cwd: repoDir, env: commonEnv, stdio: "inherit" },
);
const web = spawn(
  process.execPath,
  [resolve(appDir, "node_modules/next/dist/bin/next"), "start", "-p", port],
  { cwd: appDir, env: commonEnv, stdio: "inherit" },
);

let stopping = false;
function stop(signal = "SIGTERM") {
  if (stopping) return;
  stopping = true;
  backend.kill(signal);
  web.kill(signal);
}
process.on("SIGTERM", () => stop("SIGTERM"));
process.on("SIGINT", () => stop("SIGINT"));

backend.on("error", (error) => {
  console.error("Python backend failed to launch:", error);
  stop();
  process.exitCode = 1;
});
web.on("error", (error) => {
  console.error("Next.js web server failed to launch:", error);
  stop();
  process.exitCode = 1;
});
backend.on("exit", (code) => {
  if (!stopping) {
    console.error(`Python backend exited unexpectedly (code ${code}).`);
    stop();
    process.exitCode = code || 1;
  }
});
web.on("exit", (code) => {
  if (!stopping) {
    console.error(`Next.js web server exited unexpectedly (code ${code}).`);
    stop();
    process.exitCode = code || 1;
  }
});
