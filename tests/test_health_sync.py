import gzip
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
from datetime import datetime

from fastapi.testclient import TestClient
from beta.health_sync import create_receiver
from beta import service
from storage import workspace as ws

SLEEP = 'HKCategoryTypeIdentifierSleepAnalysis'
HRV = 'HKQuantityTypeIdentifierHeartRateVariabilitySDNN'
USER = str(uuid4())

def ms(t):
    return datetime.fromisoformat(t).timestamp()*1000

def sample(stage=3, uid=None, start='2026-11-02T23:30+08:00', end='2026-11-03T01:30+08:00'):
    return dict(uuid=uid or str(uuid4()),type=SLEEP,kind='category',category=stage,
                start=ms(start),end=ms(end),sourceName='Apple Watch',device='Apple Watch')

def body(samples=(),deletions=(),bid=None):
    header=dict(schemaVersion=1,batchID=bid or str(uuid4()),type=SLEEP,
                sampleCount=len(samples),deletionCount=len(deletions))
    return gzip.compress(('\n'.join(json.dumps(x) for x in [header,*samples,*[{'deleted':d} for d in deletions]])+'\n').encode())

class HealthSyncTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.enterContext(patch.dict(os.environ,YEHANG_DB_PATH=str(Path(temp.name)/'test.sqlite3')))
        self.c=self.enterContext(TestClient(create_receiver('secret')))
        self.headers={'Authorization':'Bearer secret','X-Puls-Protocol':'1','X-User-ID':USER,'Content-Encoding':'gzip'}
    def post(self,data,headers=None):
        return self.c.post('/v1/batches',content=data,headers=headers or self.headers)
    def snapshot(self):
        with ws.open_workspace() as db:
            return service.snapshot(db,'personal-main',selected='2026-11-03')
    def test_auth_and_isolation(self):
        self.assertEqual(self.c.get('/v1/capabilities').status_code,401)
        self.assertEqual(self.c.get('/v1/capabilities',headers=self.headers).json()['features'],['batches'])
        self.assertEqual(self.c.get('/api/provider',headers=self.headers).status_code,404)
        self.assertEqual(self.c.get('/healthz').status_code,200)
    def test_crossnight_sleep_and_idempotence(self):
        rows=[sample(), sample(2,start='2026-11-03T00:00+08:00',end='2026-11-03T00:15+08:00'),
              sample(4,start='2026-11-03T00:30+08:00',end='2026-11-03T01:00+08:00'),
              sample(0,start='2026-11-02T23:10+08:00',end='2026-11-03T01:45+08:00')]
        data=body(rows)
        self.assertEqual(self.post(data).json()['accepted'],4)
        self.assertTrue(self.post(data).json()['replayed'])
        self.assertEqual(self.post(body(rows)).json()['duplicates'],4)
        self.assertEqual(self.snapshot()['series']['sleep'][-1],105)
    def test_hrv_conversion(self):
        r=sample(); r.update(type=HRV,kind='quantity',value=.055,unit='s',end=r['start']);r.pop('category')
        self.assertEqual(self.post(body([r])).status_code,200)
        with ws.open_workspace() as db:
            s=db.execute('SELECT value,unit,source FROM samples').fetchone()
            self.assertEqual(tuple(s),(55.0,'ms','watch_1'))
    def test_atomic_bad_input_and_conflict(self):
        good=sample();bad=sample();bad['category']=99
        self.assertEqual(self.post(body([good,bad])).status_code,400)
        self.assertEqual(self.post(body([good])).json()['accepted'],1)
        changed={**good,'category':4}
        self.assertEqual(self.post(body([changed,sample()])).status_code,400)
        with ws.open_workspace() as db:self.assertEqual(db.execute('SELECT count(*) FROM samples').fetchone()[0],1)
    def test_delete_and_late_replay(self):
        r=sample();self.post(body([r]))
        deletion={'uuid':r['uuid'].upper(),'type':SLEEP}
        self.assertEqual(self.post(body(deletions=[deletion])).json()['deleted'],1)
        self.assertEqual(self.post(body([r])).json()['accepted'],0)
        with ws.open_workspace() as db:self.assertEqual(db.execute('SELECT count(*) FROM samples').fetchone()[0],0)
    def test_delete_one_identity_keeps_other(self):
        a=sample();b={**a,'uuid':str(uuid4())};self.post(body([a,b]))
        self.assertEqual(self.post(body(deletions=[{'uuid':a['uuid'],'type':SLEEP}])).json()['deleted'],0)
        with ws.open_workspace() as db:self.assertEqual(db.execute('SELECT count(*) FROM identities').fetchone()[0],1)
    def test_user_binding_and_restart(self):
        data=body([sample()]);self.post(data)
        with TestClient(create_receiver('secret')) as c:
            r=c.post('/v1/batches',content=data,headers=self.headers)
            self.assertTrue(r.json()['replayed'])
        self.assertEqual(self.post(body([sample()]),{**self.headers,'X-User-ID':str(uuid4())}).status_code,403)
    def test_bad_protocol_counts_and_ignored_types(self):
        self.assertEqual(self.post(body(),{**self.headers,'X-Puls-Protocol':'2'}).json()['supportedVersions'],[1])
        self.assertEqual(self.post(gzip.compress(b'{"sampleCount":1}\n')).status_code,400)
        r=sample();r['type']='HKQuantityTypeIdentifierBodyMass'
        self.assertEqual(self.post(body([r])).json()['ignored'],1)
        with ws.open_workspace() as db:self.assertEqual(db.execute('SELECT count(*) FROM samples').fetchone()[0],0)
