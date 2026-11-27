"""行动建议 v1：证据支持的原则＋显式标注的排程规则，不作诊断或剂量处方。"""
from datetime import timedelta
from core.features import Feature, compare
from core.health_state import assess
from beta.timebase import local, stamp

VERSION = 'actions-1.0'
EVIDENCE = {
 'nap': dict(title='NIOSH：短时小睡与轮班', url='https://www.cdc.gov/niosh/work-hour-training-for-nurses/longhours/mod7/02.html',
   finding='短时小睡可暂时改善警觉性，不能代替主要睡眠。', scope='面向成人轮班教育；不保证某个个体的收益。'),
 'inertia': dict(title='NIOSH：睡眠惯性', url='https://www.cdc.gov/niosh/work-hour-training-for-nurses/longhours/mod7/03.html',
   finding='醒后可暂时困倦，关键任务前应留恢复时间。', scope='15 分钟是夜航排程缓冲，不是已证明人人足够的恢复时长。'),
 'caffeine': dict(title='NIOSH：轮班咖啡因与入睡准备', url='https://www.cdc.gov/niosh/work-hour-training-for-nurses/longhours/mod6/04.html',
   finding='需要咖啡因的夜班人员可考虑班次开始阶段，临近睡眠应避免；作用消退存在个体差异。', scope='不等于建议每位用户喝咖啡，也未验证某个精确时刻。'),
 'dose': dict(title='Gardiner 等，Sleep 2025 · PMID 39377163', url='https://pubmed.ncbi.nlm.nih.gov/39377163/',
   finding='23 名健康男性的交叉试验中，400 mg 单次剂量在睡前 12 小时内仍可能影响睡眠；100 mg 的结果不同。',
   scope='小样本、特定人群与剂量；不能据此给你指定剂量或保证某时刻以后安全。'),
 'six': dict(title='Drake 等，JCSM 2013 · PMID 24235903', url='https://pubmed.ncbi.nlm.nih.gov/24235903/',
   finding='研究中 400 mg 咖啡因在睡前 6 小时仍影响睡眠。', scope='夜航以提前 6 小时作为最低停用提醒；较早摄入仍可能影响睡眠，敏感者应更早。'),
 'method': dict(title='夜航：评分方法及适用范围', url='/assets/health-state.md',
   finding='HRV、静息心率只作相对个人基线的描述，不直接判断心情、疾病或适岗。', scope='基线门槛和偏离阈值是工程规则，最终分数尚无临床验证。'),
 'schedule': dict(title='夜航：行动排程规则', url='/assets/actions.md',
   finding='具体分钟由可用窗口、班次、目标睡眠和现有计划计算。', scope='具体时间点与排序是产品排程结果，不是试验证实的最佳时间。'),
}


def initialize(db):
    with db:
        db.execute('''CREATE TABLE IF NOT EXISTS coaching_preferences (
            profile_id TEXT PRIMARY KEY REFERENCES profiles,
            target_sleep TEXT, caffeine_mode TEXT NOT NULL DEFAULT 'off')''')


def preferences(db, profile):
    row = db.execute('SELECT target_sleep,caffeine_mode FROM coaching_preferences WHERE profile_id=?', (profile,)).fetchone()
    return dict(row) if row else {'target_sleep':None, 'caffeine_mode':'off'}


def target_for(prefs, now):
    target = prefs.get('target_sleep')
    return local(target) if target and local(target) > local(now) else None


def save_preferences(db, profile, mode, revision, body, now):
    from storage.schedule import edit
    initialize(db)
    target = body.get('target_sleep') or None
    caffeine = body.get('caffeine_mode', 'off')
    if caffeine not in ('off', 'usual'):
        raise ValueError('请选择是否接收咖啡因提示')
    if target:
        from datetime import datetime
        t = datetime.fromisoformat(target)
        if t.tzinfo is None or not local(now) < local(t) <= local(now) + timedelta(days=7):
            raise ValueError('目标入睡须带时区，且在规划时刻之后七天内')
        target = stamp(t)
    with edit(db, profile, mode, revision):
        db.execute('INSERT INTO coaching_preferences VALUES (?,?,?) ON CONFLICT(profile_id) DO UPDATE SET target_sleep=excluded.target_sleep,caffeine_mode=excluded.caffeine_mode',
                   (profile, target, caffeine))
    return {}


