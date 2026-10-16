"""Ordered DNS failover, hourly health checks, and weekly HKG screening."""
import concurrent.futures,contextlib,datetime,http.client,ipaddress,json,os,pathlib,re,socket,ssl,subprocess,sys,time
from file_locks import lock_path
import auto_dns as shared
ROOT=shared.ROOT
SCRIPT=pathlib.Path(__file__).resolve()
HOST=os.environ.get('SPEED_TEST_HOST','speed.okl.abrdns.com')
TLS=ssl.create_default_context()
DEFAULT={'domain':'hk.example.com','latency_limit_ms':65,'speed_min_MBps':8,'loss_max':0.1,'samples':10,'tcp_timeout':1,'replacement_limit':5,'screen_workers':16,'queue_target':100,'source':'/data/source-ipv4.txt'}
def load(name,default=None):
    p=ROOT/name
    return json.loads(p.read_text()) if p.exists() else default
def config():return {**DEFAULT,**load('policy.json',{})}
def emit(event,**data):
    print(json.dumps({'time':datetime.datetime.now().astimezone().isoformat(),'event':event,**data},ensure_ascii=False),flush=True)
@contextlib.contextmanager
def lock(name,blocking=True):
    with lock_path(ROOT/name,blocking):yield
def parse_addresses(text):
    result=[];seen=set()
    for line in text.splitlines():
        value=line.split('#',1)[0].strip()
        if not value:continue
        value=value.split('/')[0]
        if ':' in value:
            value,port=value.rsplit(':',1)
            if int(port)!=443:raise ValueError('Only TCP443 candidates are supported')
        ip=ipaddress.IPv4Address(value)
        if not ip.is_global:raise ValueError('Candidate must be public IPv4')
        if str(ip) not in seen:result.append(str(ip));seen.add(str(ip))
    return result
def acceptable(m,c=None):
    c=c or config()
    return bool(m.get('latency_ms') is not None and m['latency_ms']<c['latency_limit_ms'] and m.get('speed_MBps') is not None and m['speed_MBps']>c['speed_min_MBps'] and m.get('loss',1)<c['loss_max'])
def ranking(m):return (m['latency_ms'],-m['speed_MBps'],m['loss'])
def tcp_metrics(ip,c=None):
    c=c or config();values=[]
    for _ in range(c['samples']):
        s=socket.socket(socket.AF_INET,socket.SOCK_STREAM);s.settimeout(c['tcp_timeout']);start=time.perf_counter()
        try:s.connect((ip,443));values.append((time.perf_counter()-start)*1000)
        except OSError:pass
        finally:s.close()
    return {'ip':ip,'latency_ms':sum(values)/len(values) if values else None,'loss':(c['samples']-len(values))/c['samples'],'successes':len(values)}
class DirectHTTPS(http.client.HTTPSConnection):
    def __init__(self,ip,host,timeout=8):
        self.target_ip=ip;super().__init__(host,443,timeout=timeout,context=TLS)
    def connect(self):
        raw=socket.create_connection((self.target_ip,443),self.timeout)
        try:self.sock=TLS.wrap_socket(raw,server_hostname=self.host)
        except Exception:raw.close();raise
def region(ip):
    conn=DirectHTTPS(ip,'speed.cloudflare.com',4)
    try:
        conn.request('GET','/cdn-cgi/trace',headers={'User-Agent':'Mozilla/5.0','Connection':'close'})
        r=conn.getresponse();body=r.read(4096).decode(errors='replace')
        if r.status!=200:return None
        return dict(line.split('=',1) for line in body.splitlines() if '=' in line).get('colo')
    except (OSError,http.client.HTTPException):return None
    finally:conn.close()
def speed(ip):
    conn=DirectHTTPS(ip,HOST,8)
    try:
        conn.request('GET','/',headers={'User-Agent':'Mozilla/5.0','Accept-Encoding':'identity'})
        r=conn.getresponse()
        if r.status!=200:return None
        start=time.monotonic();deadline=start+6;size=0
        while time.monotonic()<deadline:
            if conn.sock:conn.sock.settimeout(max(.05,min(2,deadline-time.monotonic())))
            try:b=r.read1(65536)
            except (socket.timeout,TimeoutError):break
            if not b:break
            size+=len(b)
        elapsed=time.monotonic()-start
        return size/elapsed/1024/1024 if elapsed>0 and size>0 else None
    except (OSError,http.client.HTTPException):return None
    finally:conn.close()
