/** Real fresh-process controls for the Python adapter boundary. */
import { expect, test } from "bun:test";
import { mkdtempSync, writeFileSync, rmSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const cases = [
  ["missing interpreter", { status: 0, stdout: "" }, false, true],
  ["nonzero exit", { status: 2, stdout: '{"ok":true}' }, false, false],
  ["invalid JSON", { status: 0, stdout: "invalid" }, false, false],
  ["absent verdict", { status: 0, stdout: "{}" }, false, false],
  ["truthy verdict", { status: 0, stdout: '{"ok":"true"}' }, false, false],
  ["malformed refusal", { status: 0, stdout: '{"ok":false,"token":"#106"}' }, false, false],
  ["qualified refusal", { status: 0, stdout: '{"ok":false,"token":"#106","message":"Use parenthetical description"}' }, false, false],
  ["qualified acceptance", { status: 0, stdout: '{"ok":true}' }, true, false],
  ["timeout", { status: 0, stdout: '{"ok":true}', sleep: 3 }, false, false],
] as const;

for (const [label, reply, expected, missing] of cases) {
  test(label + " fails closed unless the canonical response is valid", () => {
    const dir = mkdtempSync(join(tmpdir(), "cct-rule-process-"));
    const interpreter = process.env._CCT_PYTHON_EXECUTABLE;
    if (!interpreter) throw new Error("Test launcher must supply its Python interpreter");
    const stub = join(dir, "python");
    writeFileSync(stub, `#!${interpreter}\nimport json,sys,time\nd=json.loads(${JSON.stringify(JSON.stringify(reply))})\ntime.sleep(d.get('sleep',0))\nprint(d['stdout'])\nsys.exit(d['status'])\n`, {mode:0o700});
    const adapter = join(import.meta.dir, "..", "lib", "outbound-style.ts");
    const child = join(dir, "probe.ts");
    writeFileSync(child, `import {assertLabeledPrReferences} from ${JSON.stringify(adapter)};\nlet allowed=true; try {assertLabeledPrReferences('PR #106(Description)');} catch {allowed=false;} console.log(JSON.stringify({allowed}));`);
    try {
      const result = Bun.spawnSync([process.execPath, child], {
        env:{HOME:dir, PATH:"/usr/bin:/bin", _CCT_PYTHON_EXECUTABLE:missing ? join(dir,"absent") : stub},
        stdout:"pipe", stderr:"pipe", timeout:4000,
      });
      if (result.exitCode !== 0) throw new Error(new TextDecoder().decode(result.stderr));
      expect(JSON.parse(new TextDecoder().decode(result.stdout)).allowed).toBe(expected);
    } finally {
      rmSync(dir, {recursive:true, force:true});
    }
  });
}


test("the packaged predicate ignores an unrelated HOME hook", () => {
  const dir=mkdtempSync(join(tmpdir(), "cct-rule-home-"));
  const interpreter=process.env._CCT_PYTHON_EXECUTABLE;
  if (!interpreter) throw new Error("Test launcher must supply its Python interpreter");
  const hooks=join(dir,".claude","hooks","pre-tool-use");
  mkdirSync(hooks,{recursive:true});
  writeFileSync(join(hooks,"_telegram_rules.py"), 'print(\'{"ok":true}\')\n');
  const adapter=join(import.meta.dir,"..","lib","outbound-style.ts");
  const child=join(dir,"probe.ts");
  writeFileSync(child, `import {assertLabeledPrReferences} from ${JSON.stringify(adapter)};\nlet allowed=true; try {assertLabeledPrReferences('PR #106');} catch {allowed=false;} console.log(JSON.stringify({allowed}));`);
  try {
    const result=Bun.spawnSync([process.execPath,child],{env:{HOME:dir,PATH:"/usr/bin:/bin",_CCT_PYTHON_EXECUTABLE:interpreter},stdout:"pipe",stderr:"pipe",timeout:4000});
    if(result.exitCode!==0) throw new Error(new TextDecoder().decode(result.stderr));
    expect(JSON.parse(new TextDecoder().decode(result.stdout)).allowed).toBe(false);
  } finally { rmSync(dir,{recursive:true,force:true}); }
});
