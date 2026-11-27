"""HealthKit 样本适配后的事务入库；同步客户端与夜航分析层分离。"""
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from uuid import UUID

from adapters.field_mapping import TYPE_MAP, normalize_value
from storage import workspace as ws
from storage.schedule import locked_profile
from beta.timebase import local

PROFILE = 'personal-main'
STAGES = {0: 'in_bed', 1: 'asleep', 2: 'awake', 3: 'core', 4: 'deep', 5: 'rem'}


def initialize(db):
    with db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS health_sync_batches (
          user_id TEXT NOT NULL,batch_id TEXT NOT NULL,result TEXT NOT NULL,received TEXT NOT NULL,
          PRIMARY KEY(user_id,batch_id));
        CREATE TABLE IF NOT EXISTS health_sync_sources (
          fingerprint TEXT PRIMARY KEY,alias TEXT NOT NULL UNIQUE);
        CREATE TABLE IF NOT EXISTS health_sync_ids (
          user_id TEXT NOT NULL,uuid TEXT NOT NULL,source TEXT NOT NULL,content TEXT NOT NULL,
          PRIMARY KEY(user_id,uuid));
        CREATE TABLE IF NOT EXISTS health_sync_deleted (
          user_id TEXT NOT NULL,uuid TEXT NOT NULL,PRIMARY KEY(user_id,uuid));
        CREATE TABLE IF NOT EXISTS health_sync_owner (user_id TEXT PRIMARY KEY);
        ''')


def source_alias(db, sample):
    # 不落盘设备名、序列号或个人来源名称；同一来源的六类指标使用同一个匿名别名。
    fields = [sample.get(k) or '' for k in ('sourceBundleID', 'sourceName', 'device')]
    if not all(isinstance(x, str) for x in fields):
        raise ValueError('来源字段格式无效')
    fingerprint = sha256(json.dumps(fields, ensure_ascii=False).encode()).hexdigest()
    found = db.execute('SELECT alias FROM health_sync_sources WHERE fingerprint=?', (fingerprint,)).fetchone()
    if found:
        return found[0]
    hint = ' '.join(fields).lower()
    kind = 'watch' if 'watch' in hint or '手表' in hint else 'phone' if 'iphone' in hint else 'other'
    used = {r[0] for r in db.execute('SELECT source FROM samples WHERE profile_id=?', (PROFILE,))}
    used.update(r[0] for r in db.execute('SELECT alias FROM health_sync_sources'))
    i = 1
    while f'{kind}_{i}' in used:
        i += 1
    alias = f'{kind}_{i}'
    db.execute('INSERT INTO health_sync_sources VALUES (?,?)', (fingerprint, alias))
    return alias


def instant(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value == 0:
        raise ValueError('样本时间必须是非零毫秒时间戳')
    return local(datetime.fromtimestamp(value / 1000, timezone.utc)).isoformat()


def normalized(db, sample):
    metric = TYPE_MAP.get(sample['type'])
    if metric is None:
        return None
    if sample.get('kind') != ('category' if metric == 'sleep' else 'quantity'):
        raise ValueError('指标与样本类别不一致')
    start = instant(sample['start'])
    end = instant(sample.get('end') or sample['start'])
    if end < start or (metric == 'sleep' and start == end):
        raise ValueError('样本起止时间无效')
    if metric == 'sleep':
        stage = sample.get('category')
        if type(stage) is not int or stage not in STAGES:
            raise ValueError('未知睡眠分期')
        value, unit = STAGES[stage], 'stage'
    else:
        value, unit = normalize_value(metric, sample.get('value'), sample.get('unit'))
    return dict(id=str(UUID(sample['uuid'])), metric=metric, source=source_alias(db, sample),
                start=start, end=end, value=value, unit=unit)


def apply_batch(db, batch, user_id):
    initialize(db)
    batch_id = str(UUID(batch['header']['batchID']))
    with locked_profile(db, PROFILE, 'personal'):
        owner = db.execute('SELECT user_id FROM health_sync_owner').fetchone()
        if owner and owner[0] != user_id:
            raise PermissionError('此连接已绑定其他手机档案，请使用同一 PulsHealth 用户')
        old = db.execute('SELECT result FROM health_sync_batches WHERE user_id=? AND batch_id=?',
                         (user_id, batch_id)).fetchone()
        if old:
            return dict(json.loads(old[0]), replayed=True)
        db.execute('INSERT OR IGNORE INTO health_sync_owner VALUES (?)', (user_id,))
        rows, counts = [], Counter(accepted=0, duplicates=0, deleted=0, ignored=0)
        for sample in batch['samples']:
            row = normalized(db, sample)
            if row is None:
                counts['ignored'] += 1
                continue
            uid = row['id']
            if db.execute('SELECT 1 FROM health_sync_deleted WHERE user_id=? AND uuid=?', (user_id, uid)).fetchone():
                counts['duplicates'] += 1
                continue  # 较早的批次晚到，也不能复活已删除的 UUID。
            previous = db.execute('SELECT content FROM health_sync_ids WHERE user_id=? AND uuid=?',
                                  (user_id, uid)).fetchone()
            content = ws.content_key(row)
            if previous and previous[0] != content:
                raise ValueError('同一 HealthKit UUID 的内容发生冲突，整批未写入')
            rows.append(row)
        added, duplicates, conflict = ws._insert_batch(db, PROFILE, 'puls-' + batch_id, rows,
            {'mode': 'personal', 'analysis_tz': 'Asia/Shanghai', 'file': 'PulsHealth', 'transport': 'puls-v1'})
        if conflict:
            raise ValueError('健康记录身份冲突，整批未写入')
        counts['accepted'] = added
        counts['duplicates'] += duplicates
        for row in rows:
            db.execute('INSERT OR IGNORE INTO health_sync_ids VALUES (?,?,?,?)',
                       (user_id, row['id'], row['source'], ws.content_key(row)))
        for item in batch['deletions']:
            if item['type'] not in TYPE_MAP:
                counts['ignored'] += 1
                continue
            uid = str(UUID(item['uuid']))
            db.execute('INSERT OR IGNORE INTO health_sync_deleted VALUES (?,?)', (user_id, uid))
            old = db.execute('SELECT source,content FROM health_sync_ids WHERE user_id=? AND uuid=?',
                             (user_id, uid)).fetchone()
            if not old:
                continue
            source, content = old
            db.execute('DELETE FROM identities WHERE profile_id=? AND source=? AND id=?', (PROFILE, source, uid))
            db.execute('DELETE FROM health_sync_ids WHERE user_id=? AND uuid=?', (user_id, uid))
            if not db.execute('SELECT 1 FROM identities WHERE profile_id=? AND content=?', (PROFILE, content)).fetchone():
                counts['deleted'] += db.execute('DELETE FROM samples WHERE profile_id=? AND content=?',
                                                (PROFILE, content)).rowcount
        counts['ignored'] += sum(len(batch[k]) for k in ('routes', 'series', 'aggregates', 'activitySummaries'))
        counts['ignored'] += int(batch['profile'] is not None)
        result = dict(counts, routePoints=0, seriesPoints=0, aggregateSamples=0, activitySummaries=0)
        db.execute('INSERT INTO health_sync_batches VALUES (?,?,?,?)',
                   (user_id, batch_id, json.dumps(result), datetime.now(timezone.utc).isoformat()))
        db.execute('UPDATE profiles SET revision=revision+1 WHERE profile_id=?', (PROFILE,))
        return result


def status(db):
    initialize(db)
    last = db.execute('SELECT received,result FROM health_sync_batches ORDER BY rowid DESC LIMIT 1').fetchone()
    counts = dict(db.execute('SELECT metric,count(*) FROM samples WHERE profile_id=? GROUP BY metric', (PROFILE,)))
    bounds = db.execute('SELECT min(start),max(end) FROM samples WHERE profile_id=?', (PROFILE,)).fetchone()
    return {'last_sync': last[0] if last else None, 'last_result': json.loads(last[1]) if last else None,
            'counts': counts, 'coverage': list(bounds)}
