import { syncPanel, bindSync } from "./health-sync.js";
import { preferences } from "./preferences.js";
import {
  $,
  $$,
  state,
  esc,
  icon,
  modal,
  close,
  api,
  toast,
  busy,
  upload,
  dropZone,
  bindDrop,
  weekday,
} from "./shared.js";
import { home, clearExplanation } from "./home.js";
import { schedulePage } from "./schedule.js";
import { restPage, reviewPage } from "./rest.js";
const pages = {
  home: ["总览", "健康总览", "home", home],
  schedule: ["七日安排", "七日安排", "calendar", schedulePage],
  rest: ["休息计划", "休息计划", "rest", restPage],
  review: ["复盘", "七日复盘", "review", reviewPage],
  data: ["数据输入", "数据输入", "data", dataPage],
};
$("#nav").innerHTML = Object.entries(pages)
  .map(
    ([id, [short, , i]]) =>
      `<a class="navItem" href="#${id}">${icon(i)}<span>${short}</span></a>`,
  )
  .join("");
$("#settings").innerHTML = icon("settings") + "设置";
$("#settings").onclick = () => preferences(refresh, settings, clearExplanation);
$("main").insertAdjacentHTML(
  "afterbegin",
  `<div class="mobilebrand"><a href="#home" class="inline"><img src="/assets/mark.svg" alt=""><b>夜航</b></a><div class="mobiletools"><button class="chip" id="mProfile"></button><button class="ghost" aria-label="设置" id="mSettings">${icon("settings")}</button></div></div>`,
);
$("#mSettings").onclick = () =>
  preferences(refresh, settings, clearExplanation);
