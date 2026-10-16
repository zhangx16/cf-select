"""Optional network smoke test. DNS automation is forcibly disabled."""
import json,os,pathlib,subprocess,sys,tempfile,time,urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='cf-select-smoke-') as folder:
    data=pathlib.Path(folder)
    env={**os.environ,'CFDATA_DATA_DIR':str(data),'SOURCE_FILE':str(data/'source-ipv4.txt'),'WEB_PORT':'14335','WEB_BIND_HOST':'127.0.0.1','DNS_AUTOMATION_ENABLED':'false','CF_API_TOKEN':'','CF_ZONE_ID':'','WEB_USERNAME':'','WEB_PASSWORD':''}
    options={'creationflags':subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP} if os.name=='nt' else {'start_new_session':True}
    log=data/'smoke.log'
    with log.open('wb') as output:
        proc=subprocess.Popen([sys.executable,str(ROOT/'desktop/launch.py')],cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,**options)
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));ready=False
        for _ in range(60):
            if proc.poll() is not None:raise RuntimeError('Desktop supervisor exited: '+log.read_text(errors='replace')[-1200:])
            try:
                with opener.open('http://127.0.0.1:14335/',timeout=1) as r:
                    body=r.read();assert r.status==200 and b'CFData' in body;ready=True;break
            except OSError:time.sleep(1)
        assert ready,'Web startup timed out'
        assert not (data/'auto-dns/credentials.json').exists()
        assert not (data/'auto-dns/queue.json').exists()
        print('PASS: native desktop Web HTTP200; automation disabled; no token or DNS queue created')
    finally:
        if proc.poll() is None:
            if os.name=='nt':subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            else:
                import signal
                os.killpg(proc.pid,signal.SIGTERM)
            proc.wait(timeout=20)
