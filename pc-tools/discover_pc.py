"""PC-only exhaustive HKG discovery. No downloads and no DNS API writes."""
import concurrent.futures, csv, hashlib, http.client, ipaddress, json, os, pathlib, socket, sqlite3, ssl, sys, time, traceback
ROOT = pathlib.Path(__file__).resolve().parent
CONCURRENCY = int(os.environ.get("SCAN_CONCURRENCY", "100"))
BATCH = max(256, CONCURRENCY * 2)
TLS = ssl.create_default_context()

def replace_report(temp, target):
    for attempt in range(12):
        try:
            temp.replace(target)
            return
        except PermissionError:
            time.sleep(0.15)
    content = temp.read_bytes()
    try:
        target.write_bytes(content)
    except PermissionError:
        target.with_name(target.name + '.latest').write_bytes(content)

def atomic(name, data):
    p = ROOT / (name + '.tmp')
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    replace_report(p, ROOT / name)

def enumerate_batch(nets, offset, count):
    out = []
    for raw in nets:
        net = ipaddress.IPv4Network(raw)
        if offset >= net.num_addresses:
            offset -= net.num_addresses
            continue
        first = int(net.network_address) + offset
        n = min(count - len(out), int(net.broadcast_address) - first + 1)
        out.extend((str(ipaddress.IPv4Address(first + i)) for i in range(n)))
        offset = 0
        if len(out) == count:
            break
    return out

def probe(ip):
    sock = None
    try:
        sock = socket.create_connection((ip, 443), 3)
        sock.settimeout(3)
        sock = TLS.wrap_socket(sock, server_hostname='speed.cloudflare.com')
        sock.sendall(b'GET /cdn-cgi/trace HTTP/1.1\r\nHost: speed.cloudflare.com\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n')
        response = http.client.HTTPResponse(sock)
        response.begin()
        status = response.status
        body = response.read(4096).decode('utf-8', 'replace')
        response.close()
        if status != 200:
            return (ip, 'http_error', None)
        fields = dict((line.split('=', 1) for line in body.splitlines() if '=' in line))
        colo = fields.get('colo', '')
        if not colo:
            return (ip, 'no_colo', None)
        if colo != 'HKG':
            return (ip, 'colo:' + colo, None)
    except (OSError, ssl.SSLError, http.client.HTTPException):
        return (ip, 'unreachable', None)
    finally:
        if sock:
            try:
                sock.close()
            except OSError:
                pass
    return (ip, 'HKG', (None, None, 0, 0, None, time.time()))

def export(db, complete=False):
    suffix = '' if complete else '.partial'
    queries = {'hkg-all': ('1=1', ())}
    for name, (where, args) in queries.items():
        p = ROOT / (name + suffix + '.txt')
        tmp = p.with_suffix('.tmp')
        with tmp.open('w', encoding='utf-8') as f:
            for ip, in db.execute('SELECT ip FROM hkg WHERE ' + where + ' ORDER BY average_ms', args):
                f.write(ip + '/32\n')
        replace_report(tmp, p)
    p = ROOT / ('hkg-details' + suffix + '.csv')
    tmp = p.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['IPv4', '机房', '识别时间戳'])
        for r in db.execute('SELECT ip,tested_at FROM hkg ORDER BY ip'):
            writer.writerow([r[0], 'HKG', r[1]])
    replace_report(tmp, p)

def main():
    import msvcrt
    lock = (ROOT / 'scan.lock').open('a+b')
    lock.write(b'0')
    lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        print('A discovery task is already running', flush=True)
        return
    db = sqlite3.connect(ROOT / 'results.sqlite')
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS meta (id INTEGER PRIMARY KEY,data TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS hkg (ip TEXT PRIMARY KEY,initial_ms REAL,average_ms REAL,success INTEGER,failed INTEGER,maximum_ms REAL,tested_at REAL)')
    raw = (ROOT / 'source-ipv4.txt').read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    prior = db.execute('SELECT data FROM meta WHERE id=1').fetchone()
    if prior:
        state = json.loads(prior[0])
        if state['source_sha256'] != digest:
            raise RuntimeError('Source library changed; use a separate job folder')
    else:
        lines = raw.decode('utf-8-sig').splitlines()
        nets = list(ipaddress.collapse_addresses((ipaddress.IPv4Network(s.strip(), strict=False) for s in lines if s.strip() and (not s.startswith('#')))))
        state = {'source_sha256': digest, 'networks': [str(n) for n in nets], 'total': sum((n.num_addresses for n in nets)), 'checked': 0, 'started_at': time.time(), 'outcomes': {}}
    last_export = 0
    old_failure = ROOT / 'failure.json'
    if old_failure.exists():
        replace_report(old_failure, ROOT / ('failure-history-' + str(int(time.time())) + '.json'))

    def checkpoint(status):
        state['status'] = status
        state['updated_at'] = time.time()
        state['hkg_count'] = db.execute('SELECT count(*) FROM hkg').fetchone()[0]
        state.pop('under100ms_usable', None)
        state.pop('under100ms_zero_loss', None)
        db.execute('INSERT OR REPLACE INTO meta VALUES (1,?)', (json.dumps(state),))
        db.commit()
        public = {k: v for k, v in state.items() if k != 'networks'}
        public['concurrency'] = CONCURRENCY
        public['mode'] = 'HKG identification only; every IPv4; no latency, loss, speed tests or DNS updates'
        atomic('progress.json', public)
        print(json.dumps(public, ensure_ascii=False), flush=True)
    checkpoint('running on PC')
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        while state['checked'] < state['total']:
            batch = enumerate_batch(state['networks'], state['checked'], BATCH)
            for ip, reason, detail in pool.map(probe, batch):
                state['outcomes'][reason] = state['outcomes'].get(reason, 0) + 1
                if detail:
                    db.execute('INSERT OR REPLACE INTO hkg VALUES (?,?,?,?,?,?,?)', (ip, *detail))
            state['checked'] += len(batch)
            checkpoint('running on PC')
            if time.time() - last_export > 60:
                export(db)
                last_export = time.time()
    checkpoint('complete; preparing filtered libraries')
    export(db, True)
    checkpoint('complete; local results ready')
    db.close()
if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        atomic('failure.json', {'time': time.time(), 'error_type': type(e).__name__, 'traceback': traceback.format_exc(), 'checkpoint': 'retained; restart same job to resume'})
        print('Discovery stopped:', type(e).__name__, flush=True)
        raise SystemExit(1)
