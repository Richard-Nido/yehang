import { visibleMetrics } from "./preferences.js";
import { plot } from "./charts.js";
import { $, $$, state, icon, esc, fmt, api, toast } from "./shared.js";
const metrics = {
  recovery: ["身体恢复度", "分", "spark", "#267a68", "#d6f3e4"],
  stress: ["日级生理压力", "分", "hrv", "#7951a1", "#efe2ff"],
  sleep: ["睡眠", "分钟", "sleep", "#775f9d", "#efe8f7"],
  resting_hr: ["静息心率", "bpm", "heart", "#a34560", "#fae8eb"],
  hrv_sdnn: ["心率变异性", "ms", "hrv", "#247e73", "#e2f3ed"],
  heart_rate: ["心率", "bpm", "pulse", "#bd6244", "#ffede3"],
  steps: ["步数", "步", "steps", "#39754b", "#e4f0df"],
  active_energy: ["活动能量", "kcal", "energy", "#996e28", "#f8eed3"],
};
let active = "sleep",
  explanations = new Map();
export function clearExplanation(profile) {
  if (!profile) {
    explanations.clear();
    return;
  }
  for (const key of explanations.keys())
    if (JSON.parse(key)[0] === profile) explanations.delete(key);
}
const score = (m) => m === "stress" || m === "recovery";
const bars = (m) => ["sleep", "steps", "active_energy"].includes(m);
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
  if (!visibleMetrics().includes(active)) active = visibleMetrics()[0];
  const any = Object.values(d.series).some((row) => row.some((v) => v != null));
  $("#screen").innerHTML =
    `<section class="hero"><small class="inline">${icon("rest")} 建议休息时段</small><h2>${r ? r.start.slice(11, 16) + " – " + r.end.slice(11, 16) : "七日内暂无空档"}</h2><p>${r ? fmt(r.start).slice(0, 5) + " · 短休 " + r.minutes + " 分钟" : "可在七日安排中调整日程"}</p><div class="wrap"><button class="ghost inline" id="heroGo">${r ? "调整休息计划" : "查看七日安排"} ${icon("arrow")}</button>${!any ? '<a href="#data" class="herolink">导入我的数据 ↗</a><button id="firstDemo" class="herolink">体验示例</button>' : ""}</div></section>
 <section class="section"><div class="panelhead"><h2>生理指标</h2><small>${d.day.slice(5).replace("-", "/")} · 点选查看走势</small></div><div class="grid">${Object.entries(
   metrics,
 )
   .filter(([m]) => visibleMetrics().includes(m))
   .map(
     ([m, [label, , i, c, bg]]) =>
       `<button class="card ${score(m) ? "computed" : ""} ${m === active ? "sel" : ""}" aria-pressed="${m === active}" data-m="${m}" style="--accent:${c};--tint:${bg}"><span class="cardtop"><span class="bubble">${icon(i)}</span>${label}</span>${score(m) ? '<small class="calculated">自研算法估算</small>' : ""}<div class="cardnum">${num(m, d.series[m].at(-1))}</div>${plot(d.series[m], c, false, bars(m), score(m))}</button>`,
   )
   .join("")}</div></section>
 <div class="duo"><section class="panel"><div class="panelhead"><h3 id="trendTitle"></h3><small id="trendRange">近 7 日</small></div><div id="trend"></div><div class="chartDays">${d.days.map((x, i) => `<button data-point="${i}" aria-label="查看 ${x}">${x.slice(5).replace("-", "/")}</button>`).join("")}</div><p id="pointValue" class="detail"></p></section><section class="panel"><div class="panelhead"><h3 class="inline">${icon("spark")} 身体解读</h3><button class="quiet" id="retry" hidden>重试</button></div><div id="insight" class="text" aria-live="polite">${any ? "正在读取解读…" : "上传 Apple 健康导出文件，即可查看自己的睡眠、心率和活动变化。"}</div>${any ? "" : '<a class="button inline" href="#data">导入健康数据 →</a>'}</section></div>
 `;
  if ($("#firstDemo")) $("#firstDemo").onclick = () => $("#profile").click();
  $("#heroGo").onclick = () => (location.hash = r ? "rest" : "schedule");
  let point = 6;
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
    $("#trend").innerHTML = plot(
      d.series[active],
      color,
      true,
      bars(active),
      score(active),
      point,
    );
    $("#pointValue").textContent =
      d.days[point] +
      " · " +
      name +
      " " +
      (d.series[active][point] == null
        ? "暂无记录"
        : Math.round(d.series[active][point]) + " " + unit);
    $$("[data-point]").forEach((el) => {
      el.setAttribute("aria-pressed", String(+el.dataset.point === point));
      el.onclick = () => {
        point = +el.dataset.point;
        draw();
      };
    });
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
      target.innerHTML = `<div class="source">${j.source === "api" ? "模型解读" : j.source === "empty" ? "数据不足" : "模型调用失败 · 离线规则解读"}</div><ul class="insightList">${(j.items?.length ? j.items : [j.text]).map((t) => `<li>${esc(t)}</li>`).join("")}</ul>`;
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
