export const $ = (s, root = document) => root.querySelector(s);
export const $$ = (s, root = document) => [...root.querySelectorAll(s)];
export const esc = (x) =>
  String(x ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const paths = {
  home: "M3 10l9-7 9 7v10h-6v-6H9v6H3z",
  calendar: "M4 5h16v16H4z M4 10h16 M8 3v5 M16 3v5",
  rest: "M20 14a8.5 8.5 0 0 1-10-11 9 9 0 1 0 10 11z",
  review: "M3 12a9 9 0 1 1 3 7 M3 5v7h7 M12 7v6l4 2",
  data: "M4 15v5h16v-5 M12 16V3 M7 8l5-5 5 5",
  settings:
    "M3 7h10m4 0h4M3 17h3m4 0h11 M17 7a2 2 0 1 0-4 0 2 2 0 1 0 4 0 M10 17a2 2 0 1 0-4 0 2 2 0 1 0 4 0",
  sleep: "M3 17h18M3 11v9m18-9v9M4 10h16l1 6H3z M5 10V7h14v3",
  heart: "M12 20S2 14 3 8c1-5 7-5 9-1 2-4 8-4 9 1 1 6-9 12-9 12z",
  hrv: "M2 13h5l3-8 4 15 3-9 2 2h3",
  pulse: "M3 12h3l3-6 4 13 3-10 2 3h3",
  steps:
    "M7 4c3-1 5 5 3 8-2 2-5 0-5-3 0-2 0-4 2-5z M16 10c3-1 5 5 3 8-2 2-5 0-5-3 0-2 0-4 2-5z M6 15l3 1 M15 21l3 1",
  energy:
    "M13 2c1 5-4 6-3 10 2-1 3-2 4-5 4 3 6 6 5 10a7.5 7.5 0 0 1-14-2c0-5 6-7 8-13z",
  arrow: "M5 12h14m-5-5 5 5-5 5",
  plus: "M12 5v14 M5 12h14",
  spark: "M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z",
  clock: "M21 12a9 9 0 1 1-18 0 9 9 0 1 1 18 0 M12 6v6l4 2",
  file: "M6 3h8l4 4v14H6z M14 3v5h4 M9 13h6 M9 17h6",
};
export const icon = (n) =>
  `<svg class="ic" aria-hidden="true" viewBox="0 0 24 24"><path d="${paths[n] || paths.file}"/></svg>`;
export const state = {
  p:
    localStorage.getItem("yh-profile") === "synthetic-demo"
      ? "synthetic-demo"
      : "personal-main",
  data: null,
  page: "home",
  day: "",
  week: "",
};
export const daysFrom = (date, n) =>
  new Date(Date.parse(date.slice(0, 10) + "T12:00:00Z") + n * 864e5)
    .toISOString()
    .slice(0, 10);
export const weekday = (date) =>
  new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    weekday: "short",
  }).format(new Date(date.slice(0, 10) + "T12:00:00+08:00"));
export const fmt = (t) =>
  t.slice(5, 10).replace("-", "/") + " " + t.slice(11, 16);
export const sh = (t) =>
  new Date(new Date(t).getTime() + 8 * 36e5).toISOString().slice(0, 16) +
  "+08:00";