def clock(t):
    return stamp(t)[5:16].replace('T', ' ')


def build(now, features, contexts, blocks, plans, events, prefs, recommendation, availability):
    now = local(now)
    today = now.date()
    cards = []
    def add(kind, title, text, ids, **extra):
        cards.append(dict(kind=kind, title=title, text=text, evidence=ids, **extra))

    days = [d for d,f in features['sleep'].items() if today-timedelta(days=1) <= d <= today
            and f.value is not None and not f.partial]
    if not days:
        assessment = '近期缺少可用的完整睡眠记录，不能判断你是否少睡；下面只按已知日程安排，不把缺失当作零。'
    else:
        day = max(days)
        f, baseline, same, _, delta, _ = compare(features['sleep'], day, contexts, 'sleep')
        if delta is not None and delta < 0:
            basis = '相似班次' if same.ready else '长期历史'
            assessment = f'{day.month}/{day.day} 记录的睡眠比你自己的{basis}少 {abs(delta):.0f} 分钟。若当晚佩戴和记录完整，应优先保护下一次主要睡眠，小憩只是临时补充。'
        else:
            assessment = f'{day.month}/{day.day} 有睡眠记录；目前不能仅凭这些记录判断恢复是否充分。休息安排同时取决于下一班和你计划何时入睡。'

    shift = next((b for b in sorted(blocks, key=lambda b:b['start'])
                  if b['kind'] in ('night','day','work') and local(b['end']) > now), None)
    if shift:
        name = {'night':'夜班','day':'日班','work':'工作'}[shift['kind']]
        assessment += f' 接下来已记录的{name}为 {clock(local(shift["start"]))} 至 {clock(local(shift["end"]))}。'
    else:
        assessment += ' 还未填写接下来的工作班次，暂时不能围绕开班时刻安排提神提醒。'
    add('assessment','先看身体与下一班',assessment,['nap','schedule'])

    signals = assess(features, today, contexts).signals
    pulse, hrv = signals['resting_hr'], signals['hrv_sdnn']
    # 偏离 1 个稳健尺度只触发核对提示，不改变咖啡因剂量或宣称疲劳原因。
    if pulse.z is not None and hrv.z is not None and pulse.z >= 1 and hrv.z <= -1:
        add('check','先核对身体感受','今天静息心率偏高、HRV 偏低于个人参照。先核对是否刚运动、测量时段改变或确实不舒服；这组数据不能直接说明焦虑或需要喝咖啡。',['method'])
    elif pulse.current.value is not None or hrv.current.value is not None:
        add('check','心率数据怎样参与建议','已读取可用的心率类记录，缺测项仍保留为空；这些记录用于查看相对个人常态的变化，不用于推断心情，也不作为咖啡因摄入的开关。',['method'])

    fatigue = [(local(e['at']),e['value']) for e in events if e['kind']=='fatigue'
               and local(e['at']) <= now and local(e['at']).date()==today]
    if fatigue and max(fatigue)[1] >= 4:
        add('fatigue','先处理明显困倦','你今天自报疲劳较高。若已困到打瞌睡，不要靠评分或咖啡判断自己能否安全驾车／完成关键任务，先停止危险任务并寻求休息安排。',['inertia'])

    if recommendation:
        r = recommendation
        text = f'可在 {clock(local(r["start"]))}–{clock(local(r["end"]))} 预留 {r["minutes"]} 分钟休息。'
        if r['minutes'] >= 20:
            text += ' 若能入睡，可先尝试约 15–20 分钟短时小睡；这里的预留时间包含准备，不代表实际睡眠时长。'
        else:
            text += ' 这个窗口较短，可先安静休息；若需要小睡，应调整窗口给入睡及醒后恢复留足时间。'
        if availability['assumed']:
            text += ' 这个空档是日程估算，先确认自己确实能休息。'
        text += ' 醒后先确认清醒，再恢复工作；日程中的 15 分钟缓冲不保证足以消除困倦。'
        add('nap','把休息落实到一个时段',text,['nap','inertia','schedule'],start=r['start'],end=r['end'],minutes=r['minutes'])
    else:
        add('nap','暂时没有可安排的小憩窗口','在当前日程、已存计划及目标睡眠限制下，没有连续至少 10 分钟的候选。先调整日程或保护主要睡眠，不把无空档解释成不需要休息。',['nap','schedule'])

    target = target_for(prefs, now)
    caffeine = {'status':'needs_sleep_target','cutoff':None,'candidate':None}
    if not target:
        expired = bool(prefs.get('target_sleep'))
        text = ('上次目标入睡时间已过，请更新。' if expired else '先补充下一次主要睡眠的目标入睡时间。')
        text += ' 未填写有效目标时，不生成喝咖啡时刻或停用钟点。'
        add('caffeine','先保护下一次主要睡眠',text,['caffeine','dose'])
    else:
        cutoff = target - timedelta(hours=6)
        caffeine['cutoff'] = stamp(cutoff)
        text = f'目标主要睡眠为 {clock(target)}。停用提醒线设在 {clock(cutoff)}：'
        text += '从该时刻起避免继续摄入咖啡因。提前 6 小时只是最低提醒，不是安全线；高剂量或敏感人群可能需要提前更久。'
        target_conflict = any(b['kind'] not in ('available','rest') and local(b['start']) <= target < local(b['end']) for b in blocks)
        candidate = max(now, local(shift['start'])) if shift else None
        recent_caffeine = any(e['kind']=='caffeine' and now-timedelta(hours=24) <= local(e['at']) <= now for e in events)
        if prefs['caffeine_mode'] != 'usual':
            caffeine['status']='opted_out'
            text += ' 你未开启可选摄入提示，不推荐具体饮用时刻。'
        elif target_conflict:
            caffeine['status']='target_conflict'
            text += ' 目标入睡与已有日程冲突，先调整目标或日程，不生成摄入时刻。'
        elif recent_caffeine:
            caffeine['status']='intake_unknown'
            text += ' 过去 24 小时已记录咖啡因但剂量不明，不再额外推荐摄入。'
        elif candidate is None:
            caffeine['status']='needs_shift'
            text += ' 尚无下一班信息，不生成具体饮用时刻。'
        elif local(shift['start']) < now or candidate >= cutoff or candidate >= target:
            caffeine['status']='no_early_shift_window'
            text += ' 当前没有符合“班次开始阶段且早于停用线”的候选，不为了提神继续推迟喝咖啡。'
        else:
            caffeine.update(status='optional_early_shift',candidate=stamp(candidate))
            text += f' 如果你平时饮用、确有提神需求且无需限制，可选在 {clock(candidate)} 班次开始时考虑；不是必须喝，不生成毫克数或杯数。'
        add('caffeine','咖啡因：先排时间，再决定是否需要',text,['caffeine','six','dose','schedule'])
        add('sleep','给主要睡眠留出准备时间',f'围绕 {clock(target)} 安排安静的入睡准备，减少临睡前刺激。若日程与该时间冲突，应先调整日程或目标，短休与咖啡不能代替主要睡眠。',['caffeine'])
        if any(b['kind'] not in ('available','rest') and local(b['start']) <= target < local(b['end']) for b in blocks):
            add('conflict','目标入睡与日程冲突','目标入睡时仍有工作、通勤或课程。请先调整其中一项，算法不能把这段忙碌时间算成睡眠。',['schedule'])
    used = list(dict.fromkeys(e for c in cards for e in c['evidence']))
    return dict(version=VERSION, generated_at=stamp(now), cards=cards, caffeine=caffeine,
                evidence={k:EVIDENCE[k] for k in used}, preferences=prefs,
                scope='成人日程辅助；研究支持一般原则，具体分钟、阈值和组合算法是产品规则，尚未验证个体疗效或适岗能力。')
