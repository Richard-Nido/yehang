import {
  $,
  $$,
  state,
  esc,
  icon,
  fmt,
  at,
  daysFrom,
  weekday,
  modal,
  close,
  timeWheel,
  api,
  payload,
  toast,
  busy,
  upload,
  dropZone,
  bindDrop,
} from "./shared.js";
const kinds = {
  day: "日班",
  night: "夜班",
  work: "工作",
  course: "课程",
  commute: "通勤",
  available: "可休息时段",
  rest: "休息日",
};
const presets = {
  day: ["08:00", "17:00"],
  night: ["20:00", "08:00"],
  work: ["09:00", "18:00"],
  course: ["09:00", "10:30"],
  commute: ["07:30", "08:00"],
  available: ["13:00", "14:00"],
  rest: ["00:00", "00:00"],
};
let selected = "";
function dayBar(days, marked) {
  return `<div class="days">${days.map((d) => `<button type="button" data-day="${d}" class="${marked.includes(d) ? "on" : ""}" aria-pressed="${marked.includes(d)}"><span>${weekday(d)}</span><strong>${Number(d.slice(-2))}</strong></button>`).join("")}</div>`;
}
export function schedulePage(refresh) {
  const d = state.data,
    first = d.scheduleStart || d.now.slice(0, 10),
    days = Array.from({ length: 7 }, (_, i) => daysFrom(first, i));
  if (!days.includes(selected)) selected = first;
  $("#action").innerHTML =
    '<button class="primary inline" id="addShift">' +
    icon("plus") +
    "添加日程</button>";
  const matches = d.blocks.filter(
    (b) =>
      Date.parse(b.start) < Date.parse(at(daysFrom(selected, 1), "00:00")) &&
      Date.parse(b.end) > Date.parse(at(selected, "00:00")),
  );
  $("#screen").innerHTML =
    `<div class="panel"><div class="panelhead"><h2>${first.slice(5).replace("-", "/")} — ${days.at(-1).slice(5).replace("-", "/")}</h2><label><span class="offscreen">七日安排起始日</span><input class="control" type="date" id="weekStart" value="${first}"></label></div>${dayBar(days, [selected])}<div class="section"><h3>${weekday(selected)}的安排</h3>${matches.length ? matches.map((b, i) => `<div class="entry"><span class="bubble">${icon(b.kind === "rest" ? "rest" : "calendar")}</span><div><b>${esc(b.title)}</b><p class="detail">${b.kind === "rest" ? "全天" : fmt(b.start) + " – " + fmt(b.end)}</p></div><button class="quiet" data-del="${i}" aria-label="移除${esc(b.title)}">移除</button></div>`).join("") : '<p class="empty">这天还没有日程。可以添加班次，或从下面导入排班表。</p>'}</div></div>
 <section class="panel section"><h2>从排班表导入</h2><p class="note">上传后会将排班页发送给配置的视觉模型。识别结果可按姓名筛选，确认后加入七日安排。</p>${dropZone("roster", ".pdf,.png,.jpg,.jpeg,.webp", "放入七日排班表", "支持 PDF、JPG、PNG、WebP，可拖放到这里")}</section>`;
  $$("[data-day]").forEach(
    (b) =>
      (b.onclick = () => {
        selected = b.dataset.day;
        schedulePage(refresh);
      }),
  );
  $("#weekStart").onchange = (e) => {
    state.scheduleStart = e.target.value;
    refresh();
  };
  $("#addShift").onclick = () => manual(days, refresh);
  $$("[data-del]").forEach(
    (b) =>
      (b.onclick = () => {
        const item = matches[+b.dataset.del];
        modal(
          "移除这项日程？",
          `<p class="note">${esc(item.title)} · ${fmt(item.start)}</p><button class="primary" id="confirmDel">移除日程</button>`,
        );
        $("#confirmDel").onclick = async () => {
          await api("events/remove", payload(item));
          close();
          await refresh();
          toast("已移除日程");
        };
      }),
  );
  bindDrop("roster", async (file) => {
    const target = state.p;
    const j = await upload("schedule", file, first);
    if (state.p !== target || state.page !== "schedule")
      return toast("已离开原排班页面，本次识别结果未写入日程。");
    busy(null);
    preview(j, refresh);
  });
}
function manual(days, refresh) {
  let chosen = new Set([selected]),
    kind = "day",
    [start, end] = presets.day;
  function form() {
    const b = modal(
      "添加日程",
      `<p class="note">可一次选择多天，重复班次只需填一次。</p>${dayBar(days, [...chosen])}<label class="field">班次<select id="kind">${Object.entries(
        kinds,
      )
        .map(
          ([k, v]) =>
            `<option value="${k}" ${k === kind ? "selected" : ""}>${v}</option>`,
        )
        .join(
          "",
        )}</select></label>${kind === "rest" ? "" : `<div class="inputgrid"><button class="ghost" id="sStart">开始　${start}</button><button class="ghost" id="sEnd">结束　${end}</button></div><p class="note">${end <= start ? "结束于次日" : "当天结束"} · 点选时间可滚动调整</p>`}<button class="primary" id="saveShift">添加到 ${chosen.size} 天</button>`,
    );
    $$("[data-day]", b).forEach(
      (el) =>
        (el.onclick = () => {
          const d = el.dataset.day;
          if (chosen.has(d)) chosen.delete(d);
          else chosen.add(d);
          form();
        }),
    );
    $("#kind", b).onchange = (e) => {
      kind = e.target.value;
      [start, end] = presets[kind];
      form();
    };
    if (kind !== "rest") {
      const pick = (side) => {
        timeWheel(
          side === "start" ? "班次开始" : "班次结束",
          at(selected, side === "start" ? start : end),
          (v) => {
            if (side === "start") start = v.slice(11, 16);
            else end = v.slice(11, 16);
            form();
          },
          false,
        );
      };
      $("#sStart").onclick = () => pick("start");
      $("#sEnd").onclick = () => pick("end");
    }
    $("#saveShift").disabled = !chosen.size;
    $("#saveShift").onclick = async () => {
      const events = [...chosen].map((d) => ({
        kind,
        title: kinds[kind],
        start: at(d, start),
        end: at(end <= start ? daysFrom(d, 1) : d, end),
      }));
      const j = await api("events", payload({ events }));
      close();
      await refresh();
      toast(`已添加 ${j.added} 项日程`);
    };
  }
  form();
}
function preview(result, refresh) {
  const people = [...new Set(result.events.map((r) => r.person))];
  let remembered = localStorage.getItem("yh-roster-" + state.p) || "";
  let person =
    people.length === 1
      ? people[0]
      : people.includes(remembered) && remembered
        ? remembered
        : null;
  let remember = !!remembered;
  function draw() {
    const rows = result.events.filter((x) => x.person === person);
    const b = modal(
      "确认识别的日程",
      `${people.length > 1 ? `<label class="field">选择排班表中的本人<select id="person"><option value="-1">请选择姓名或代号</option>${people.map((p, i) => `<option value="${i}" ${p === person ? "selected" : ""}>${esc(p || "未署名")}</option>`).join("")}</select></label><label class="detail"><input type="checkbox" id="remember" ${remember ? "checked" : ""}> 下次记住我的选择</label>` : ""}${rows.map((r, i) => `<label class="entry"><input type="checkbox" checked data-row="${i}"><div><b>${esc(r.title)}</b><p class="detail">${fmt(r.start)} – ${fmt(r.end)}</p></div></label>`).join("")}${result.unresolved.length ? `<p class="warn">待手动补充：${result.unresolved.map(esc).join("、")}</p>` : ""}${!people.length ? "<p class='empty'>未找到可匹配的班次。请检查排班日期和班次图例，或手动添加。</p>" : ""}<button id="saveRows" class="primary" ${!rows.length ? "disabled" : ""}>加入七日安排</button>`,
    );
    if ($("#person", b)) {
      $("#remember", b).onchange = (e) => (remember = e.target.checked);
      $("#person", b).onchange = (e) => {
        person = people[+e.target.value] ?? null;
        draw();
      };
    }
    $("#saveRows", b).onclick = async () => {
      const events = $$("[data-row]:checked", b).map(
        (el) => rows[+el.dataset.row],
      );
      if (!events.length) return toast("请选择至少一项日程");
      const j = await api("events", payload({ events }));
      if (remember && person)
        localStorage.setItem("yh-roster-" + state.p, person);
      else localStorage.removeItem("yh-roster-" + state.p);
      close();
      await refresh();
      toast(`已添加 ${j.added} 项日程`);
    };
  }
  draw();
}
