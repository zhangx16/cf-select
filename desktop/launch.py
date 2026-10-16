"""Native desktop entry point. Reads local settings without executing shell code."""
import os,pathlib,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
def read_env(path):
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line=line.strip()
        if not line or line.startswith('#'):continue
        key,separator,value=line.partition('=')
        if not separator or not key.replace('_','').isalnum():raise ValueError('Invalid local environment setting')
        if len(value)>1 and value[0]==value[-1] and value[0] in ('"',"'"):value=value[1:-1]
        os.environ.setdefault(key,value)
def configure_environment():
    if sys.version_info<(3,11):raise RuntimeError('Python 3.11 or newer is required')
    os.chdir(ROOT)
    config=ROOT/'desktop'/'.env'
    if not config.exists():config.write_bytes((ROOT/'desktop'/'.env.example').read_bytes())
    read_env(config)
    data=pathlib.Path(os.environ.get('CFDATA_DATA_DIR','data-desktop')).resolve();data.mkdir(parents=True,exist_ok=True)
    os.environ['CFDATA_DATA_DIR']=str(data);os.environ['POLICY_DATA_DIR']=str(data/'auto-dns');os.environ['CFDATA_BINARY_DIR']=str(ROOT/'bin')
    os.environ.setdefault('SOURCE_FILE',str(data/'source-ipv4.txt'))
    sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'app'))
    return data
def main():
    configure_environment()
    if sys.platform not in ('linux','win32'):raise RuntimeError('Native desktop launcher supports Windows and Linux')
    import fetch_upstream
    fetch_upstream.fetch(sys.platform if sys.platform=='linux' else 'windows',fetch_upstream.machine_arch(),ROOT/'bin')
    import entrypoint
    os.umask(0o077);entrypoint.main()
if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:pass
    except Exception as e:
        print('Desktop startup failed:',type(e).__name__,str(e) if isinstance(e,(ValueError,RuntimeError)) else '',flush=True);raise SystemExit(1)
