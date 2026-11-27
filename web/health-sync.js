import { $, api, esc, toast } from './shared.js';
export function syncPanel() {
  return `<section class="panel"><h2>手机健康同步 · 试运行</h2>
  <p class="note">使用 PulsHealth 连接这台电脑，自动接收原始健康样本。免费版可先选择睡眠、静息心率、HRV；不要选择日汇总代替原始样本。</p>
  <p class="detail">本次仅在可信的同一 Wi-Fi 临时验证，连接使用 HTTP，数据传输未加密。仅开放同步接口；不要用于公共网络。</p>
  <div class="wrap"><button id="syncStart" class="primary">开启临时局域网同步</button><button id="syncStop" class="ghost">停止同步</button><button id="syncUpdate" class="ghost">刷新同步状态</button></div>
  <div id="syncInfo" class="section" aria-live="polite"></div></section>`;
}
export function bindSync(refresh) {
  const root = $('#syncInfo');
  if (!root) return;
  async function update() {
    const s = await api('health-sync');
    if (!root.isConnected) return;
    const names = {sleep:'睡眠',resting_hr:'静息心率',hrv_sdnn:'HRV',heart_rate:'心率',steps:'步数',active_energy:'活动能量'};
    root.innerHTML = `<p>${s.running ? '同步接收中 · 端口 '+s.port : '同步已停止'}</p>
    ${s.running ? `<p class="note">PulsHealth → Connections → ＋ → Your database：地址填写 <code>http://电脑局域网IP:${s.port}</code>，Token 填写下方口令，再点 Test Connection 和 Save & Apply。</p><label class="field">连接口令（仅供你自己的手机）<input readonly id="syncToken" value="${esc(s.token)}"></label><button class="ghost" id="syncCopy">复制口令</button>` : ''}
    <p class="note">最后收到：${s.last_sync ? esc(new Date(s.last_sync).toLocaleString()) : '尚未收到手机批次'}</p>
    <p>${Object.entries(names).map(([k,n])=>`${n} ${s.counts[k]||0} 条`).join(' · ')}</p>
    ${s.last_result ? `<p class="detail">最近批次：新增 ${s.last_result.accepted}、重复 ${s.last_result.duplicates}、删除 ${s.last_result.deleted}、未用于分析 ${s.last_result.ignored}。仅六类原始样本参与分析；个人资料和其他类型不保存。</p>` : ''}
    ${s.coverage[0] ? `<p class="detail">记录范围：${esc(s.coverage[0])} 至 ${esc(s.coverage[1])}</p>` : ''}`;
    $('#syncStart').disabled = s.running;
    $('#syncStop').disabled = !s.running;
    if ($('#syncCopy')) $('#syncCopy').onclick = async () => {
      try { await navigator.clipboard.writeText(s.token); toast('已复制连接口令'); }
      catch (_) { $('#syncToken').select(); toast('请复制选中的口令'); }
    };
  }
  $('#syncStart').onclick = async () => { await api('health-sync', {action:'start'}); await update(); };
  $('#syncStop').onclick = async () => { await api('health-sync', {action:'stop'}); await update(); };
  $('#syncUpdate').onclick = async () => { await refresh(); };
  update();
}
