import { $, $$, state, icon, esc, fmt, api, toast } from "./shared.js";
const metrics = {
  sleep: ["睡眠", "分钟", "sleep", "#775f9d", "#efe8f7"],
  resting_hr: ["静息心率", "bpm", "heart", "#a34560", "#fae8eb"],
  hrv_sdnn: ["心率变异性", "ms", "hrv", "#247e73", "#e2f3ed"],
  heart_rate: ["心率", "bpm", "pulse", "#bd6244", "#ffede3"],
  steps: ["步数", "步", "steps", "#39754b", "#e4f0df"],
  active_energy: ["活动能量", "kcal", "energy", "#996e28", "#f8eed3"],
};
let active = "sleep",
  explanations = new Map();
export function clearExplanation() {
  explanations.clear();
}
function chart(values, color, large = false) {
  const valid = values.filter((v) => v != null),
    w = 260,
    h = large ? 100 : 30;
  if (!valid.length)
    return `<div class="${large ? "bigchart" : "spark"}" style="display:grid;align-items:center;color:#73847c;font-size:12px">${large ? "这七天还没有可绘制的记录" : "暂无记录"}</div>`;
  const min = Math.min(...valid),
    max = Math.max(...valid),
    span = max - min || 1;
  let last = null,
    lines = "",
    dots = "";
  values.forEach((v, i) => {
    if (v == null) {
      last = null;
      return;
    }
    const x = 5 + (i * (w - 10)) / 6,
      y = max === min ? h / 2 : 5 + (h - 10) * (1 - (v - min) / span);
    if (last) lines += `M${last[0]},${last[1]} L${x},${y} `;
    dots += `<circle cx="${x}" cy="${y}" r="${large ? 3 : 2}" fill="${color}"><title>${state.data.days[i]} · ${v}</title></circle>`;
    last = [x, y];
  });
  return `<svg role="img" aria-label="七日走势，${values.map((v) => (v == null ? "缺测" : Math.round(v))).join("，")}" class="${large ? "bigchart" : "spark"}" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">${large ? [0.15, 0.5, 0.85].map((y) => `<path d="M0 ${h * y}h${w}" stroke="#dce4db" stroke-dasharray="3 5"/>`).join("") : ""}<path d="${lines}" fill="none" stroke="${color}" stroke-width="${large ? 2.5 : 1.8}" vector-effect="non-scaling-stroke"/>${dots}</svg>`;
}
function num(m, v) {
  if (v == null) return "—";
  if (m === "sleep") {
    let n = Math.round(v);
    return `${Math.floor(n / 60)}<small>小时</small> ${n % 60}<small>分</small>`;
  }
  return (
    Math.round(v).toLocaleString("zh-CN") + `<small>${metrics[m][1]}</small>`
  );
}
export function home(refresh) {
  const d = state.data,
    r = d.recommendation;
  $("#action").innerHTML =
    `<label><span class="offscreen">观察日期</span><input class="control" type="date" value="${d.day}" id="obsDay" max="${d.now.slice(0, 10)}"></label>`;
  $("#obsDay").onchange = (e) => {
    state.day = e.target.value;
    refresh();
  };
  const any = Object.values(d.series).some((row) => row.some((v) => v != null));
  $("#screen").innerHTML =
    `<section class="hero"><small class="inline">${icon("rest")} 建议休息时段</small><h2>${r ? r.start.slice(11, 16) + " – " + r.end.slice(11, 16) : "七日内暂无空档"}</h2><p>${r ? fmt(r.start).slice(0, 5) + " · 短休 " + r.minutes + " 分钟" : "可在七日安排中调整日程"}</p><div class="wrap"><button class="ghost inline" id="heroGo">${r ? "调整休息计划" : "查看七日安排"} ${icon("arrow")}</button>${!any ? '<a href="#data" class="herolink">导入我的数据 ↗</a><button id="firstDemo" class="herolink">体验示例</button>' : ""}</div></section>
 <section class="section"><div class="panelhead"><h2>生理指标</h2><small>${d.day.slice(5).replace("-", "/")} · 点选查看走势</small></div><div class="grid">${Object.entries(
   metrics,
 )
   .map(
     ([m, [label, , i, c, bg]]) =>
       `<button class="card ${m === active ? "sel" : ""}" aria-pressed="${m === active}" data-m="${m}" style="--accent:${c};--tint:${bg}"><span class="cardtop"><span class="bubble">${icon(i)}</span>${label}</span><div class="cardnum">${num(m, d.series[m].at(-1))}</div>${chart(d.series[m], c)}</button>`,
   )
   .join("")}</div></section>
 <div class="duo"><section class="panel"><div class="panelhead"><h3 id="trendTitle"></h3><small id="trendRange">近 7 日</small></div><div id="trend"></div><div class="axis">${d.days.map((x) => `<span>${x.slice(5).replace("-", "/")}</span>`).join("")}</div></section><section class="panel"><div class="panelhead"><h3 class="inline">${icon("spark")} 身体解读</h3><button class="quiet" id="retry" hidden>重试</button></div><div id="insight" class="text" aria-live="polite">${any ? "正在读取解读…" : "上传 Apple 健康导出文件，即可查看自己的睡眠、心率和活动变化。"}</div>${any ? "" : '<a class="button inline" href="#data">导入健康数据 →</a>'}</section></div>
 ${d.recovery != null || d.stress != null ? `<div class="panel section"><h3>个人基线对照</h3><p class="note">身体恢复度 ${d.recovery ?? "资料不足"}　·　日级生理压力 ${d.stress ?? "资料不足"}。分值为探索性估计。</p></div>` : ""}`;
  if ($("#firstDemo")) $("#firstDemo").onclick = () => $("#profile").click();
  $("#heroGo").onclick = () => (location.hash = r ? "rest" : "schedule");
  function draw() {
    const [name, unit, , color] = metrics[active];
    $("#trendTitle").textContent = name + " · " + unit;
    const valid = d.series[active].filter((v) => v != null);
    $("#trendRange").textContent =
      "近 7 日" +
      (valid.length
        ? " · " +
          Math.round(Math.min(...valid)) +
          "–" +
          Math.round(Math.max(...valid)) +
          " " +
          unit
        : "");
    $("#trend").innerHTML = chart(d.series[active], color, true);
  }
  $$("[data-m]").forEach(
    (el) =>
      (el.onclick = () => {
        active = el.dataset.m;
        $$("[data-m]").forEach((x) => {
          x.classList.toggle("sel", x === el);
          x.setAttribute("aria-pressed", x === el);
        });
        draw();
      }),
  );
  draw();
  if (!any) return;
  const key = JSON.stringify([d.profile, d.day, d.series, d.partial]);
  const target = $("#insight");
  async function explain(force) {
    try {
      if (force || !explanations.has(key))
        explanations.set(
          key,
          api("explanation", { profile: d.profile, day: d.day }),
        );
      const j = await explanations.get(key);
      if (!target.isConnected) return;
      target.innerHTML = `<div class="source">${j.source === "api" ? "模型解读" : j.source === "empty" ? "数据不足" : "模型调用失败 · 离线规则解读"}</div>${esc(j.text)}`;
      $("#retry").hidden = j.source !== "offline";
      $("#retry").onclick = () => {
        target.textContent = "正在请求模型…";
        explain(true);
      };
    } catch (e) {
      explanations.delete(key);
      if (target.isConnected) target.textContent = e.message;
    }
  }
  explain(false);
}
