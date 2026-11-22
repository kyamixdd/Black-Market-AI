import { hashPassword } from "../lib/session-core.mjs";

const password = process.env.PREVIEW_PASSWORD;
if (!password) {
  console.error("Set PREVIEW_PASSWORD in your local shell; do not commit or paste it into source files.");
  process.exit(1);
}
console.log(hashPassword(password));
