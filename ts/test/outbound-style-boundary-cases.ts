import { describe, expect, test } from "bun:test";
import { assertLabeledPrReferences, unlabeledPrReferences } from "../lib/outbound-style.js";
import { executeDurableSend, type DurableSendDeps } from "../lib/send-cli.js";
import { sendMessage, editMessageText, sendDocument } from "../lib/telegram-api.js";
import { join } from "node:path";

const cases: [string, string, boolean][] = [
  ["bare PR", "PR #106", false],
  ["Japanese parentheses", "PR #106（Storage 容量超過処理）", true],
  ["ASCII parentheses", "PR #106(Storage quota response)", true],
  ["horizontal spacing", "PR #106　（Storage 容量超過処理）", true],
  ["dash is not the required form", "PR #106 — Storage quota response", false],
  ["colon is not the required form", "PR #106: Storage quota response", false],
  ["empty parentheses", "PR #106()", false],
  ["blank parentheses", "PR #106（　）", false],
  ["newline cannot supply description", "PR #106\n(Storage quota response)", false],
  ["multiline multiple PRs", "PR #106（Storage 容量超過処理）\n\nPR #107(Write permission)", true],
  ["every new number needs a description", "PR #106（Storage 容量超過処理）\nPR #107", false],
  ["nonhash issue numbers unchanged", "Issue 106 and row902 remain open.", true],
  ["existing issue hash rule retained", "Issue #106", false],
  ["existing issue descriptions retained", "Issue #106(Storage quota response)", true],
  ["existing inheritance retained", "#106(Storage quota response) is ready; #106 CI is green", true],
  ["bare before description still refused", "#106 ready; #106(Storage quota response)", false],
  ["existing URL exemption", "https://example.test/pull/106#123", true],
  ["existing code exemption", "The literal `PR #106` is fixture data.", true],
  ["existing fenced data exemption", "Fixture\n```\nPR #106\n```", true],
  ["existing colour/entity exemption", "Use #589abc, &#8212;", true],
];

describe("canonical operator rule remains one policy", () => {
  for (const [label,text,expected] of cases) {
    test(label, () => {
      let allowed=true;
      try { assertLabeledPrReferences(text); } catch { allowed=false; }
      expect(allowed).toBe(expected);
    });
  }
});

const context={host:"synthetic-host",project:"/synthetic",agent_id:"fixture-agent",bot_token_hash:"synthetic"};
function deps(events: string[]): DurableSendDeps {
  return {
    async initStore(){events.push("store:init");},
    async resolveInboundReplyTarget(chatId,messageId){events.push("store:resolve");return {rowId:1,chatId,messageId,readAt:null,repliedAt:null};},
    async sendMessage(_chatId,text){events.push("send:"+text);return 7001;},
    async saveExplicitReply(){events.push("store:reply");return 2;},
    async saveOutbound(){events.push("store:outbound");return 2;},
  };
}

test("CLI bare PR refuses before store/correlation/send side effects", async () => {
  const events:string[]=[];let refused=false;
  try {await executeDurableSend({chatId:"synthetic",text:"PR #106",replyTo:11},context,deps(events));}
  catch(error){refused=String(error).includes("parenthesis after the number");}
  expect({refused,events}).toEqual({refused:true,events:[]});
});

test("CLI described PR preserves exact durable send text and ordering", async () => {
  const events:string[]=[];const text="PR #106（Storage 容量超過処理）";
  await executeDurableSend({chatId:"synthetic",text,replyTo:11},context,deps(events));
  expect(events).toEqual(["store:init","store:resolve","send:"+text,"store:reply"]);
});

for (const [name,send] of [
  ["common message",()=>sendMessage("synthetic","PR #106")],
  ["common edit",()=>editMessageText("synthetic",1,"PR #106")],
  ["common document caption",()=>sendDocument("synthetic",join(import.meta.dir,"outbound-style.test.ts"),"PR #106")],
] as const) {
  test(name+" refuses before loopback transport",async()=>{
    const requests=(globalThis as any).__STYLE_REQUESTS;const before=requests.length;let refused=false;
    try {await send();} catch(error){refused=String(error).includes("parenthesis after the number");}
    expect({refused,newRequests:requests.length-before}).toEqual({refused:true,newRequests:0});
  });
}

test("invalid document caption is refused before even opening absent file",async()=>{
  await expect(sendDocument("synthetic",join(import.meta.dir,"does-not-exist"),"PR #106")).rejects.toThrow("parenthesis after the number");
});

test("described message/edit/document payloads reach only synthetic loopback unchanged",async()=>{
  const requests=(globalThis as any).__STYLE_REQUESTS;const before=requests.length;const text="PR #106（Storage 容量超過処理）";
  await sendMessage("synthetic",text);await editMessageText("synthetic",1,text);await sendDocument("synthetic",join(import.meta.dir,"outbound-style.test.ts"),text);
  expect(requests.slice(before).map((r:any)=>r.data.text ?? r.data.caption)).toEqual([text,text,text]);
});


test("inheritance survives transport splitting without another policy", async () => {
  const requests=(globalThis as any).__STYLE_REQUESTS; const before=requests.length;
  const text="#106(Description) " + "x".repeat(4500) + " #106 completed";
  await sendMessage("synthetic",text);
  expect(requests.slice(before).map((r:any)=>r.data.text).join("")).toBe(text);
});

test("late undescribed reference refuses before sending the first chunk", async () => {
  const requests=(globalThis as any).__STYLE_REQUESTS; const before=requests.length;
  const text="#106(Description) " + "x".repeat(4500) + " #107";
  let refused=false;
  try { await sendMessage("synthetic",text); } catch { refused=true; }
  expect({refused,newRequests:requests.length-before}).toEqual({refused:true,newRequests:0});
});
