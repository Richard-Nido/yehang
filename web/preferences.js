import { $, $$, api, state, modal, close, toast, esc } from "./shared.js";

export const metricNames = {
  sleep: "睡眠",
  resting_hr: "静息心率",
  hrv_sdnn: "心率变异性",
  heart_rate: "心率",
  steps: "步数",
  active_energy: "活动能量",
  recovery: "身体恢复度",
  stress: "日级生理压力",
};
const defaults = { size: "standard", motion: "auto", hidden: [] };
const key = "yh-display-v2";
let prefs = { ...defaults };
try {
  Object.assign(prefs, JSON.parse(localStorage.getItem(key) || "{}"));
} catch {}
export function visibleMetrics() {
  return Object.keys(metricNames).filter((m) => !prefs.hidden.includes(m));
}
function apply() {
  document.documentElement.dataset.type = prefs.size;
  document.documentElement.dataset.motion = prefs.motion;
}
function save() {
  localStorage.setItem(key, JSON.stringify(prefs));
  apply();
}
apply();

export function preferences(refresh, models, clearCache) {
  const profile = state.p === "synthetic-demo" ? "示例档案" : "我的档案";
  modal(
    "设置",
    `<section class="prefgroup"><h3>显示与阅读</h3><label class="prefrow">文字大小<select id="fontSize"><option value="standard">标准</option><option value="large">大</option><option value="larger">特大</option></select></label><label class="prefrow">动态效果<select id="motion"><option value="auto">跟随系统</option><option value="reduce">减少动态效果</option></select></label><details><summary>总览显示的指标</summary><div class="checkgrid">${Object.entries(
      metricNames,
    )
      .map(
        ([id, name]) =>
          `<label><input type="checkbox" data-visible="${id}" ${prefs.hidden.includes(id) ? "" : "checked"}> ${name}</label>`,
      )
      .join("")}</div></details></section>
 <section class="prefgroup"><h3>模型服务</h3><button class="prefrow" id="configModels">配置文字与排班模型 <span>›</span></button></section>
 <section class="prefgroup"><h3>数据与历史</h3><small>当前范围 · ${profile}</small><button class="prefrow" id="clearCache">清理解读缓存 <span>›</span></button>
 ${Object.entries({
   health: "健康导入",
   schedule: "日程历史",
   feedback: "复盘反馈",
   plans: "休息计划与反馈",
 })
   .map(
     ([id, name]) =>
       `<button class="prefrow" data-clear="${id}">清除${name}<span>›</span></button>`,
   )
   .join("")}</section><button class="primary" id="prefDone">完成</button>`,
  );
  $("#fontSize").value = prefs.size;
  $("#motion").value = prefs.motion;
  $("#fontSize").onchange = (e) => {
    prefs.size = e.target.value;
    save();
  };
  $("#motion").onchange = (e) => {
    prefs.motion = e.target.value;
    save();
  };
  $$("[data-visible]").forEach(
    (el) =>
      (el.onchange = () => {
        const checked = $$("[data-visible]:checked");
        if (!checked.length) {
          el.checked = true;
          return toast("请至少保留一个指标");
        }
        prefs.hidden = $$("[data-visible]:not(:checked)").map(
          (x) => x.dataset.visible,
        );
        save();
        if (state.page === "home") refresh();
      }),
  );
  $("#prefDone").onclick = () => {
    close();
    refresh();
  };
  $("#configModels").onclick = () => models("text");
  $("#clearCache").onclick = () => {
    clearCache(state.p);
    toast("已清除当前档案的解读缓存");
  };
  $$("[data-clear]").forEach(
    (el) =>
      (el.onclick = async () => {
        const group = el.dataset.clear,
          p = state.p;
        const info = await api(
          `history?profile=${encodeURIComponent(p)}&group=${group}`,
        );
        modal(
          "确认清除历史",
          `<p class="text">将从「${profile}」永久清除${esc(info.impact)}。</p><div class="wrap section"><button class="ghost" id="cancelClear">取消</button><button class="danger" id="acceptClear">确认清除</button></div>`,
        );
        $("#cancelClear").onclick = () =>
          preferences(refresh, models, clearCache);
        $("#acceptClear").onclick = async () => {
          await api("history/clear", {
            profile: p,
            group,
            revision: info.revision,
          });
          clearCache(p);
          close();
          await refresh();
          toast("所选历史已清除");
        };
      }),
  );
}
