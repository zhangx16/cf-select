"""Latency-only filtering of the completed HKG library; never updates DNS."""
import concurrent.futures, csv, hashlib, ipaddress, json, os, pathlib, socket, sqlite3, sys, time, traceback
from discover_pc import replace_report
ROOT = pathlib.Path(__file__).resolve().parent
WORKERS = int(os.environ.get("LATENCY_CONCURRENCY", "200"))
BATCH = 512
SAMPLES = 10
TIMEOUT = 1.0

def save(name, data):
    p = ROOT / (name + '.tmp')
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    replace_report(p, ROOT / name)

def measure(ip):
    values = []
    for _ in range(SAMPLES):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)
        start = time.perf_counter()
        try:
            sock.connect((ip, 443))
            values.append((time.perf_counter() - start) * 1000)
        except OSError:
            pass
        finally:
            sock.close()
    return (ip, sum(values) / len(values) if values else None, min(values) if values else None, max(values) if values else None, len(values), SAMPLES - len(values), time.time())

def export(db, complete=False):
    suffix = '' if complete else '.partial'
    target = ROOT / ('hkg-under100ms' + suffix + '.txt')
    temp = target.with_suffix('.tmp')
    with temp.open('w', encoding='utf-8') as f:
        for ip, in db.execute('SELECT ip FROM latency WHERE success>0 AND average_ms<100 ORDER BY average_ms,ip'):
            f.write(ip + '/32\n')
    replace_report(temp, target)
    target = ROOT / ('hkg-latency-details' + suffix + '.csv')
    temp = target.with_suffix('.tmp')
    with temp.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['IPv4', '平均TCP延迟ms', '最低ms', '最高ms', '成功次数', '失败次数', '测试时间戳', '保留'])
        for r in db.execute('SELECT ip,average_ms,minimum_ms,maximum_ms,success,failed,tested_at FROM latency ORDER BY average_ms,ip'):
            w.writerow([*r, bool(r[1] is not None and r[1] < 100 and (r[4] > 0))])
    replace_report(temp, target)

def main():
    import msvcrt
    lock = (ROOT / 'latency.lock').open('a+b')
    lock.write(b'0')
    lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        print('Latency task is already running', flush=True)
        return
    source = (ROOT / 'hkg-all.txt').read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    ips = list(dict.fromkeys((str(ipaddress.IPv4Network(s).network_address) for s in source.decode('utf-8-sig').splitlines() if s.strip())))
    db = sqlite3.connect(ROOT / 'latency.sqlite')
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS meta (id INTEGER PRIMARY KEY,data TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS latency (ip TEXT PRIMARY KEY,average_ms REAL,minimum_ms REAL,maximum_ms REAL,success INTEGER,failed INTEGER,tested_at REAL)')
    old = db.execute('SELECT data FROM meta WHERE id=1').fetchone()
    state = json.loads(old[0]) if old else {'total': len(ips), 'checked': 0, 'source_sha256': digest, 'started_at': time.time()}
    if state['source_sha256'] != digest:
        raise RuntimeError('HKG source changed')

    def checkpoint(status):
        state.update(status=status, updated_at=time.time(), concurrency=WORKERS, samples=SAMPLES, timeout_seconds=TIMEOUT, criterion='average successful TCP 443 latency strictly <100ms; no extra packet-loss filter')
        state['retained'] = db.execute('SELECT count(*) FROM latency WHERE success>0 AND average_ms<100').fetchone()[0]
        state['unreachable'] = db.execute('SELECT count(*) FROM latency WHERE success=0').fetchone()[0]
        state['at_least100ms'] = db.execute('SELECT count(*) FROM latency WHERE success>0 AND average_ms>=100').fetchone()[0]
        db.execute('INSERT OR REPLACE INTO meta VALUES(1,?)', (json.dumps(state),))
        db.commit()
        save('latency-progress.json', state)
        print(json.dumps(state), flush=True)
    checkpoint('running on PC')
    last_export = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        while state['checked'] < len(ips):
            batch = ips[state['checked']:state['checked'] + BATCH]
            for row in pool.map(measure, batch):
                db.execute('INSERT OR REPLACE INTO latency VALUES(?,?,?,?,?,?,?)', row)
            state['checked'] += len(batch)
            checkpoint('running on PC')
            if time.time() - last_export > 60:
                export(db)
                last_export = time.time()
    export(db, True)
    checkpoint('complete; filtered library ready')
    checkpoint('complete; local results ready')
    db.close()
if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        save('latency-failure.json', {'time': time.time(), 'error_type': type(e).__name__, 'traceback': traceback.format_exc(), 'checkpoint': 'retained'})
        print('Latency task stopped:', type(e).__name__, flush=True)
        raise SystemExit(1)
