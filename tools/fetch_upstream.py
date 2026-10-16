"""Download the pinned official CFData binary and verify its published checksum."""
import argparse,hashlib,pathlib,platform,time,urllib.request
VERSION='v1.8.3'
CHECKSUMS={
 'cfdata-linux-arm64':'5bbf69d20826964d27c708c2ccd40b5625edf1753067a2dffd9f56767709f299',
 'cfdata-linux-amd64':'af19422b8c016e347f44d6ea86afb3b2ab874b9bffb10af5bba620bffbb1ca5e',
 'cfdata-windows-amd64.exe':'06e80b2c561221d45323da5d14d3a84c512d6c81089270d4cea46289872d04f8',
 'cfdata-windows-arm64.exe':'4498a5e73f074d50e5ad4701f5e4c558824c1c9b07a91dbfcc00223407892b11'}
def machine_arch():
    arch={'x86_64':'amd64','amd64':'amd64','aarch64':'arm64','arm64':'arm64'}.get(platform.machine().lower())
    if not arch:raise RuntimeError('Supported architectures: amd64 and arm64')
    return arch
def fetch(system,arch,directory):
    name=f'cfdata-{system}-{arch}'+('.exe' if system=='windows' else '')
    if name not in CHECKSUMS:raise ValueError('Unsupported platform')
    directory=pathlib.Path(directory);directory.mkdir(parents=True,exist_ok=True);target=directory/name
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest()!=CHECKSUMS[name]:raise RuntimeError('Existing binary checksum mismatch; move it aside before retrying')
        return target
    url=f'https://github.com/PoemMisty/CFData-WEB/releases/download/{VERSION}/{name}'
    temp=directory/(name+'.download')
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url,timeout=45) as response,temp.open('wb') as out:
                while block:=response.read(262144):out.write(block)
            if hashlib.sha256(temp.read_bytes()).hexdigest()!=CHECKSUMS[name]:raise RuntimeError('Downloaded binary checksum mismatch')
            temp.chmod(0o755);temp.replace(target);print('Verified official binary:',name,flush=True);return target
        except (OSError,TimeoutError):
            if attempt==2:raise
            time.sleep(attempt+1)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--system',default=platform.system().lower(),choices=['linux','windows']);parser.add_argument('--arch',default=machine_arch(),choices=['amd64','arm64']);parser.add_argument('--directory',default=str(pathlib.Path(__file__).resolve().parents[1]/'bin'))
    args=parser.parse_args();fetch(args.system,args.arch,args.directory)
