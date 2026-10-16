"""Offline tests: no Cloudflare requests or DNS writes are performed."""
import contextlib,copy,datetime,importlib.util,os,pathlib,runpy,sys,tempfile,types,unittest
from unittest import mock
ROOT=pathlib.Path(__file__).resolve().parents[1]
TEMP=tempfile.TemporaryDirectory(prefix='cfdata-share-test-')
os.environ['POLICY_DATA_DIR']=TEMP.name
sys.path.insert(0,str(ROOT/'app'))
if sys.platform=='win32':sys.modules['fcntl']=types.SimpleNamespace()
import dns_policy as policy
import entrypoint
class PolicyTests(unittest.TestCase):
    def test_boundaries(self):
        good={'latency_ms':64.999,'speed_MBps':8.001,'loss':0}
        self.assertTrue(policy.acceptable(good))
        for field,value in [('latency_ms',65),('speed_MBps',8),('loss',.1),('speed_MBps',None)]:self.assertFalse(policy.acceptable({**good,field:value}))
    def test_priority(self):
        rows=[{'latency_ms':50,'speed_MBps':20,'loss':0},{'latency_ms':49,'speed_MBps':9,'loss':0},{'latency_ms':50,'speed_MBps':21,'loss':0}]
        self.assertEqual([r['speed_MBps'] for r in sorted(rows,key=policy.ranking)],[9,21,20])
    def test_ordered_import(self):
        self.assertEqual(policy.parse_addresses('104.16.0.2:443#HKG\n104.16.0.1/32\n104.16.0.2/32'),['104.16.0.2','104.16.0.1'])
        with self.assertRaises(ValueError):policy.parse_addresses('192.0.2.1')
    def test_scheduler(self):
        sunday=datetime.datetime(2026,10,18,3,17)
        self.assertEqual(entrypoint.schedule_due(sunday,{},6,'03:17',7),[('screen','2026-10-18')])
        self.assertEqual(entrypoint.schedule_due(sunday,{'screen':'2026-10-18'},6,'03:17',7),[])
        self.assertEqual(entrypoint.schedule_due(sunday.replace(minute=7),{},6,'03:17',7),[('hourly','2026-10-18T03')])
    def test_every_address(self):
        tools=runpy.run_path(str(ROOT/'pc-tools/discover_pc.py'),run_name='test')
        self.assertEqual(tools['enumerate_batch'](['104.16.0.0/23'],254,4),['104.16.0.254','104.16.0.255','104.16.1.0','104.16.1.1'])
    def test_configured_domain(self):
        import auto_dns
        auto_dns.save('credentials.json',{'token':'test-only-not-a-real-token','zone':'test-zone'})
        auto_dns.save('policy.json',{'domain':'node.example.org'})
        with mock.patch.object(auto_dns,'api',return_value=[]) as api:
            auto_dns.records();self.assertEqual(api.call_args.args,('GET','zones/test-zone/dns_records?name=node.example.org'))
        (auto_dns.ROOT/'policy.json').unlink()
    def test_ordered_failover_and_fifth_failure(self):
        ips=['104.16.0.1','104.16.0.2','104.16.0.3'];good={'latency_ms':50,'speed_MBps':9,'loss':0}
        for count,triggers_expected in [(3,0),(4,1)]:
            memory={'queue.json':{'generation':'test','items':ips},'policy-state.json':{'failures_since_screen':count,'replacements_since_screen':count}}
            current={'ip':ips[0]};seen=[];triggers=[]
            def measure(ip,*args):
                seen.append(ip);return {**good,'ip':ip,'latency_ms':66 if ip==ips[0] else 50,'speed_MBps':8 if ip==ips[1] else 9}
            def update(ip,expected):self.assertEqual(expected,current['ip']);current['ip']=ip
            with mock.patch.object(policy,'load',side_effect=lambda n,d=None:copy.deepcopy(memory.get(n,d))),mock.patch.object(policy.shared,'save',side_effect=lambda n,v:memory.__setitem__(n,copy.deepcopy(v))),mock.patch.object(policy,'lock',side_effect=lambda *a,**k:contextlib.nullcontext()),mock.patch.object(policy,'measure',side_effect=measure),mock.patch.object(policy,'set_dns',side_effect=update),mock.patch.object(policy,'dns_record',side_effect=lambda:({},{'content':current['ip']})),mock.patch.object(policy,'trigger_screen',side_effect=triggers.append),mock.patch.object(policy,'emit'):
                policy._hourly()
            self.assertEqual(seen,ips);self.assertEqual(current['ip'],ips[2]);self.assertEqual(len(triggers),triggers_expected)
            self.assertEqual(memory['policy-state.json']['failures_since_screen'],count+1)
    def test_lock_contention(self):
        from file_locks import lock_path
        p=pathlib.Path(TEMP.name)/'contention.lock'
        with lock_path(p):
            with self.assertRaises(BlockingIOError):
                with lock_path(p,False):pass
    def test_trigger_uses_real_script(self):
        self.assertTrue(policy.SCRIPT.is_file())
        self.assertEqual(policy.SCRIPT.parent,ROOT/'app')
    def test_screen_uses_only_source_library(self):
        source=pathlib.Path(TEMP.name)/'source-ipv4.txt';source.write_text('104.16.0.1/32\n104.16.0.2/32\n')
        memory={'queue.json':{'generation':'old','items':['104.16.0.99']},'policy-state.json':{'failures_since_screen':5}}
        visited=[];good={'latency_ms':50,'speed_MBps':9,'loss':0}
        def precheck(ip,*args):visited.append(ip);return {**good,'ip':ip}
        with mock.patch.object(policy,'config',return_value={**policy.DEFAULT,'source':str(source),'screen_workers':2}),mock.patch.object(policy,'load',side_effect=lambda n,d=None:copy.deepcopy(memory.get(n,d))),mock.patch.object(policy.shared,'save',side_effect=lambda n,v:memory.__setitem__(n,copy.deepcopy(v))),mock.patch.object(policy,'lock',side_effect=lambda *a,**k:contextlib.nullcontext()),mock.patch.object(policy,'tcp_metrics',side_effect=precheck),mock.patch.object(policy,'region',return_value='HKG'),mock.patch.object(policy,'measure',side_effect=lambda ip:{**good,'ip':ip}),mock.patch.object(policy,'dns_record',return_value=({},{'content':'104.16.0.99'})),mock.patch.object(policy,'set_dns'),mock.patch.object(policy,'emit'),mock.patch.object(policy.time,'sleep'):
            policy._screen('test')
        self.assertEqual(set(visited),{'104.16.0.1','104.16.0.2'})
        self.assertNotIn('104.16.0.99',memory['queue.json']['items'])
        self.assertEqual(memory['policy-state.json']['failures_since_screen'],0)
if __name__=='__main__':
    try:unittest.main()
    finally:TEMP.cleanup()
