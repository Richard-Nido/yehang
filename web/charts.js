let serial = 0;
export function plot(
  values,
  color,
  large = false,
  bars = false,
  score = false,
  selected = 6,
) {
  const valid = values.filter((v) => v != null);
  if (!valid.length)
    return `<div class="${large ? "bigchart" : "spark"} emptyplot">${large ? "这七天还没有有效记录" : "暂无记录"}</div>`;
  const w = large ? 540 : 200,
    h = large ? 160 : 35,
    pad = large ? 18 : 4;
  const min = Math.min(...valid),
    max = Math.max(...valid);
  const lower =
    bars || score ? 0 : Math.max(0, min - Math.max(1, (max - min) * 0.18));
  const upper = score ? 100 : max + Math.max(1, (max - lower) * 0.12);
  const left = large ? 42 : pad;
  const x = (i) => left + (i * (w - pad - left)) / 6,
    y = (v) => h - pad - ((v - lower) / (upper - lower)) * (h - 2 * pad);
  const id = "wash" + ++serial;
  let ink = "",
    segments = [],
    section = [];
  for (let i = 0; i < 7; i++) {
    if (values[i] == null) {
      if (section.length) segments.push(section);
      section = [];
      continue;
    }
    section.push([x(i), y(values[i])]);
    if (bars) {
      const width = large ? 30 : 12;
      ink += `<rect x="${x(i) - width / 2}" y="${y(values[i])}" width="${width}" height="${Math.max(2, h - pad - y(values[i]))}" rx="${large ? 6 : 3}" fill="${color}" opacity="${i === selected ? 1 : 0.65}"/>`;
    }
  }
  if (section.length) segments.push(section);
  if (!bars)
    for (const points of segments) {
      let line = `M${points[0][0]} ${points[0][1]}`;
      for (let i = 1; i < points.length; i++) {
        const [a, b] = points[i - 1],
          [c, d] = points[i],
          mid = (a + c) / 2;
        line += ` C${mid} ${b} ${mid} ${d} ${c} ${d}`;
      }
      const last = points.at(-1);
      ink += `<path d="${line} V${h} H${points[0][0]} Z" fill="url(#${id})"/><path d="${line}" fill="none" stroke="${color}" stroke-linecap="round" stroke-width="${large ? 3 : 2}" vector-effect="non-scaling-stroke"/>`;
      for (const [cx, cy] of large ? points : [last])
        ink += `<circle cx="${cx}" cy="${cy}" r="${large ? 3.6 : 2.1}" fill="white" stroke="${color}" stroke-width="1.8"/>`;
    }
  const guide = large
    ? `<path d="M${x(selected)} ${pad}V${h - pad}" stroke="${color}" opacity=".45" stroke-dasharray="3 4"/>
 ${[lower, (lower + upper) / 2, upper].map((v) => `<text x="0" y="${y(v) + 4}" fill="#63727b" font-size="12">${Math.round(v)}</text>`).join("")}
 ${!bars && values[selected] != null ? `<circle cx="${x(selected)}" cy="${y(values[selected])}" r="6" fill="white" stroke="${color}" stroke-width="3"/>` : ""}`
    : "";
  return `<svg class="${large ? "bigchart" : "spark"}" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="七日走势：${values.map((v) => (v == null ? "缺测" : Math.round(v))).join("，")}"><defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1" gradientUnits="objectBoundingBox"><stop stop-color="${color}" stop-opacity=".22"/><stop offset="1" stop-color="${color}" stop-opacity=".025"/></linearGradient></defs>${large ? [0.15, 0.5, 0.85].map((k) => `<path d="M0 ${h * k} H${w}" stroke="#dce2e7" stroke-dasharray="2 5"/>`).join("") : ""}${ink}${guide}</svg>`;
}
