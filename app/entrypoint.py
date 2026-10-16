"""Start CFData Web and supervise its optional DNS policy scheduler."""
import datetime,hashlib,json,os,pathlib,platform,shutil,signal,subprocess,sys,time
import auto_dns as storage
DATA=pathlib.Path(os.environ.get('CFDATA_DATA_DIR','/data')).resolve();STOP=False
def enabled(value):return str(value).lower() in ('1','true','yes','on')
def setting(name,default):return os.environ.get(name,str(default))
def prepare():
    DATA.mkdir(exist_ok=True);os.chmod(storage.ROOT,0o700)
    arch={'aarch64':'arm64','arm64':'arm64','x86_64':'amd64','amd64':'amd64'}.get(platform.machine().lower())
    if not arch:raise RuntimeError('Only Linux arm64 and amd64 are supported')
    system=platform.system().lower()
    if system not in ('linux','windows'):raise RuntimeError('Supported native systems: Windows and Linux')
    name='cfdata-'+system+'-'+arch+('.exe' if system=='windows' else '')
    source=pathlib.Path(setting('CFDATA_BINARY_DIR','/opt/cfdata/bin'))/name
    target=DATA/('cfdata.exe' if system=='windows' else 'cfdata')
    if not target.exists() or hashlib.sha256(source.read_bytes()).digest()!=hashlib.sha256(target.read_bytes()).digest():
        temporary=DATA/'cfdata.new';shutil.copyfile(source,temporary);temporary.chmod(0o755);temporary.replace(target)
    active=enabled(setting('DNS_AUTOMATION_ENABLED','false'))
    policy={'domain':setting('DNS_NAME','hk.example.com'),'latency_limit_ms':float(setting('LATENCY_LIMIT_MS',65)),'speed_min_MBps':float(setting('SPEED_MIN_MBPS',8)),'loss_max':float(setting('LOSS_LIMIT_PERCENT',10))/100,'samples':int(setting('TCP_SAMPLES',10)),'tcp_timeout':float(setting('TCP_TIMEOUT_SECONDS',1)),'replacement_limit':int(setting('FAILURE_TRIGGER',5)),'screen_workers':int(setting('SCREEN_WORKERS',16)),'queue_target':int(setting('QUEUE_TARGET',100)),'source':str(pathlib.Path(setting('SOURCE_FILE',DATA/'source-ipv4.txt')).resolve())}
    if policy['samples']<1 or policy['screen_workers']<1 or policy['queue_target']<1:raise ValueError('Positive sample/worker/queue counts required')
    storage.save('policy.json',policy)
    token=setting('CF_API_TOKEN','');zone=setting('CF_ZONE_ID','')
    if token and zone:storage.save('credentials.json',{'token':token,'zone':zone})
    if active:
        if policy['domain'].endswith('.example.com'):raise ValueError('Set DNS_NAME before enabling automation')
        if not (storage.ROOT/'credentials.json').exists():raise ValueError('Configure Cloudflare token and zone ID')
        if not pathlib.Path(policy['source']).is_file() or not pathlib.Path(policy['source']).stat().st_size:raise ValueError('Provide a nonempty SOURCE_FILE')
    return target,active
def schedule_due(now,last,weekday,weekly_time,hourly_minute):
    due=[];hour=now.strftime('%Y-%m-%dT%H');day=now.strftime('%Y-%m-%d')
    if now.minute==hourly_minute and last.get('hourly')!=hour:due.append(('hourly',hour))
    if now.weekday()==weekday and now.strftime('%H:%M')==weekly_time and last.get('screen')!=day:due.append(('screen',day))
    return due
def schedule_now():
    name=setting('TZ','Asia/Shanghai')
    if name=='Asia/Shanghai':return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    if name=='UTC':return datetime.datetime.now(datetime.timezone.utc)
    if name=='local':return datetime.datetime.now().astimezone()
    from zoneinfo import ZoneInfo
    return datetime.datetime.now(ZoneInfo(name))
def main():
    global STOP
    binary,active=prepare();jobs=[];web=None
    def stopping(*args):
        global STOP
        STOP=True
    signal.signal(signal.SIGTERM,stopping);signal.signal(signal.SIGINT,stopping)
    def start(mode,reason='scheduled'):
        log=storage.ROOT/('jobs-'+mode+'.log')
        if log.exists() and log.stat().st_size>5*1024*1024:log.replace(log.with_suffix('.log.1'))
        with log.open('ab') as out:
            args=[sys.executable,str(pathlib.Path(__file__).with_name('dns_policy.py')),mode]
            if mode=='screen':args.append(reason)
            options={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
            jobs.append(subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT,**options))
        print('DNS job started:',mode,flush=True)
    try:
        args=[str(binary),'-host',setting('WEB_BIND_HOST','0.0.0.0'),'-port',setting('WEB_PORT',13335),'-url',setting('SPEED_TEST_HOST','speed.okl.abrdns.com')]
        user=setting('WEB_USERNAME','');password=setting('WEB_PASSWORD','')
        if bool(user)!=bool(password):raise ValueError('Set both WEB_USERNAME and WEB_PASSWORD')
        if user:args+=['-user',user,'-password',password]
        options={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
        web=subprocess.Popen(args,cwd=DATA,stdin=subprocess.DEVNULL,**options)
        last=json.loads((storage.ROOT/'scheduler-state.json').read_text()) if (storage.ROOT/'scheduler-state.json').exists() else {}
        if active and not (storage.ROOT/'queue.json').exists():
            ordered=DATA/'manual-priority.txt'
            if enabled(setting('INITIALIZE_FROM_ORDERED_LIST','false')) and ordered.exists():
                shutil.copyfile(ordered,storage.ROOT/'manual-priority.txt');start('initialize')
            else:start('screen','first-start')
        print('DNS automation:', 'enabled' if active else 'disabled',flush=True)
        while not STOP:
            if web.poll() is not None:raise RuntimeError('CFData Web exited')
            jobs[:]=[job for job in jobs if job.poll() is None]
            if active:
                now=schedule_now()
                for mode,key in schedule_due(now,last,int(setting('WEEKLY_WEEKDAY',6)),setting('WEEKLY_TIME','03:17'),int(setting('HOURLY_MINUTE',7))):
                    if mode=='hourly' and not (storage.ROOT/'queue.json').exists():continue
                    start(mode);last[mode]=key;storage.save('scheduler-state.json',last)
            time.sleep(2)
    finally:
        for job in jobs+([web] if web else []):
            if job.poll() is None:
                job.terminate()
                try:job.wait(timeout=8)
                except subprocess.TimeoutExpired:job.kill();job.wait()
if __name__=='__main__':
    os.umask(0o077)
    try:main()
    except Exception as e:
        print('Startup/supervisor error:',type(e).__name__,str(e) if isinstance(e,(ValueError,RuntimeError)) else '',flush=True)
        raise SystemExit(1)
