"""独立边界场景：有证据的原则与工程排程分开，缺测不虚构。"""
from collections import defaultdict
from datetime import date, timedelta
import unittest
from unittest.mock import patch

from beta import coaching
from beta.rest import recommend, rest_windows
from core.features import Feature
import test_beta as beta_tests

NOW='2026-11-03T15:00+08:00'
BED='2026-11-04T09:00+08:00'
BLOCKS=[{'kind':'night','start':'2026-11-03T22:00+08:00','end':'2026-11-04T07:00+08:00'},
        {'kind':'available','start':'2026-11-03T16:00+08:00','end':'2026-11-03T18:00+08:00'}]

def features():
    return {m:defaultdict(Feature) for m in ('sleep','sleep_hrv','resting_hr','hrv_sdnn')}

def build(bed=BED, mode='usual', events=(), blocks=BLOCKS, now=NOW):
    fs=features();prefs={'target_sleep':bed,'caffeine_mode':mode}
    target=coaching.target_for(prefs,now)
    r=recommend(now,blocks,[],fs,{},target)
    a=rest_windows(now,blocks,[],target)
    return coaching.build(now,fs,{},blocks,[],events,prefs,r,a)

class CoachingRules(unittest.TestCase):
    def test_missing_sleep_is_not_zero_or_sleep_debt(self):
        c=build()
        self.assertIn('不能判断你是否少睡',c['cards'][0]['text'])
        self.assertNotIn('少睡 0',c['cards'][0]['text'])
    def test_cross_midnight_early_shift_is_optional(self):
        c=build()['caffeine']
        self.assertEqual(c['candidate'],'2026-11-03T22:00+08:00')
        self.assertEqual(c['cutoff'],'2026-11-04T03:00+08:00')
    def test_unknown_bedtime_never_assigns_caffeine_time(self):
        c=build(bed=None)['caffeine']
        self.assertIsNone(c['candidate']);self.assertIsNone(c['cutoff'])
    def test_default_opt_out_and_recent_intake(self):
        self.assertEqual(build(mode='off')['caffeine']['status'],'opted_out')
        c=build(events=[{'kind':'caffeine','at':'2026-11-03T12:00+08:00'}])
        self.assertEqual(c['caffeine']['status'],'intake_unknown')
        self.assertIsNone(c['caffeine']['candidate'])
    def test_cutoff_passed_or_shift_already_running(self):
        self.assertIsNone(build(bed='2026-11-04T02:00+08:00')['caffeine']['candidate'])
        self.assertIsNone(build(now='2026-11-03T23:00+08:00')['caffeine']['candidate'])
    def test_expired_bedtime_is_not_reused(self):
        self.assertIsNone(build(bed='2026-11-03T10:00+08:00')['caffeine']['cutoff'])
    def test_no_window_before_bedtime_is_not_invented(self):
        fs=features();bed='2026-11-03T15:30+08:00'
        self.assertIsNone(recommend(NOW,BLOCKS,[],fs,{},bed))
        self.assertEqual(rest_windows(NOW,BLOCKS,[],bed)['windows'],[])
    def test_conflicting_target_suppresses_coffee(self):
        self.assertEqual(build(bed='2026-11-04T06:00+08:00')['caffeine']['status'],'target_conflict')
    def test_all_cards_have_sources_and_limits(self):
        c=build()
        for card in c['cards']:
            self.assertTrue(card['evidence'])
            for key in card['evidence']:
                self.assertTrue(c['evidence'][key]['scope'])
                self.assertTrue(c['evidence'][key]['url'])
        self.assertTrue(any('不是安全线' in x['text'] for x in c['cards']))
    def test_short_window_does_not_promise_twenty_minutes_sleep(self):
        c=build(blocks=[{'kind':'available','start':'2026-11-03T16:00+08:00','end':'2026-11-03T16:10+08:00'}])
        card=next(x for x in c['cards'] if x['kind']=='nap')
        self.assertIn('窗口较短',card['text']);self.assertNotIn('15–20',card['text'])

class CoachingAPI(beta_tests.BetaFlow):
    # 复用临时数据库设置，不重复运行父类测试。
    def test_goal_persists_and_default_never_calls_model(self):
        self.p='synthetic-demo'
        before=self.state()
        r=self.post('coaching',target_sleep=BED,caffeine_mode='usual')
        self.assertEqual(r.status_code,200,r.text)
        after=self.state()
        self.assertEqual(after['coaching']['preferences']['target_sleep'],BED)
        self.assertGreater(after['revision'],before['revision'])
        with patch('beta.provider.complete',side_effect=AssertionError('no API')) as model:
            r=self.post('explanation')
            self.assertEqual(r.json()['source'],'rules')
            self.assertTrue(r.json()['cards']);model.assert_not_called()
    def test_invalid_target_rolls_back(self):
        self.p='synthetic-demo'
        revision=self.state()['revision']
        r=self.post('coaching',target_sleep='2026-11-02T09:00+08:00',caffeine_mode='usual')
        self.assertEqual(r.status_code,400)
        self.assertEqual(self.state()['revision'],revision)
        self.assertIsNone(self.state()['coaching']['preferences']['target_sleep'])

# unittest 会继承父类测试；只保留本文件定义的 API 场景。
for name in list(vars(beta_tests.BetaFlow)):
    if name.startswith('test_'):
        setattr(CoachingAPI,name,None)
