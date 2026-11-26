import {
  $,
  state,
  modal,
  close,
  esc,
  fmt,
  api,
  payload,
  toast,
} from "./shared.js";

export function feedbackDraft(plan, refresh) {
  const root = modal(
    "用自己的话复盘",
    `<p class="detail">休息计划 · ${fmt(plan.start)}</p><label class="field">这次休息怎么样？<textarea id="reflection" rows="4" maxlength="2000" placeholder="例如：午休只睡了一半，醒来感觉精神好多了。"></textarea></label><p class="note">只将这段自述发送给文字模型。确认草稿后保存到本机。</p><button class="primary" id="parseReflection">整理为反馈</button><p id="draftStatus" role="status" class="detail"></p><div id="draftFields"></div>`,
  );
  const parse = $("#parseReflection", root),
    input = $("#reflection", root),
    fields = $("#draftFields", root),
    status = $("#draftStatus", root);
  const owner = state.p;
  input.oninput = () => {
    fields.replaceChildren();
    status.textContent = "";
  };
  parse.onclick = async () => {
    if (!input.value.trim()) {
      input.focus();
      return;
    }
    parse.disabled = true;
    input.readOnly = true;
    fields.replaceChildren();
    status.textContent = "模型正在整理…";
    try {
      const draft = await api("feedback/draft", { text: input.value });
      if (!parse.isConnected || state.p !== owner) return;
      status.textContent = "请核对并按需修改。";
      fields.innerHTML = `<label class="field">执行情况<select id="draftResult"><option value="">请选择</option>${["完成", "部分完成", "跳过"].map((x) => `<option ${draft.status === x ? "selected" : ""}>${x}</option>`).join("")}</select></label><label class="field">休息后的疲劳程度<select id="draftFatigue"><option value="">未提及</option>${["精神很好", "较有精神", "一般", "有些疲惫", "非常疲惫"].map((x, i) => `<option value="${i + 1}" ${draft.fatigue === i + 1 ? "selected" : ""}>${i + 1} · ${x}</option>`).join("")}</select></label><label class="field">我的记录<textarea id="draftNote" rows="2" maxlength="1000">${esc(draft.note)}</textarea></label><button class="primary" id="saveDraft">确认保存反馈</button>`;
      const result = $("#draftResult", root),
        fatigue = $("#draftFatigue", root);
      result.onchange = () => {
        fatigue.disabled = result.value === "跳过";
      };
      result.onchange();
      $("#saveDraft", root).onclick = async () => {
        if (!result.value) return toast("请先选择执行情况");
        await api(
          "feedback",
          payload({
            ...plan,
            status: result.value,
            fatigue:
              fatigue.disabled || !fatigue.value ? null : Number(fatigue.value),
            note: $("#draftNote", root).value,
          }),
        );
        close();
        await refresh();
        toast("已保存复盘反馈");
      };
    } catch (e) {
      status.textContent = e.message;
    } finally {
      parse.disabled = false;
      input.readOnly = false;
    }
  };
}