def measure(ip,priority=False):
    if priority:(ROOT/'monitor.priority').touch()
    while True:
        marker=ROOT/'monitor.priority'
        if not priority and marker.exists() and time.time()-marker.stat().st_mtime<1800:time.sleep(.5);continue
        with lock('bandwidth.lock'):
            if not priority and marker.exists() and time.time()-marker.stat().st_mtime<1800:continue
            m=tcp_metrics(ip);m['speed_MBps']=speed(ip);m['checked_at']=time.time()
            return m
def dns_record():
    cfg,rr=shared.records();a=[r for r in rr if r['type']=='A']
    if len(a)>1 or any(r['type']=='CNAME' for r in rr):raise RuntimeError('DNS record conflict')
    return cfg,a[0] if a else None
def set_dns(ip,expected):
    cfg,current=dns_record()
    if (current['content'] if current else None)!=expected:raise RuntimeError('DNS changed during health test')
    body={'type':'A','name':config()['domain'],'content':ip,'ttl':300,'proxied':False}
    path=f"zones/{cfg['zone']}/dns_records"+('/'+current['id'] if current else '')
    shared.api('PATCH' if current else 'POST',path,body)
    _,check=dns_record()
    if not check or check['content']!=ip or check['proxied'] or check['ttl']!=300:raise RuntimeError('DNS update verification failed')
def trigger_screen(reason):
    shared.save('screen-request.json',{'time':time.time(),'reason':reason})
    with (ROOT/'screen.log').open('ab') as out:
        options={'creationflags':subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP} if os.name=='nt' else {'start_new_session':True}
        subprocess.Popen([sys.executable,str(SCRIPT),'screen',reason],stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT,**options)
    emit('screen_requested',reason=reason)
def initialize():
    ips=parse_addresses((ROOT/'manual-priority.txt').read_text(encoding='utf-8-sig'))
    if not ips:raise RuntimeError('Empty input queue')
    with lock('control.lock'):
        _,old=dns_record();shared.save('dns-before-policy.json',old)
        set_dns(ips[0],old['content'] if old else None)
        generation=str(time.time_ns())
        shared.save('queue.json',{'generation':generation,'created_at':time.time(),'source':'user ordered export','items':ips})
        state={'generation':generation,'active_ip':ips[0],'active_index':0,'replacements_since_screen':0,'failures_since_screen':0,'last_screen_at':time.time(),'initialized_at':time.time()}
        shared.save('policy-state.json',state)
    emit('initialized',active_ip=ips[0],queue_size=len(ips),replacements_since_screen=0)
def hourly():
    try:
        with lock('hourly.lock',False):_hourly()
    except BlockingIOError:emit('hourly_already_running')
def _hourly():
    marker=ROOT/'monitor.priority';marker.touch()
    try:
        q=load('queue.json');items=q['items'];_,record=dns_record()
        if not record:trigger_screen('DNS A record missing');return
        current=record['content'];m=measure(current,True);emit('current_health',**m,qualified=acceptable(m))
        shared.save('last-health.json',m)
        if acceptable(m):
            with lock('control.lock'):
                if load('queue.json')['generation']!=q['generation']:return
                state=load('policy-state.json',{});state.update(active_ip=current,last_health=m)
                if current in items:state['active_index']=items.index(current)
                shared.save('policy-state.json',state)
            return
        with lock('control.lock'):
            if load('queue.json')['generation']!=q['generation']:return
            state=load('policy-state.json',{})
            failures=int(state.get('failures_since_screen',state.get('replacements_since_screen',0)))+1
            state.update(failures_since_screen=failures,last_failure_at=time.time(),last_health=m)
            shared.save('policy-state.json',state)
        rescreen_requested=failures>=config()['replacement_limit']
        if rescreen_requested:trigger_screen('five selected-IP failures since last successful screening')
        start=items.index(current)+1 if current in items else 0
        for index in range(start,len(items)):
            marker.touch();candidate=items[index];test=measure(candidate,True)
            emit('fallback_health',queue_index=index+1,**test,qualified=acceptable(test))
            if not acceptable(test):continue
            with lock('control.lock'):
                latest=load('queue.json')
                if latest['generation']!=q['generation']:emit('queue_changed_retry_next_check');return
                set_dns(candidate,current)
                state=load('policy-state.json',{})
                count=int(state.get('replacements_since_screen',0))+1
                state.update(active_ip=candidate,active_index=index,last_health=test,replacements_since_screen=count,last_replacement_at=time.time())
                shared.save('policy-state.json',state)
            emit('dns_replaced',previous_ip=current,active_ip=candidate,replacements_since_screen=count)
            return
        emit('queue_exhausted',active_ip=current)
        if not rescreen_requested:trigger_screen('no remaining queued IP meets all thresholds')
    finally:
        try:marker.unlink()
        except FileNotFoundError:pass
