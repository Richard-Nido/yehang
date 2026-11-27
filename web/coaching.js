import { $, esc, api, modal, close, toast, fmt } from './shared.js';

const metricInfo = {
  sleep: ['睡眠', '分钟'], resting_hr: ['静息心率', 'bpm'],
  hrv_sdnn: ['心率变异性', 'ms'],
};
const number = n => Number(n.toFixed(1)).toLocaleString('zh-CN');
function metricAnalysis(d) {
  return (d.notable_signals || []).map(s => {
    const [name,unit]=metricInfo[s.metric], delta=number(Math.abs(s.value-s.center));
    const change=s.metric==='sleep' ? `少 ${delta} ${unit}` : `${s.metric==='resting_hr'?'高':'低'} ${delta} ${unit}`;
    const reference=s.basis==='同班次情境' ? '同班次参照' : '个人长期参照';
    const text=s.metric==='sleep' ? '优先保护下一次主要睡眠，小憩只作补充。' :
      s.metric==='resting_hr' ? '先留意是否伴随疲劳或不适，适当放缓安排。' : '结合疲劳感和近期作息，给恢复留出时间。';
    return `<p class="coachingChange"><b>${name}比${reference}${esc(change)}。</b>${esc(text)}<small>${esc(s.basis)} · ${s.n} 个有效日</small></p>`;
  }).join('');
}
function actionCard(c, advice) {
  let headline=c.title, detail=c.text, badge='行动建议', link='';
  if (c.kind==='nap' && c.start) {
    badge='优先安排 · 休息'; headline=`${fmt(c.start)} – ${fmt(c.end)}`;
    detail=`预留 ${c.minutes} 分钟。`+(c.minutes>=20 ? '若能入睡，可先尝试约 15–20 分钟短睡。' : '窗口较短，先安静休息，或调整出更充足的小憩时间。');
    detail+=' 醒后确认清醒，再恢复工作。';
    link='<a class="button" href="#rest">查看并调整休息计划 →</a>';
  } else if (c.kind==='caffeine') {
    const coffee=advice.caffeine;
    badge='咖啡因提醒';
    if (coffee.candidate) {
      headline=`${fmt(coffee.candidate)} · 可选摄入时机`;
      detail=`仅在平时饮用、确有需求且无需限制时考虑。${fmt(coffee.cutoff)} 起避免继续摄入；提醒线不是安全保证。`;
    } else if (coffee.cutoff) {
      headline=`${fmt(coffee.cutoff)} 起避免咖啡因`;
      detail=coffee.status==='target_conflict' ? '目标入睡与日程冲突，请先调整目标或日程。' :
        coffee.status==='intake_unknown' ? '已有摄入记录但剂量不明，本次不再推荐额外摄入。' :
        coffee.status==='opted_out' ? '仅显示睡前停用提醒，不推荐喝咖啡。' :
        '当前不生成饮用时刻，优先保护下一次主要睡眠。';
      detail+=' 敏感者或高剂量摄入可能需要更早停止。';
    } else { headline='先补充目标入睡时间'; detail='知道下一次主要睡眠何时开始，才能安排咖啡因提醒。'; }
  } else if (c.kind==='sleep') {
    badge='主要睡眠'; headline=fmt(advice.preferences.target_sleep);
    detail='围绕这个目标准备入睡。小憩与咖啡不能代替主要睡眠；日程冲突时先调整安排。';
  }
  return `<article class="coachingAction"><small>${esc(badge)}</small><h4>${esc(headline)}</h4><p>${esc(detail)}</p>${link}</article>`;
}
export function coachingPanel(target, d, refresh) {
  const advice = d.coaching;
  if (!advice) { target.textContent = '请刷新页面读取行动建议。'; return; }
  const assessment=advice.cards.find(c=>c.kind==='assessment');
  const cards=advice.cards.filter(c=>!['assessment','check'].includes(c.kind));
  const sources=Object.entries(advice.evidence);
  const changes=metricAnalysis(d);
  target.innerHTML = `${changes ? `<section class="coachingAnalysis"><h4>值得留意的变化 <small>${esc(d.day.slice(5).replace('-','/'))}</small></h4>${changes}</section>` : ''}
    <section class="coachingNext"><div class="panelhead"><h4>接下来怎么安排</h4><button class="ghost" id="coachingSettings">${advice.preferences.target_sleep ? '调整入睡目标' : '设置入睡目标'}</button></div>
    <p class="note">${esc(assessment?.text||'')}</p>
    <div class="coachingActions">${cards.map(c=>actionCard(c,advice)).join('')}</div></section>
    <details class="coachingEvidence"><summary>依据与适用条件 · 统一查看</summary>
    <p class="detail">${esc(advice.scope)}</p><p class="detail">只提示睡眠偏少、静息心率偏高或 HRV 偏低且达到个人参照提示门槛的变化。沿用评分的过去 28 日稳健参照，至少 14 个有效日，同情境达到 7 日时优先使用；偏离一个稳健尺度触发提示，属于产品规则，不是医学异常诊断。缺测、覆盖不完整或样本不足时不作偏离判断，也不代表正常。HRV 受测量时段、活动等影响，不能推断心情。行动按规划时刻的近期记录和未来日程生成，不把历史回看日期当成现在。</p>
    <h4>各项建议的条件</h4>${advice.cards.map(c=>`<div class="coachingCondition"><b>${esc(c.title)}</b><p class="detail">${esc(c.text)}</p></div>`).join('')}
    <h4>研究与方法来源</h4>${sources.map(([id,e],i)=>`<div class="coachingReference"><a href="${esc(e.url)}" target="_blank" rel="noreferrer">${i+1}. ${esc(e.title)} ↗</a><p class="detail">${esc(e.finding)}</p><p class="detail">适用范围：${esc(e.scope)}</p></div>`).join('')}
    <p class="detail">${esc(advice.version)} · 规划时刻 ${esc(advice.generated_at.replace('T',' '))}</p></details>`;
  $('#retry').hidden = true;
  $('#coachingSettings').onclick = () => settings(d, refresh);
}
function settings(d, refresh) {
  const prefs=d.coaching.preferences;
  const b=modal('下一次主要睡眠', `<p class="note">填写准备正式睡觉的日期和时间，区别于短时小憩。按上海时间保存。</p>
    <form id="coachingForm"><label class="field">目标入睡时间（可留空）<input id="sleepTarget" type="datetime-local" value="${esc(prefs.target_sleep?.slice(0,16)||'')}" min="${esc(d.now.slice(0,16))}"></label>
    <label class="field">咖啡因提示<select id="caffeineMode"><option value="off">不推荐摄入，只看睡前停用提醒</option><option value="usual">我平时饮用且无需限制，查看可选时机</option></select></label>
    <p class="detail">如果你对咖啡因敏感、处于孕哺期、存在相关疾病／用药限制或已被建议避免，请保留“不推荐摄入”。本功能不计算剂量、杯数或个人代谢速度。</p>
    <p class="detail" id="coachingError" role="status"></p><button class="primary" type="submit">保存并重新安排</button></form>`);
  $('#caffeineMode',b).value=prefs.caffeine_mode;
  $('#coachingForm',b).onsubmit=async e=>{
    e.preventDefault();
    try {
      const t=$('#sleepTarget',b).value;
      await api('coaching',{profile:d.profile,revision:d.revision,target_sleep:t ? t+'+08:00':null,caffeine_mode:$('#caffeineMode',b).value});
      close(); await refresh(); toast('已更新入睡目标与行动建议');
    } catch(err) { $('#coachingError',b).textContent=err.message; }
  };
}
