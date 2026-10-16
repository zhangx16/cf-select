"""Small, configurable Cloudflare API adapter; contains no account credentials."""
import json,os,pathlib,time,urllib.error,urllib.parse,urllib.request
ROOT=pathlib.Path(os.environ.get('POLICY_DATA_DIR','/data/auto-dns'))
ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
def save(name,data):
    target=ROOT/name;temp=ROOT/(name+'.tmp')
    with temp.open('w',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    temp.chmod(0o600);temp.replace(target)
def settings():return json.loads((ROOT/'credentials.json').read_text(encoding='utf-8'))
def api(method,path,body=None):
    cfg=settings()
    req=urllib.request.Request('https://api.cloudflare.com/client/v4/'+path,data=json.dumps(body).encode() if body is not None else None,method=method,headers={'Authorization':'Bearer '+cfg['token'],'Content-Type':'application/json','User-Agent':'CFData-DNS-Automation/1.0'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req,timeout=25) as r:result=json.load(r)
            if not result.get('success'):raise RuntimeError('Cloudflare API unsuccessful')
            return result['result']
        except urllib.error.HTTPError as e:
            if method=='POST' or (e.code!=429 and e.code<500) or attempt==2:raise
        except (urllib.error.URLError,TimeoutError):
            if method=='POST' or attempt==2:raise
        time.sleep(2**attempt)
def records():
    cfg=settings();policy=json.loads((ROOT/'policy.json').read_text(encoding='utf-8'))
    name=policy['domain']
    query=urllib.parse.urlencode({'name':name})
    return cfg,api('GET',f"zones/{cfg['zone']}/dns_records?{query}")
