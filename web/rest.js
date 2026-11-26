import { feedbackDraft } from "./feedback-draft.js";
import {
  $,
  $$,
  state,
  esc,
  fmt,
  icon,
  sh,
  at,
  daysFrom,
  api,
  payload,
  timeWheel,
  toast,
  modal,
  close,
} from "./shared.js";
export function restPage(refresh, initial) {
  const d = state.data,
    r = d.recommendation;
  const fallback = d.now.slice(0, 16) + "+08:00";
  let start = new Date(initial?.start || r?.start || fallback).getTime(),
    end = new Date(initial?.end || r?.end || start + 20 * 60000).getTime();
  const existing = initial?.id;
  $("#action").innerHTML = '<a class="button" href="#schedule">查看日程</a>';
  $("#screen").innerHTML =
    `<div class="panel"><div class="panelhead"><h2>${existing ? "调整已存计划" : r ? "推荐短休" : "自选休息时段"}</h2><span class="bubble" style="--tint:#e5f0e3;--accent:#3c6e53">${icon("rest")}</span></div>
 <p class="note">${existing ? "可移动开始时间或调整时长。" : r ? esc(r.reason) : "当前七天没有满足条件的推荐窗口。你仍可自行安排。"}</p><div class="timeval" id="clockDisplay"></div><small id="spanLabel"></small>
 <div class="timeline"><div class="track" id="track"><div id="segment" class="segment" title="拖动以移动休息时段"><i class="handle" title="拖动以调整时长"></i></div></div><div class="axis"><span id="axisStart"></span><span>拖动色块移动 · 拖动右端调整时长</span><span id="axisEnd"></span></div></div>
 <label class="field">休息时长 <input class="range" id="duration" type="range" min="1" step="1"></label><div class="wrap"><button class="ghost" id="startTime">选择开始时间</button><button class="ghost" id="endTime">选择结束时间</button></div><p id="conflict" class="warn" hidden></p>
 <div class="row section"><small>起止日期和时间均可自由调整</small><button class="primary" id="savePlan">保存休息计划</button></div></div>
 <section class="panel section"><h2>接下来的计划</h2>${d.plans.length ? d.plans.map((p, i) => `<div class="entry"><span class="bubble">${icon("clock")}</span><div><b>${fmt(p.start)} – ${fmt(p.end)}</b><p class="detail">${p.minutes} 分钟</p></div><button class="quiet" data-edit="${i}">调整</button><button class="ghost" data-review="${i}">反馈</button></div>`).join("") : '<p class="empty">保存后，你的休息计划会显示在这里。</p>'}</section>
 <details><summary>推荐依据</summary><p class="note">在未来七天的空档中比较开始时间、目标时长和工作前缓冲。近期睡眠与个人基线、恢复信号都会影响排序。资料不足时参考 20 分钟短休，睡眠偏少时优先预留 30 分钟。具体阈值为 Beta 版设计参数。${r?.assumed ? "未标记可休息时段时，按日间或夜班前后的空档估算。" : ""}建议仅供成人日程安排参考。</p><a class="quiet" href="https://pubmed.ncbi.nlm.nih.gov/16796222/" target="_blank" rel="noreferrer">短时小睡研究 ↗</a></details>`;
  const track = $("#track"),
    seg = $("#segment"),
    slider = $("#duration");
  let left,
    width,
    drag = null;
  function scale() {
    width = Math.max(120, ((end - start) / 60000) * 2) * 60000;
    left = start - width * 0.22;
  }
  function paint(rescale = true) {
    if (rescale) scale();
    const a = sh(start),
      b = sh(end),
      mins = Math.round((end - start) / 60000);
    $("#clockDisplay").textContent = a.slice(11, 16) + " – " + b.slice(11, 16);
    $("#spanLabel").textContent =
      fmt(a) + " 至 " + fmt(b) + " · " + mins + " 分钟";
    $("#startTime").textContent = "开始　" + fmt(a);
    $("#endTime").textContent = "结束　" + fmt(b);
    seg.style.left = Math.max(0, ((start - left) / width) * 100) + "%";
    seg.style.width =
      Math.max(0.5, Math.min(100, ((end - start) / width) * 100)) + "%";
    $("#axisStart").textContent = sh(left).slice(11, 16);
    $("#axisEnd").textContent = sh(left + width).slice(11, 16);
    slider.max = Math.max(120, mins);
    slider.value = mins;
    slider.setAttribute("aria-valuetext", mins + " 分钟");
    const hits = d.blocks
      .filter(
        (x) =>
          !["rest", "available"].includes(x.kind) &&
          Date.parse(x.start) < end &&
          Date.parse(x.end) > start,
      )
      .map((x) => x.title);
    for (const p of d.plans)
      if (
        p.id !== existing &&
        Date.parse(p.start) < end &&
        Date.parse(p.end) > start
      )
        hits.push("已保存的休息计划");
    $("#conflict").hidden = !hits.length;
    $("#conflict").textContent =
      "与" + hits.join("、") + "重叠。你仍可保存自己的安排。";
  }
  slider.oninput = () => {
    end = start + Number(slider.value) * 60000;
    paint();
  };
  seg.onpointerdown = (e) => {
    e.preventDefault();
    drag = {
      x: e.clientX,
      a: start,
      b: end,
      resize: e.target.classList.contains("handle"),
    };
    seg.setPointerCapture(e.pointerId);
  };
  seg.onpointermove = (e) => {
    if (!drag) return;
    const shift =
      Math.round((((e.clientX - drag.x) / track.clientWidth) * width) / 60000) *
      60000;
    if (drag.resize) end = Math.max(start + 60000, drag.b + shift);
    else {
      start = drag.a + shift;
      end = drag.b + shift;
    }
    paint(false);
  };
  seg.onlostpointercapture = () => {
    drag = null;
    paint();
  };
  $("#startTime").onclick = () =>
    timeWheel("休息开始", sh(start), (v) => {
      const diff = end - start;
      start = Date.parse(v);
      end = start + diff;
      paint();
    });
  $("#endTime").onclick = () =>
    timeWheel("休息结束", sh(end), (v) => {
      if (Date.parse(v) <= start) return toast("结束时间须晚于开始时间");
      end = Date.parse(v);
      paint();
    });
  $("#savePlan").onclick = async () => {
    await api(
      "plans",
      payload({ id: existing, start: sh(start), end: sh(end) }),
    );
    await refresh();
    toast("已保存休息计划");
  };
  $$("[data-review]").forEach(
    (el) =>
      (el.onclick = () => {
        const plan = d.plans[+el.dataset.review];
        state.week = plan.start.slice(0, 10);
        location.hash = "review";
      }),
  );
  $$("[data-edit]").forEach(
    (el) =>
      (el.onclick = () => {
        restPage(refresh, d.plans[+el.dataset.edit]);
        window.scrollTo({ top: 0, behavior: "instant" });
      }),
  );
  paint();
}
export function reviewPage(refresh) {
  const d = state.data;
  $("#action").innerHTML =
    `<label><span class="offscreen">复盘截至日期</span><input class="control" id="week" type="date" value="${d.weekEnd}"></label>`;
  $("#week").onchange = (e) => {
    state.week = e.target.value;
    refresh();
  };
  const done = d.reviews.filter((r) => r.status === "完成").length,
    observed = d.reviews.filter((r) => r.evidence.details.length).length;
  $("#screen").innerHTML =
    `<section class="panel soft"><small>${daysFrom(d.weekEnd, -6).slice(5)} 至 ${d.weekEnd.slice(5)}</small><h2>本周完成 ${done} 次休息</h2><p class="note">共 ${d.reviews.length} 项计划，${observed} 项有可对照的生理记录。</p></section>
 ${
   !d.reviews.length
     ? '<section class="panel section"><h3>这里会留下每一次休息</h3><p class="note">保存休息计划后可随时反馈。导入后续健康记录，便可对照休息前后的变化。</p><a class="button" href="#rest">查看休息建议 →</a></section>'
     : d.reviews
         .map(
           (r, i) =>
             `<section class="panel section"><div class="panelhead"><h3>${fmt(r.start)} – ${fmt(r.end)}</h3><small>${r.minutes} 分钟</small></div><div class="wrap">${["完成", "部分完成", "跳过"].map((s) => `<button class="chip" data-i="${i}" data-status="${s}" aria-pressed="${r.status === s}">${s}</button>`).join("")}</div>${
               ["完成", "部分完成"].includes(r.status)
                 ? `<div class="feel"><small>休息后感觉（选填）</small><div class="wrap">${[
                     [1, "精神不错"],
                     [3, "一般"],
                     [5, "仍感疲惫"],
                   ]
                     .map(
                       ([v, l]) =>
                         `<button class="chip" data-i="${i}" data-feel="${v}" aria-pressed="${r.fatigue === v}">${l}</button>`,
                     )
                     .join("")}</div></div>`
                 : ""
             }<button class="ghost freeform" data-draft="${i}">用自己的话复盘</button>${r.note ? `<p class="evidence">我的记录 · ${esc(r.note)}</p>` : ""}<div class="evidence"><b>${esc(r.evidence.state)}</b>${r.evidence.details.map((t) => `<p>${esc(t)}</p>`).join("")}</div>${r.evidence.details.length ? "<small>同时段睡眠和前后指标用于个人对照。单次变化难以判断恢复是否充分。</small>" : ""}</section>`,
         )
         .join("")
 }`;
  $$("[data-draft]").forEach(
    (el) =>
      (el.onclick = () => feedbackDraft(d.reviews[+el.dataset.draft], refresh)),
  );
  $$("[data-feel]").forEach(
    (el) =>
      (el.onclick = async () => {
        const r = d.reviews[+el.dataset.i];
        await api("feedback", payload({ ...r, fatigue: +el.dataset.feel }));
        await refresh();
        toast("已保存休息感受");
      }),
  );
  $$("[data-status]").forEach(
    (el) =>
      (el.onclick = async () => {
        const r = d.reviews[+el.dataset.i];
        await api("feedback", payload({ ...r, status: el.dataset.status }));
        await refresh();
        toast("已记录执行反馈");
      }),
  );
}