export const at = (d, t) => d.slice(0, 10) + "T" + t.slice(0, 5) + ":00+08:00";
export function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (el.hidden = true), 5500);
}
export async function api(path, data) {
  const r = await fetch(
    "/api/" + path,
    data
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Yehang": "1" },
          body: JSON.stringify(data),
        }
      : {},
  );
  const j = await r.json();
  if (!r.ok) throw Error(j.error || "操作未完成");
  return j;
}
export const payload = (extra) => ({
  profile: state.p,
  revision: state.data.revision,
  ...extra,
});
export function busy(label, progress) {
  const el = $(".busy");
  el.hidden = !label;
  if (label) {
    $("strong", el).textContent = label;
    const p = $("progress", el);
    if (progress == null) p.removeAttribute("value");
    else p.value = progress;
  }
}
export function upload(kind, file, week) {
  if (file.size > 1024 ** 3) throw Error("单个文件上限为 1 GB。");
  const ext = file.name.split(".").pop();
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open(
      "POST",
      `/api/upload/${kind}?ext=${encodeURIComponent(ext)}&profile=${state.p}&week=${week || ""}`,
    );
    x.setRequestHeader("X-Yehang", "1");
    x.upload.onprogress = (e) =>
      busy("正在上传…", e.lengthComputable ? (100 * e.loaded) / e.total : null);
    x.upload.onload = () =>
      busy(kind === "health" ? "正在解析并保存健康记录…" : "模型正在读取排班…");
    x.onerror = () => reject(Error("上传连接中断，请重试。"));
    x.onload = () => {
      try {
        const v = JSON.parse(x.responseText);
        if (x.status >= 400) throw Error(v.error || "导入失败");
        resolve(v);
      } catch (e) {
        reject(e);
      }
    };
    busy("正在上传…", 0);
    x.send(file);
  });
}
export function modal(title, body) {
  const el = $("#sheet");
  $("h2", el).textContent = title;
  $("#sheetbody").innerHTML = body;
  if (!el.open) el.showModal();
  return $("#sheetbody");
}
export const close = () => $("#sheet").close();
$(".close").onclick = close;
export function timeWheel(title, initial, commit, withDate = true) {
  const h = Number(initial.slice(11, 13)),
    m = Number(initial.slice(14, 16));
  const wheel = (n, name) =>
    `<div class="wheel" tabindex="0" role="spinbutton" aria-label="${name}" aria-valuemin="0" aria-valuemax="${n - 1}">${Array.from({ length: n }, (_, i) => `<div>${String(i).padStart(2, "0")}</div>`).join("")}</div>`;
  const b = modal(
    title,
    `${withDate ? `<label class="field">日期<input type="date" id="wdate" value="${initial.slice(0, 10)}"></label>` : ""}<div class="wheels">${wheel(24, "小时")}<b>:</b>${wheel(60, "分钟")}</div><p class="note">上下滚动选择时间，也可以点选或使用方向键。</p><button class="primary" id="wdone">确定时间</button>`,
  );
  const wheels = $$(".wheel", b);
  wheels.forEach((w, i) => {
    const update = () =>
      w.setAttribute("aria-valuenow", Math.round(w.scrollTop / 44));
    w.scrollTop = [h, m][i] * 44;
    update();
    w.onscroll = update;
    w.onclick = (e) => {
      if (e.target.parentNode === w)
        w.scrollTop = [...w.children].indexOf(e.target) * 44;
    };
    w.onkeydown = (e) => {
      if (["ArrowUp", "ArrowDown"].includes(e.key)) {
        e.preventDefault();
        w.scrollTop += e.key === "ArrowUp" ? -44 : 44;
      }
    };
  });
  $("#wdone", b).onclick = () => {
    const d = withDate ? $("#wdate", b).value : initial.slice(0, 10);
    if (!d) return;
    const t = wheels
      .map((w) => String(Math.round(w.scrollTop / 44)).padStart(2, "0"))
      .join(":");
    close();
    commit(at(d, t));
  };
}
export function dropZone(id, accept, label, desc) {
  return `<div class="drop" id="${id}-drop">${icon("data")}<h3>${label}</h3><p class="note">${desc}</p><input class="offscreen" type="file" id="${id}" accept="${accept}"><label class="pick" for="${id}">选择文件</label></div>`;
}
export function bindDrop(id, handler) {
  const z = $("#" + id + "-drop");
  const run = async (f) => {
    if (!f) return;
    if (state.uploading) return toast("请等待当前文件处理完成");
    state.uploading = true;
    try {
      await handler(f);
    } catch (e) {
      toast(e.message);
    } finally {
      state.uploading = false;
      busy(null);
    }
  };
  $("#" + id).onchange = (e) => {
    run(e.target.files[0]);
    e.target.value = "";
  };
  z.ondragover = (e) => {
    e.preventDefault();
    z.classList.add("drag");
  };
  z.ondragleave = () => z.classList.remove("drag");
  z.ondrop = (e) => {
    e.preventDefault();
    z.classList.remove("drag");
    run(e.dataTransfer.files[0]);
  };
}