def screen(reason='weekly'):
    try:
        with lock('screen.lock',False):_screen(reason)
    except BlockingIOError:emit('screen_already_running')
def _screen(reason):
    c=config()
    source=pathlib.Path(c['source'])
    ips=parse_addresses(source.read_text())
    shared.save('screen-status.json',{'status':'checking latency and HKG','started_at':time.time(),'total':len(ips),'reason':reason})
    def precheck(ip):
        m=tcp_metrics(ip,c)
        if m['latency_ms'] is None or m['latency_ms']>=c['latency_limit_ms'] or m['loss']>=c['loss_max']:return None
        return m if region(ip)=='HKG' else None
    viable=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=c['screen_workers']) as pool:
        for m in pool.map(precheck,ips):
            if m:viable.append(m)
    viable.sort(key=lambda m:m['latency_ms']);selected=[]
    shared.save('screen-status.json',{'status':'testing mobile download speed','total':len(ips),'latency_qualified':len(viable),'reason':reason,'time':time.time()})
    for n,m in enumerate(viable):
        fresh=measure(m['ip']);emit('screen_speed',tested=n+1,**fresh,qualified=acceptable(fresh))
        if acceptable(fresh):selected.append(fresh)
        if len(selected)>=c['queue_target']:break
        time.sleep(1.2)
    if not selected:
        shared.save('screen-status.json',{'status':'no qualified IP; queue and DNS preserved','time':time.time(),'reason':reason});return
    selected.sort(key=ranking)
    with lock('control.lock'):
        _,old=dns_record();set_dns(selected[0]['ip'],old['content'] if old else None)
        generation=str(time.time_ns());items=[m['ip'] for m in selected]
        shared.save('queue.previous.json',load('queue.json'))
        shared.save('queue.json',{'generation':generation,'created_at':time.time(),'source':str(source),'items':items,'metrics':selected})
        state=load('policy-state.json',{});state.update(generation=generation,active_ip=items[0],active_index=0,replacements_since_screen=0,failures_since_screen=0,last_screen_at=time.time(),last_health=selected[0])
        shared.save('policy-state.json',state)
    shared.save('screen-status.json',{'status':'complete; queue and DNS refreshed','count':len(items),'active_ip':items[0],'time':time.time(),'reason':reason})
    emit('screen_complete',queue_size=len(items),active_ip=items[0],replacements_since_screen=0)
if __name__=='__main__':
    try:
        mode=sys.argv[1]
        if mode=='initialize':initialize()
        elif mode=='hourly':hourly()
        elif mode=='screen':screen(sys.argv[2] if len(sys.argv)>2 else 'weekly')
        elif mode=='inspect':print(json.dumps({'state':load('policy-state.json'),'queue_size':len(load('queue.json',{'items':[]})['items']),'config':config()},ensure_ascii=False))
        else:raise ValueError('Unknown mode')
    except Exception as e:
        emit('policy_error',mode=sys.argv[1] if len(sys.argv)>1 else '',error_type=type(e).__name__)
        raise SystemExit(1)