async function switchProfile(p) {
  state.p = p;
  localStorage.setItem("yh-profile", p);
  state.day = "";
  state.week = "";
  state.scheduleStart = "";
  close();
  await refresh();
}
function profiles() {
  modal(
    "选择档案",
    `<div class="stack"><div class="panel"><h3>我的档案</h3><p class="note">使用本机保存的健康记录和日程。</p><button id="mine" class="primary">进入我的档案</button></div><div class="panel"><h3>体验示例</h3><p class="note">用一周虚构排班和健康数据体验完整流程。示例时钟固定在 11 月 3 日。</p><button id="demo" class="ghost">打开示例档案</button></div></div>`,
  );
  $("#mine").onclick = () => switchProfile("personal-main");
  $("#demo").onclick = () => switchProfile("synthetic-demo");
}
$("#profile").onclick = profiles;
$("#mProfile").onclick = profiles;
const protocolOptions = [
  ["chat", "OpenAI Chat Completions"],
  ["responses", "OpenAI Responses"],
  ["anthropic", "Anthropic Messages"],
  ["gemini", "Google Gemini"],
];
async function settings(scope = "text") {
  const cfg = await api("provider?scope=" + scope);
  const text = scope === "text";
  const b = modal(
    "模型设置",
    `<div class="wrap"><button class="chip ${text ? "on" : ""}" id="pText">生理解读</button><button class="chip ${text ? "" : "on"}" id="pVision">排班识别</button></div><p class="note">${text ? "保存后自动使用该服务解释每日生理汇总。原始健康文件保留在本机。" : "默认使用生理解读的服务。若它不支持图片，可在这里单独指定视觉服务。"}</p>
 <form id="providerForm"><label class="field">Base URL<input id="base" type="url" required placeholder="https://api.example.com/v1" value="${esc(cfg.base)}"></label>
 <label class="field">接口协议<select id="proto">${protocolOptions.map(([id, n]) => `<option value="${id}" ${cfg.protocol === id ? "selected" : ""}>${n}</option>`).join("")}</select></label>
 <label class="field">API Key<input id="key" type="password" autocomplete="off" placeholder="${cfg.base ? "使用已保存的密钥，或输入新密钥" : "输入供应商密钥"}"></label>
 <label class="field">模型名称<input id="model" required placeholder="选择或输入供应商的模型 ID" value="${esc(cfg.model)}"></label><section id="availableModels" class="modelPicker" hidden><label class="field">选择可用模型<input type="search" id="filterModels" placeholder="搜索全部模型"></label><div id="modelList" class="modelOptions" role="group" aria-label="可用模型"></div></section>
 <div class="wrap"><button type="button" class="ghost" id="models">获取模型列表</button><button type="submit" class="primary">保存配置</button></div><p class="detail" id="providerMsg" role="status"></p></form>${!text && cfg.independent ? '<button id="inherit" class="quiet">改用生理解读的服务</button>' : ""}`,
  );
  const raw = () => ({
    scope,
    base: $("#base", b).value.trim(),
    protocol: $("#proto", b).value,
    key: $("#key", b).value.trim(),
    model: $("#model", b).value.trim(),
  });
  $("#pText").onclick = () => settings("text");
  $("#pVision").onclick = () => settings("vision");
  $("#models").onclick = async () => {
    const msg = $("#providerMsg");
    msg.textContent = "正在读取供应商模型…";
    try {
      const j = await api("models", raw());
      if (!b.contains(msg)) return;
      const ids = [
        ...new Set(j.models.filter((m) => typeof m === "string" && m.trim())),
      ];
      const box = $("#availableModels", b),
        list = $("#modelList", b),
        search = $("#filterModels", b),
        field = $("#model", b);
      box.hidden = false;
      function options() {
        const matches = ids.filter((m) =>
          m.toLowerCase().includes(search.value.trim().toLowerCase()),
        );
        list.replaceChildren();
        for (const name of matches) {
          const choice = document.createElement("button");
          choice.type = "button";
          choice.className = "modelOption";
          choice.textContent = name;
          choice.setAttribute("aria-pressed", String(field.value === name));
          choice.onclick = () => {
            field.value = name;
            options();
            msg.textContent = "已选择 " + name + "，点击保存配置生效。";
          };
          list.append(choice);
        }
        if (!matches.length)
          list.textContent = "没有匹配的模型，可手动填写名称。";
      }
      search.value = "";
      search.oninput = options;
      field.oninput = options;
      options();
      msg.textContent = `已读取 ${ids.length} 个模型。点选上方列表，或直接填写模型名称。`;
      search.focus();
    } catch (e) {
      msg.textContent = e.message + " 也可手动输入模型名称。";
    }
  };
  $("#providerForm").onsubmit = async (e) => {
    e.preventDefault();
    try {
      await api("provider", raw());
      clearExplanation();
      close();
      toast("已保存模型配置");
      await refresh();
    } catch (err) {
      $("#providerMsg").textContent = err.message;
    }
  };
  if ($("#inherit"))
    $("#inherit").onclick = async () => {
      await api("provider/inherit", {});
      close();
      toast("排班识别已改用生理解读的服务");
    };
}
function dataPage(refresh) {
  const demo = state.p === "synthetic-demo";
  $("#screen").innerHTML =
    `${demo ? "" : syncPanel()}<section class="panel section"><h2>导入健康记录</h2><p class="note">在 iPhone 的「健康 → 头像 → 导出所有健康数据」导出并解压，选择 export.xml。也支持夜航格式的个人 JSON。</p>${demo ? "<button id='personalImport' class='primary'>切换到我的档案并导入</button>" : dropZone("health", ".xml,.json", "将健康文件拖放到这里", "XML 或 JSON · 单个文件最大 1 GB")}<p class="detail section">系统自动合并重复记录，并按上海时间归日。</p></section><section class="panel section"><div class="row"><div><h3>排班表</h3><p class="detail">从 Office 文件、PDF 或图片识别班次，也可逐日点选。</p></div><a class="button" href="#schedule">导入排班</a></div></section>`;
  if (demo) {
    $("#personalImport").onclick = () => switchProfile("personal-main");
    return;
  }
  bindSync(refresh);
  bindDrop("health", async (f) => {
    const j = await upload("health", f);
    state.day = "";
    await refresh();
    busy(null);
    modal(
      "导入完成",
      `<p class="text">新增 ${j.added} 条记录，已合并 ${j.duplicate} 条重复记录。${j.invalid + j.conflict ? `另有 ${j.invalid + j.conflict} 条记录格式无效或内容冲突，已跳过。` : ""}</p><button id="seeHome" class="primary section">查看健康总览</button>`,
    );
    $("#seeHome").onclick = () => {
      close();
      location.hash = "home";
    };
  });
}
let run = 0;
let lastPage = null;
async function refresh() {
  const token = ++run;
  const id = location.hash.slice(1);
  state.page = pages[id] ? id : "home";
  const [short, title, , render] = pages[state.page];
  document.title = title + " · 夜航";
  $("#title").textContent = title;
  $("#action").innerHTML = "";
  $$("nav a").forEach((el) => {
    if (el.hash === "#" + state.page) el.setAttribute("aria-current", "page");
    else el.removeAttribute("aria-current");
  });
  const label = state.p === "synthetic-demo" ? "示例档案" : "我的档案";
  $("#profileLabel").textContent = label;
  $("#mProfile").textContent = label;
  try {
    const params = new URLSearchParams({
      profile: state.p,
      ...(state.day && { day: state.day }),
      ...(state.week && { week: state.week }),
      ...(state.scheduleStart && { scheduleStart: state.scheduleStart }),
    });
    const d = await api("state?" + params);
    if (token !== run) return;
    state.data = d;
    const date = d.now.slice(0, 10);
    $("#kicker").textContent =
      (state.p === "synthetic-demo" ? "示例 · " : "") +
      Number(date.slice(5, 7)) +
      " 月 " +
      Number(date.slice(8)) +
      " 日　" +
      weekday(date);
    render(refresh);
    if (
      lastPage &&
      lastPage !== state.page &&
      document.documentElement.dataset.motion !== "reduce" &&
      !matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      $("#screen").animate(
        [
          { opacity: 0.55, transform: "translateY(5px)" },
          { opacity: 1, transform: "none" },
        ],
        { duration: 180, easing: "cubic-bezier(.2,.75,.25,1)" },
      );
    }
    lastPage = state.page;
  } catch (e) {
    if (token === run) {
      $("#screen").innerHTML =
        `<div class="panel"><p>${esc(e.message)}</p><button class="ghost" id="reload">重新读取</button></div>`;
      $("#reload").onclick = refresh;
    }
  }
}
window.addEventListener("unhandledrejection", (e) => {
  e.preventDefault();
  toast(e.reason?.message || "操作未完成");
});
window.addEventListener("hashchange", () => {
  window.scrollTo(0, 0);
  refresh();
});
refresh();

// 有新批次时刷新当前个人页面；没有变化时不重复触发分析或打断编辑。
let syncRevision;
setInterval(async () => {
  if (state.p !== "personal-main" || document.hidden || document.querySelector("dialog[open]") ||
      document.activeElement?.matches("input,textarea,select")) return;
  try {
    const s = await api("health-sync");
    if (syncRevision !== undefined && s.last_sync !== syncRevision) { clearExplanation(); await refresh(); }
    syncRevision = s.last_sync;
  } catch (_) { /* 服务未运行时沿用当前页面 */ }
}, 5000);
