import { afterAll } from "bun:test";
import { join } from "node:path";
import { tmpdir } from "node:os";
for (const name of Object.keys(process.env)) {
  if (name.startsWith("CCT_") || name.startsWith("CLAUDE_CODE_TELEGRAMMER_")) delete process.env[name];
}
delete process.env.CC_ALLOW_BARE_ISSUE;
process.env.CCT_BOT_TOKEN = "synthetic-only-token";
process.env.CCT_SIGNATURE = "0";
process.env.CCT_AGENT_STATE_DIR = join(tmpdir(), "runtime-unused");
process.env.CCT_STORE_DSN = "postgresql://synthetic:synthetic@127.0.0.1:1/refused";
const requests: unknown[] = [];
const server = Bun.serve({hostname:"127.0.0.1",port:0,async fetch(request) {
  const data = request.headers.get("content-type")?.includes("multipart") ? Object.fromEntries(await request.formData()) : await request.json();
  requests.push({path:new URL(request.url).pathname,data});
  return Response.json({ok:true,result:{message_id:7001}});
}});
process.env.CCT_TELEGRAM_API_BASE = `http://127.0.0.1:${server.port}`;
(globalThis as any).__STYLE_REQUESTS = requests;
afterAll(()=>server.stop(true));
