/** Run real transport boundaries in a fresh process without a Store or public network. */
import { expect, test } from "bun:test";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

test("canonical CLI and human egress boundaries against isolated loopback", () => {
  const dir=mkdtempSync(join(tmpdir(), "cct-rule-boundaries-"));
  const interpreter=process.env._CCT_PYTHON_EXECUTABLE;
  if (!interpreter) throw new Error("Test launcher must supply its Python interpreter");
  try {
    const result=Bun.spawnSync([process.execPath,"test","--preload",join(import.meta.dir,"outbound-style-loopback-preload.ts"),join(import.meta.dir,"outbound-style-boundary-cases.ts")],{
      cwd:dir,env:{HOME:dir,PATH:"/usr/bin:/bin",TMPDIR:dir,_CCT_PYTHON_EXECUTABLE:interpreter},stdout:"pipe",stderr:"pipe",timeout:10000,
    });
    const log=new TextDecoder().decode(result.stdout)+new TextDecoder().decode(result.stderr);
    console.log(log);
    expect(result.exitCode).toBe(0);
  } finally { rmSync(dir,{recursive:true,force:true}); }
},15000);
