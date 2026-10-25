"""HashMargin local pilot API. Python 3.10+, standard library only.
No pool passwords, private keys, remote commands, or payment collection.
"""
import argparse
import tenant_store
import hashlib
import secrets
import re
import ipaddress
import socket
import smtplib
import ssl
from email.message import EmailMessage
import threading
import hmac
import json
import mimetypes
import os
import sqlite3
import time
import urllib.request
import urllib.error
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

DB = Path(os.environ.get('HASHMARGIN_DB', str(Path(__file__).resolve().parent / 'hashmargin.sqlite3')))
TOKEN = os.environ.get('HASHMARGIN_TOKEN', 
HOST = os.environ.get('HASHMARGIN_HOST', '0.0.0.0')
PORT = int(os.environ.get('PORT', os.environ.get('HASHMARGIN_PORT', '8787')))
MAX_BODY = 8192
TENANT_DB = Path(os.environ.get("HASHMARGIN_TENANT_DB",str(Path(__file__).resolve().parent / "tenants.sqlite3")))
BRAIINS_URL = 'https://pool.braiins.com/accounts/workers/json/btc'
BRAIINS_TOKEN = os.environ.get('HASHMARGIN_BRAIINS_TOKEN', '')
_LAST_SYNC = 0.0
SYNC_COOLDOWN = 30.0

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def connect():
    db=sqlite3.connect(DB)
    db.row_factory=sqlite3.Row
    return db

def init_db():
    with connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS miners (device_id TEXT PRIMARY KEY, name TEXT NOT NULL, hashrate_ths REAL NOT NULL, watts REAL NOT NULL, temperature_c REAL, last_seen REAL NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS samples (id INTEGER PRIMARY KEY, device_id TEXT NOT NULL, sampled_at REAL NOT NULL, hashrate_ths REAL NOT NULL, watts REAL NOT NULL, temperature_c REAL, source TEXT NOT NULL)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_samples_device_time ON samples(device_id, sampled_at)')
        db.execute('CREATE TABLE IF NOT EXISTS device_settings (device_id TEXT PRIMARY KEY, electricity_usd_kwh REAL NOT NULL DEFAULT 0.12, btc_per_th_day REAL NOT NULL DEFAULT 0, btc_price_usd REAL NOT NULL DEFAULT 0, pool_fee_percent REAL NOT NULL DEFAULT 2, other_usd_day REAL NOT NULL DEFAULT 0)')
        db.execute('CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY, device_id TEXT NOT NULL, kind TEXT NOT NULL, message TEXT NOT NULL, opened_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, UNIQUE(device_id, kind))')
        db.execute('CREATE TABLE IF NOT EXISTS alert_events (id INTEGER PRIMARY KEY, device_id TEXT NOT NULL, kind TEXT NOT NULL, transition TEXT NOT NULL, occurred_at TEXT NOT NULL)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_alert_events_time ON alert_events(id DESC)')
        db.execute('CREATE TABLE IF NOT EXISTS owner_sessions (token_hash TEXT PRIMARY KEY, created_at REAL NOT NULL, expires_at REAL NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS subscription_events (id INTEGER PRIMARY KEY, provider TEXT NOT NULL, external_id TEXT NOT NULL UNIQUE, event_type TEXT NOT NULL, created_at TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS notification_outbox (id INTEGER PRIMARY KEY, device_id TEXT NOT NULL, kind TEXT NOT NULL, transition TEXT NOT NULL, created_at TEXT NOT NULL, delivered_at TEXT, attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT)')

def ingest(payload, source='user-supplied'):
    device_id=payload.get('device_id');name=payload.get('name',device_id)
    if not isinstance(device_id,str) or not (1<=len(device_id)<=80) or not all(c.isalnum() or c in '-_.' for c in device_id):raise ValueError('invalid device_id')
    if not isinstance(name,str) or not (1<=len(name)<=100):raise ValueError('invalid name')
    try:
        hashrate=float(payload['hashrate_ths']);watts=float(payload['watts']);temperature=payload.get('temperature_c');temperature=None if temperature is None else float(temperature)
    except (KeyError,ValueError,TypeError):raise ValueError('invalid telemetry values')
    import math
    if any(not math.isfinite(x) for x in [hashrate,watts]+([] if temperature is None else [temperature])):raise ValueError('non-finite telemetry')
    if not 0<=hashrate<=1000000 or not 0<=watts<=10000000 or (temperature is not None and not -50<=temperature<=200):raise ValueError('telemetry outside allowed range')
    with connect() as db:
        db.execute('INSERT INTO samples(device_id,sampled_at,hashrate_ths,watts,temperature_c,source) VALUES(?,?,?,?,?,?)',(device_id,time.time(),hashrate,watts,temperature,source))
        db.execute('INSERT INTO miners VALUES (?,?,?,?,?,?) ON CONFLICT(device_id) DO UPDATE SET name=excluded.name,hashrate_ths=excluded.hashrate_ths,watts=excluded.watts,temperature_c=excluded.temperature_c,last_seen=excluded.last_seen',(device_id,name,hashrate,watts,temperature,time.time()))
    return device_id

def snapshot(stale_after=120, temp_alert=85):
    now=time.time(); miners=[];alerts=[]
    with connect() as db:
        rows=db.execute('SELECT * FROM miners ORDER BY name').fetchall()
        for r in rows:
            status='Offline' if now-r['last_seen']>stale_after else ('Low hashrate' if r['hashrate_ths']<=0 else 'Online')
            if r['temperature_c'] is not None and r['temperature_c']>=temp_alert and status=='Online':status='High temperature'
            miner=dict(r);miner['status']=status;miner['age_seconds']=round(now-r['last_seen'],1);miners.append(miner)
            for kind,active,message in [('offline',status=='Offline','No recent telemetry'),('hashrate',status=='Low hashrate','Hashrate is zero'),('temperature',status=='High temperature','Temperature threshold exceeded')]:
                existing=db.execute('SELECT active FROM alerts WHERE device_id=? AND kind=?',(r['device_id'],kind)).fetchone()
                if active and (not existing or not existing['active']):
                    db.execute('INSERT INTO alerts(device_id,kind,message,opened_at,active) VALUES (?,?,?,?,1) ON CONFLICT(device_id,kind) DO UPDATE SET message=excluded.message,opened_at=excluded.opened_at,active=1',(r['device_id'],kind,message,utc_now()))
                    db.execute('INSERT INTO alert_events(device_id,kind,transition,occurred_at) VALUES (?,?,?,?)',(r['device_id'],kind,'opened',utc_now()))
                    db.execute('INSERT INTO notification_outbox(device_id,kind,transition,created_at) VALUES (?,?,?,?)',(r['device_id'],kind,'opened',utc_now()))
                if not active and existing and existing['active']:
                    db.execute('UPDATE alerts SET active=0 WHERE device_id=? AND kind=?',(r['device_id'],kind))
                    db.execute('INSERT INTO alert_events(device_id,kind,transition,occurred_at) VALUES (?,?,?,?)',(r['device_id'],kind,'resolved',utc_now()))
                    db.execute('INSERT INTO notification_outbox(device_id,kind,transition,created_at) VALUES (?,?,?,?)',(r['device_id'],kind,'resolved',utc_now()))
        alerts=[dict(x) for x in db.execute('SELECT device_id,kind,message,opened_at FROM alerts WHERE active=1 ORDER BY opened_at DESC')]
    return {'generated_at':utc_now(),'miners':miners,'alerts':alerts,'source':'mixed: user-supplied and/or read-only Braiins pool worker data; see source in history'}

def profitability(payload):
    """Scenario economics, never a promise of actual pool payout."""
    def number(key, maximum):
        try: v=Decimal(str(payload[key]))
        except (KeyError, InvalidOperation, ValueError): raise ValueError('invalid '+key)
        if not v.is_finite() or not 0 <= v <= maximum: raise ValueError('out of range '+key)
        return v
    h=number('hashrate_ths',1000000); watts=number('watts',10000000)
    yield_per_th=number('btc_per_th_day',Decimal('0.01'))
    btc_price=number('btc_price_usd',Decimal('10000000'))
    tariff=number('electricity_usd_kwh',Decimal('100'))
    pool_fee=number('pool_fee_percent',Decimal('100'))
    uptime=number('uptime_percent',Decimal('100'))
    overhead=number('other_usd_day',Decimal('1000000'))
    # Uptime is applied to both revenue and device consumption; fixed overhead remains.
    active=uptime/100
    btc_day=h*yield_per_th*active
    revenue=btc_day*btc_price*(1-pool_fee/100)
    electricity=watts/1000*24*tariff*active
    net=revenue-electricity-overhead
    def fmt(x):return format(x.quantize(Decimal('0.00000001')),'f')
    return {'estimated_btc_day':fmt(btc_day),'gross_after_pool_usd_day':fmt(revenue),
            'electricity_usd_day':fmt(electricity),'other_usd_day':fmt(overhead),
            'net_usd_day':fmt(net),'net_usd_month_30d':fmt(net*30),
            'break_even_btc_usd':fmt((electricity+overhead)/(btc_day*(1-pool_fee/100))) if btc_day>0 and pool_fee<100 else None,
            'estimated':True,'assumptions':'Constant yield, price, tariff and uptime; excludes taxes, depreciation and variance'}

def normalize_braiins_workers(data):
    """Normalize documented Braiins worker API (GH/s -> TH/s). No secrets returned."""
    workers=data.get('btc',{}).get('workers',{})
    if not isinstance(workers,dict):raise ValueError('unexpected Braiins workers response')
    out=[]
    for name, worker in list(workers.items())[:1000]:
        if not isinstance(worker,dict):continue
        unit=worker.get('hash_rate_unit','Gh/s').lower().replace(' ','')
        multiplier={'gh/s':0.001,'th/s':1.0,'mh/s':0.000001,'ph/s':1000.0}.get(unit)
        if multiplier is None:continue
        raw=worker.get('hash_rate_5m',0)
        try: rate=float(raw)*multiplier
        except (ValueError,TypeError):continue
        if not 0<=rate<=1000000:continue
        # Worker is a pool identity, not necessarily a single ASIC. No wattage supplied.
        out.append({'device_id':'braiins-'+__import__('hashlib').sha256(name.encode()).hexdigest()[:16],
                    'name':name[:100], 'hashrate_ths':rate,'watts':0,'temperature_c':None,
                    'pool_state':worker.get('state','unknown')})
    return out

def sync_braiins(fetcher=None):
    global _LAST_SYNC
    if not BRAIINS_TOKEN:raise ValueError('Braiins read-only token not configured on server')
    if time.monotonic()-_LAST_SYNC<SYNC_COOLDOWN:raise ValueError('sync rate limited; retry later')
    _LAST_SYNC=time.monotonic()
    if fetcher is None:
        def fetcher():
            req=urllib.request.Request(BRAIINS_URL,headers={'Pool-Auth-Token':BRAIINS_TOKEN,'Accept':'application/json'})
            with urllib.request.urlopen(req,timeout=12) as response:
                if response.status!=200:raise ValueError('pool request failed')
                return json.load(response)
    workers=normalize_braiins_workers(fetcher())
    for worker in workers:ingest(worker,source='braiins-pool-worker')
    return {'synced':len(workers),'note':'Braiins pool worker hashrate only. Power and temperatures are unknown, not zero measurements.'}

def fleet_economics():
    """Only calculate real cost when power readings are available. Zero from pool is UNKNOWN."""
    snap=snapshot()
    with connect() as db:
        settings={r['device_id']:dict(r) for r in db.execute('SELECT * FROM device_settings')}
        sources={r['device_id']:r['source'] for r in db.execute('SELECT s.device_id,s.source FROM samples s JOIN (SELECT device_id,MAX(id) id FROM samples GROUP BY device_id) t ON s.id=t.id')}
    items=[]; known_cost=Decimal(0); known_net=Decimal(0)
    for miner in snap['miners']:
        device=miner['device_id']; setting=settings.get(device)
        pool_only=sources.get(device) in ('braiins-pool-worker','cgminer-summary-power-unknown')
        power_known=not pool_only
        item={'device_id':device,'name':miner['name'],'status':miner['status'],'power_known':power_known,'configured':bool(setting),'net_usd_day':None,'electricity_usd_day':None,'warning':None}
        if not setting:
            item['warning']='Set miner economics before using profit estimates'
        elif not power_known:
            item['warning']='Pool worker hashrate does not include measured power; no net profit estimate'
        elif not setting['btc_per_th_day'] or not setting['btc_price_usd']:
            item['warning']='BTC yield and market price assumptions required'
        else:
            result=profitability({'hashrate_ths':miner['hashrate_ths'],'watts':miner['watts'],'btc_per_th_day':setting['btc_per_th_day'],'btc_price_usd':setting['btc_price_usd'],'electricity_usd_kwh':setting['electricity_usd_kwh'],'pool_fee_percent':setting['pool_fee_percent'],'uptime_percent':100 if miner['status']!='Offline' else 0,'other_usd_day':setting['other_usd_day']})
            item['net_usd_day']=result['net_usd_day'];item['electricity_usd_day']=result['electricity_usd_day'];known_net+=Decimal(result['net_usd_day']);known_cost+=Decimal(result['electricity_usd_day'])
        items.append(item)
    return {'estimated':True,'miners':items,'known_estimated_net_usd_day':str(known_net),'known_estimated_electricity_usd_day':str(known_cost),'coverage':{'modeled':sum(x['net_usd_day'] is not None for x in items),'total':len(items)},'warning':'Totals cover only miners with configured assumptions and known power; not verified earnings.'}

def configure_device(obj):
    device=obj.get('device_id')
    if not isinstance(device,str) or not device or len(device)>80 or not all(c.isalnum() or c in '-_.' for c in device):raise ValueError('invalid device_id')
    with connect() as db:
        if not db.execute('SELECT 1 FROM miners WHERE device_id=?',(device,)).fetchone():raise ValueError('unknown miner')
    fields=['electricity_usd_kwh','btc_per_th_day','btc_price_usd','pool_fee_percent','other_usd_day']
    limits=[100,0.01,10000000,100,1000000]
    values=[]
    for key,maximum in zip(fields,limits):
        try:v=Decimal(str(obj[key]))
        except (KeyError,InvalidOperation,ValueError):raise ValueError('invalid '+key)
        if not v.is_finite() or v<0 or v>Decimal(str(maximum)):raise ValueError('out of range '+key)
        values.append(float(v))
    with connect() as db:
        db.execute('INSERT INTO device_settings VALUES (?,?,?,?,?,?) ON CONFLICT(device_id) DO UPDATE SET electricity_usd_kwh=excluded.electricity_usd_kwh,btc_per_th_day=excluded.btc_per_th_day,btc_price_usd=excluded.btc_price_usd,pool_fee_percent=excluded.pool_fee_percent,other_usd_day=excluded.other_usd_day',(device,*values))
    return {'configured':device,'estimated':True}

def acknowledge_alert(obj):
    device=obj.get('device_id');kind=obj.get('kind')
    if not isinstance(device,str) or not isinstance(kind,str) or kind not in ('offline','hashrate','temperature'):raise ValueError('invalid alert')
    with connect() as db:
        changed=db.execute('UPDATE alerts SET active=0 WHERE device_id=? AND kind=? AND active=1',(device,kind)).rowcount
        if changed:db.execute('INSERT INTO alert_events(device_id,kind,transition,occurred_at) VALUES (?,?,?,?)',(device,kind,'acknowledged',utc_now()))
    return {'acknowledged':bool(changed),'note':'If the condition persists, the next snapshot will reopen the alert.'}

# Compatible CGMiner/BMMiner read-only summary API. Never issues device-control commands.
def parse_cgminer_summary(raw):
    if isinstance(raw,bytes): raw=raw.decode('utf-8','replace')
    raw=raw.strip('\x00 \r\n\t')
    try:
        obj=json.loads(raw)
        summaries=obj.get('SUMMARY',[])
        if not isinstance(summaries,list) or not summaries:raise ValueError('no SUMMARY data')
        summary=summaries[0]
    except (json.JSONDecodeError,AttributeError):
        # Older cgminer returns SUMMARY,field=value,field=value|STATUS,...
        section=next((x for x in raw.split('|') if x.startswith('SUMMARY,')),None)
        if not section:raise ValueError('unrecognized summary response')
        summary={}
        for part in section.split(',')[1:]:
            if '=' in part:
                key,val=part.split('=',1);summary[key]=val
    if not isinstance(summary,dict):raise ValueError('invalid summary')
    # Prefer explicit 5s rates. Common firmware units: GH/s, MH/s, TH/s.
    for key,multiplier in [('GHS 5s',.001),('GHS av',.001),('MHS 5s',.000001),('MHS av',.000001),('THS 5s',1),('THS av',1)]:
        if key in summary:
            try: rate=float(summary[key])*multiplier
            except (TypeError,ValueError):raise ValueError('invalid hashrate')
            if not __import__('math').isfinite(rate) or not 0<=rate<=1000000:raise ValueError('invalid hashrate')
            return rate
    raise ValueError('no supported hashrate field')

def validated_lan_ip(host):
    try: ip=ipaddress.ip_address(host)
    except ValueError:raise ValueError('use a literal private LAN IPv4 address, not hostname')
    if ip.version!=4 or not ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        raise ValueError('miner must be on a private LAN address')
    return str(ip)

def poll_asic(device_id, host, port=4028):
    host=validated_lan_ip(host)
    if not isinstance(port,int) or not 1<=port<=65535:raise ValueError('invalid port')
    if not isinstance(device_id,str) or not 1<=len(device_id)<=80 or not all(c.isalnum() or c in '-_.' for c in device_id):raise ValueError('invalid device_id')
    with socket.create_connection((host,port),timeout=3) as sock:
        sock.settimeout(3)
        sock.sendall(b'{"command":"summary"}')
        chunks=[];size=0
        while size<65536:
            try:chunk=sock.recv(min(4096,65536-size))
            except socket.timeout:break
            if not chunk:break
            chunks.append(chunk);size+=len(chunk)
            if b'\x00' in chunk:break
    if not chunks:raise ValueError('miner returned no data')
    rate=parse_cgminer_summary(b''.join(chunks))
    # Summary endpoint cannot reliably supply watts or chip temperatures.
    ingest({'device_id':device_id,'name':device_id,'hashrate_ths':rate,'watts':0,'temperature_c':None},source='cgminer-summary-power-unknown')
    return {'device_id':device_id,'hashrate_ths':rate,'power_known':False,'temperature_known':False,'source':'cgminer-summary'}

def configured_miners():
    raw=os.environ.get('HASHMARGIN_ASICS','').strip()
    if not raw:return []
    try: items=json.loads(raw)
    except json.JSONDecodeError:raise ValueError('HASHMARGIN_ASICS must be a JSON array')
    if not isinstance(items,list) or len(items)>50:raise ValueError('expected at most 50 ASIC entries')
    output=[]
    for item in items:
        if not isinstance(item,dict):raise ValueError('invalid ASIC entry')
        host=validated_lan_ip(item.get('host'))
        device_id=item.get('device_id')
        if not isinstance(device_id,str) or not 1<=len(device_id)<=80 or not all(c.isalnum() or c in '-_.' for c in device_id):raise ValueError('invalid device_id')
        port=item.get('port',4028)
        if not isinstance(port,int) or not 1<=port<=65535:raise ValueError('invalid port')
        output.append((device_id,host,port))
    if len({i[0] for i in output})!=len(output):raise ValueError('duplicate ASIC id')
    return output

def poll_loop(items,stop_event):
    while not stop_event.is_set():
        for device_id,host,port in items:
            try:poll_asic(device_id,host,port)
            except (OSError,ValueError) as exc:
                # Failed polls do not overwrite last valid telemetry; staleness opens offline alerts.
                print(f'ASIC poll failed for {device_id}: {type(exc).__name__}')
        snapshot()
        stop_event.wait(60)

def send_alert_email(message, smtp_factory=smtplib.SMTP_SSL):
    """Send an alert through an explicitly configured TLS SMTP relay."""
    host=os.environ.get('HASHMARGIN_SMTP_HOST','')
    user=os.environ.get('HASHMARGIN_SMTP_USER','')
    password=os.environ.get('HASHMARGIN_SMTP_PASSWORD','')
    recipient=os.environ.get('HASHMARGIN_ALERT_TO','')
    sender=os.environ.get('HASHMARGIN_ALERT_FROM','')
    if not all((host,user,password,recipient,sender)):
        raise ValueError('SMTP alerts not configured')
    port=int(os.environ.get('HASHMARGIN_SMTP_PORT','465'))
    if port < 1 or port > 65535: raise ValueError('invalid SMTP port')
    mail=EmailMessage()
    mail['From']=sender;mail['To']=recipient
    mail['Subject']='HashMargin miner alert: '+message['transition']
    mail.set_content(f"Miner: {message['device_id']}\nCondition: {message['kind']}\nTransition: {message['transition']}\nTime: {message['created_at']}\n")
    with smtp_factory(host,port,timeout=10,context=ssl.create_default_context()) as client:
        client.login(user,password)
        client.send_message(mail)

def dispatch_notifications(sender=send_alert_email, limit=20):
    """Outbox prevents duplicate sends after successful delivery; retries failures."""
    if not os.environ.get('HASHMARGIN_ALERT_TO'): return {'sent':0,'failed':0,'disabled':True}
    sent=failed=0
    with connect() as db:
        rows=[dict(x) for x in db.execute('SELECT * FROM notification_outbox WHERE delivered_at IS NULL AND attempts < 10 ORDER BY id LIMIT ?', (limit,))]
    for item in rows:
        try:
            sender(item)
        except Exception as exc:
            failed+=1
            with connect() as db:
                db.execute('UPDATE notification_outbox SET attempts=attempts+1,last_error=? WHERE id=?',(type(exc).__name__,item['id']))
        else:
            sent+=1
            with connect() as db:
                db.execute('UPDATE notification_outbox SET delivered_at=?,attempts=attempts+1,last_error=NULL WHERE id=?',(utc_now(),item['id']))
    return {'sent':sent,'failed':failed,'disabled':False}

def notification_loop(stop_event):
    while not stop_event.is_set():
        snapshot()
        dispatch_notifications()
        stop_event.wait(60)

# Single-owner login is for local pilot only. Not customer tenancy or billing.
OWNER_PASSWORD_HASH = os.environ.get('HASHMARGIN_OWNER_PASSWORD_HASH', '')
SESSION_TTL = 8 * 3600

def password_digest(password, salt):
    return hashlib.scrypt(password.encode('utf-8'), salt=salt, n=2**14, r=8, p=1, dklen=32)

def make_password_hash(password):
    if not isinstance(password,str) or len(password)<14 or len(password)>1024:
        raise ValueError('owner password must be 14-1024 characters')
    salt=secrets.token_bytes(16)
    return 'scrypt$'+salt.hex()+'$'+password_digest(password,salt).hex()

def verify_password(password, stored):
    try:
        algorithm,salt_hex,digest_hex=stored.split('$')
        if algorithm!='scrypt' or len(salt_hex)!=32 or len(digest_hex)!=64:return False
        return hmac.compare_digest(password_digest(password,bytes.fromhex(salt_hex)),bytes.fromhex(digest_hex))
    except (ValueError,TypeError,OverflowError):return False

def create_owner_session():
    token=secrets.token_urlsafe(32)
    with connect() as db:
        db.execute('DELETE FROM owner_sessions WHERE expires_at<?',(time.time(),))
        db.execute('INSERT INTO owner_sessions VALUES (?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),time.time(),time.time()+SESSION_TTL))
    return {'access_token':token,'token_type':'Bearer','expires_in':SESSION_TTL,'scope':'single-owner-local-pilot'}

def session_authorized(token):
    if not isinstance(token,str) or len(token)>256:return False
    digest=hashlib.sha256(token.encode()).hexdigest()
    with connect() as db:
        row=db.execute('SELECT expires_at FROM owner_sessions WHERE token_hash=?',(digest,)).fetchone()
    return bool(row and row['expires_at']>time.time())

class Handler(BaseHTTPRequestHandler):
    def respond(self,status,obj):
        data=json.dumps(obj,allow_nan=False).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def authorized(self):
        value=self.headers.get('Authorization','');return (bool(TOKEN) and hmac.compare_digest(value,'Bearer '+TOKEN)) or (value.startswith('Bearer ') and session_authorized(value[7:]))
    def tenant_identity(self):
        auth=self.headers.get('Authorization','')
        return tenant_store.identity(TENANT_DB,auth[7:]) if auth.startswith('Bearer ') else None
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/api/v2/tenant/devices':
            who=self.tenant_identity()
            return self.respond(200,{'devices':tenant_store.list_devices(TENANT_DB,who['tenant_id'])}) if who else self.respond(401,{'error':'unauthorized'})
        if path=='/api/v1/account/status':return self.respond(200,{'mode':'single-owner','password_login_enabled':bool(OWNER_PASSWORD_HASH),'subscriptions':'not configured','public_signup':False})
        if path=='/healthz':return self.respond(200,{'status':'ok','service':'hashmargin-local-bridge'})
        if path in ('/','/index.html','/manifest.webmanifest','/sw.js'):
            filename='index.html' if path=='/' else path[1:]
            data=(Path(__file__).resolve().parent/filename).read_bytes()
            self.send_response(200)
            self.send_header('Content-Type',{'index.html':'text/html; charset=utf-8','manifest.webmanifest':'application/manifest+json','sw.js':'text/javascript'}[filename])
            self.send_header('Content-Length',str(len(data)))
            self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers();self.wfile.write(data);return
        if path not in ('/api/v1/snapshot','/api/v1/history','/api/v1/fleet/economics','/api/v1/alerts/events','/api/v1/notifications/status'):return self.respond(404,{'error':'not found'})
        if not self.authorized():return self.respond(401,{'error':'unauthorized'})
        if path=='/api/v1/notifications/status':
            with connect() as db:
                pending=db.execute('SELECT COUNT(*) FROM notification_outbox WHERE delivered_at IS NULL').fetchone()[0]
                delivered=db.execute('SELECT COUNT(*) FROM notification_outbox WHERE delivered_at IS NOT NULL').fetchone()[0]
            return self.respond(200,{'configured':bool(os.environ.get('HASHMARGIN_ALERT_TO')),'pending':pending,'delivered':delivered})
        if path=='/api/v1/fleet/economics':return self.respond(200,fleet_economics())
        if path=='/api/v1/alerts/events':
            with connect() as db: events=[dict(x) for x in db.execute('SELECT device_id,kind,transition,occurred_at FROM alert_events ORDER BY id DESC LIMIT 100')]
            return self.respond(200,{'events':events})
        if path=='/api/v1/history':
            with connect() as db:
                rows=[dict(x) for x in db.execute('SELECT device_id,sampled_at,hashrate_ths,watts,temperature_c,source FROM samples ORDER BY sampled_at DESC LIMIT 250')]
            return self.respond(200,{'samples':rows})
        self.respond(200,snapshot())
    def do_POST(self):
        path=urlparse(self.path).path
        if path=='/api/v2/tenant/login':
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 1<=length<=2048:return self.respond(413,{'error':'invalid request size'})
                obj=json.loads(self.rfile.read(length))
                email=obj.get('email','');password=obj.get('password','')
                if not isinstance(email,str) or not isinstance(password,str) or len(email)>254 or len(password)>1024:return self.respond(400,{'error':'invalid request'})
                token=tenant_store.login(TENANT_DB,email,password)
                return self.respond(200,{'token':token,'expires_in':3600}) if token else self.respond(401,{'error':'invalid credentials'})
            except (ValueError,UnicodeDecodeError,AttributeError):return self.respond(400,{'error':'invalid request'})
        if path=='/api/v2/tenant/devices':
            who=self.tenant_identity()
            if not who:return self.respond(401,{'error':'unauthorized'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 1<=length<=MAX_BODY:return self.respond(413,{'error':'invalid request size'})
                obj=json.loads(self.rfile.read(length))
                if not isinstance(obj,dict):raise ValueError('expected JSON object')
                return self.respond(200,tenant_store.upsert_device(TENANT_DB,who['tenant_id'],obj))
            except (ValueError,UnicodeDecodeError):return self.respond(400,{'error':'invalid request'})
        if path=='/api/v1/account/login':
            if not OWNER_PASSWORD_HASH:return self.respond(503,{'error':'owner password login not configured'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 1<=length<=2048:return self.respond(413,{'error':'invalid request size'})
                obj=json.loads(self.rfile.read(length))
                password=obj.get('password') if isinstance(obj,dict) else None
                if not isinstance(password,str) or len(password)>1024:return self.respond(401,{'error':'invalid credentials'})
                if not verify_password(password,OWNER_PASSWORD_HASH):
                    time.sleep(0.2)
                    return self.respond(401,{'error':'invalid credentials'})
                return self.respond(200,create_owner_session())
            except (ValueError,UnicodeDecodeError):return self.respond(400,{'error':'invalid request'})
        if path not in ('/api/v1/telemetry','/api/v1/economics','/api/v1/braiins/sync','/api/v1/devices/configure','/api/v1/alerts/acknowledge'):return self.respond(404,{'error':'not found'})
        if not self.authorized():return self.respond(401,{'error':'unauthorized'})
        if path=='/api/v1/braiins/sync':
            try:return self.respond(200,sync_braiins())
            except (ValueError,urllib.error.URLError,TimeoutError) as e:return self.respond(400,{'error':str(e)})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<1 or length>MAX_BODY:return self.respond(413,{'error':'invalid request size'})
            obj=json.loads(self.rfile.read(length))
            if not isinstance(obj,dict):raise ValueError('expected JSON object')
            if path=='/api/v1/economics':return self.respond(200,profitability(obj))
            if path=='/api/v1/devices/configure':return self.respond(200,configure_device(obj))
            if path=='/api/v1/alerts/acknowledge':return self.respond(200,acknowledge_alert(obj))
            device_id=ingest(obj)
        except (ValueError,UnicodeDecodeError,json.JSONDecodeError) as e:return self.respond(400,{'error':str(e)})
        self.respond(202,{'accepted':device_id})
    def do_OPTIONS(self):self.respond(405,{'error':'unsupported'})
    def log_message(self,format,*args):pass # avoid logging auth-related request data

if __name__=='__main__':
    if not TOKEN or len(TOKEN)<24:raise SystemExit('Set HASHMARGIN_TOKEN to a random secret of at least 24 characters')
    if HOST not in ('127.0.0.1', 'localhost', '::1', '0.0.0.0'):
    raise SystemExit('Invalid server host')
    init_db()
    tenant_store.initialize(TENANT_DB)
    threading.Thread(target=notification_loop,args=(threading.Event(),),daemon=True).start()
    asics=configured_miners()
    if asics:
        threading.Thread(target=poll_loop,args=(asics,threading.Event()),daemon=True).start()
        print(f'Read-only ASIC polling enabled for {len(asics)} LAN devices')
    print(f'HashMargin bridge listening on http://{HOST}:{PORT} (loopback only)')
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
