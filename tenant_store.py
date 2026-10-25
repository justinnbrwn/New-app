"""Isolated tenant API prototype. Never shares legacy owner fleet tables."""
import hashlib, hmac, secrets, sqlite3, time, re
from pathlib import Path

def dbconn(path):
    db=sqlite3.connect(path); db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON');return db

def initialize(path):
    with dbconn(path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS tenants (id INTEGER PRIMARY KEY, name TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS tenant_users (id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id), email TEXT NOT NULL UNIQUE, salt TEXT NOT NULL, password_hash TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS tenant_sessions (token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES tenant_users(id), expires REAL NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS tenant_devices (tenant_id INTEGER NOT NULL REFERENCES tenants(id), device_id TEXT NOT NULL, name TEXT NOT NULL, hashrate_ths REAL NOT NULL DEFAULT 0, PRIMARY KEY (tenant_id,device_id))')

def password_hash(password,salt):return hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
def provision(path,tenant_name,email,password):
    if len(password)<12:raise ValueError('password must have at least 12 characters')
    if not 3<=len(tenant_name)<=80 or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email):raise ValueError('invalid tenant or email')
    salt=secrets.token_hex(16)
    with dbconn(path) as db:
        tid=db.execute('INSERT INTO tenants(name) VALUES (?)',(tenant_name,)).lastrowid
        db.execute('INSERT INTO tenant_users(tenant_id,email,salt,password_hash) VALUES (?,?,?,?)',(tid,email.lower(),salt,password_hash(password,salt)))
    return tid

def login(path,email,password):
    with dbconn(path) as db:
        row=db.execute('SELECT * FROM tenant_users WHERE email=?',(email.lower(),)).fetchone()
        if row is None or not hmac.compare_digest(password_hash(password,row['salt']),row['password_hash']):return None
        token=secrets.token_urlsafe(32)
        db.execute('INSERT INTO tenant_sessions VALUES (?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),row['id'],time.time()+3600))
        return token

def identity(path,token):
    if not token:return None
    with dbconn(path) as db:
        row=db.execute('SELECT u.tenant_id,u.id AS user_id,u.email FROM tenant_sessions s JOIN tenant_users u ON s.user_id=u.id WHERE s.token_hash=? AND s.expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
        return dict(row) if row else None

def list_devices(path,tenant_id):
    with dbconn(path) as db:return [dict(r) for r in db.execute('SELECT device_id,name,hashrate_ths FROM tenant_devices WHERE tenant_id=? ORDER BY device_id',(tenant_id,))]

def upsert_device(path,tenant_id,obj):
    device_id=obj.get('device_id');name=obj.get('name');hashrate=obj.get('hashrate_ths')
    if not isinstance(device_id,str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,80}',device_id):raise ValueError('invalid device_id')
    if not isinstance(name,str) or not 1<=len(name)<=100:raise ValueError('invalid name')
    import math
    if type(hashrate) not in (int,float) or not math.isfinite(hashrate) or hashrate<0 or hashrate>1e7:raise ValueError('invalid hashrate_ths')
    with dbconn(path) as db:
        db.execute('INSERT INTO tenant_devices(tenant_id,device_id,name,hashrate_ths) VALUES (?,?,?,?) ON CONFLICT(tenant_id,device_id) DO UPDATE SET name=excluded.name,hashrate_ths=excluded.hashrate_ths',(tenant_id,device_id,name,hashrate))
    return {'device_id':device_id}
