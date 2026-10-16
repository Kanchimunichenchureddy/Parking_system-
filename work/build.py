from pathlib import Path
root=Path('outputs/parkreceipt')
def put(p,s):
 (root/p).parent.mkdir(parents=True,exist_ok=True); (root/p).write_text(s.lstrip('\n'))
put('backend/requirements.txt','''fastapi==0.135.1
uvicorn==0.42.0
SQLAlchemy==2.0.48
alembic==1.18.4
PyMySQL==1.1.2
cryptography>=46,<49
pwdlib[argon2]==0.3.0
pytest>=8,<10
httpx>=0.28,<1
''')
put('backend/app/__init__.py','')
put('backend/app/models.py','''import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

def now(): return datetime.now(timezone.utc).replace(tzinfo=None)
engine = create_engine(os.getenv("DATABASE_URL", "mysql+pymysql://parkreceipt:parkreceipt@localhost:3306/parkreceipt"), pool_pre_ping=True)
Session = sessionmaker(engine, expire_on_commit=False)
class Base(DeclarativeBase): pass
class Location(Base):
    __tablename__="locations"
    id: Mapped[int]=mapped_column(primary_key=True)
    slug: Mapped[str]=mapped_column(String(60),unique=True)
    name: Mapped[str]=mapped_column(String(100))
    rate: Mapped[int]=mapped_column(Integer,default=3000)
class User(Base):
    __tablename__="users"
    id: Mapped[int]=mapped_column(primary_key=True)
    username: Mapped[str]=mapped_column(String(80),unique=True)
    password_hash: Mapped[str]=mapped_column(String(255))
    role: Mapped[str]=mapped_column(String(10))
    location_id: Mapped[int|None]=mapped_column(ForeignKey("locations.id"),nullable=True)
class PaymentRequest(Base):
    __tablename__="payment_requests"
    id: Mapped[int]=mapped_column(primary_key=True)
    token: Mapped[str]=mapped_column(String(64),unique=True)
    idempotency_key: Mapped[str]=mapped_column(String(100),unique=True)
    reference: Mapped[str]=mapped_column(String(16),unique=True)
    location_id: Mapped[int]=mapped_column(ForeignKey("locations.id"))
    vehicle: Mapped[str]=mapped_column(String(32))
    phone: Mapped[str|None]=mapped_column(String(20),nullable=True)
    amount: Mapped[int]=mapped_column(Integer)
    method: Mapped[str]=mapped_column(String(10))
    state: Mapped[str]=mapped_column(String(12),default="pending")
    created_at: Mapped[datetime]=mapped_column(DateTime,default=now)
    confirmed_at: Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    confirmed_by: Mapped[int|None]=mapped_column(ForeignKey("users.id"),nullable=True)
class PaymentAttempt(Base):
    __tablename__="payment_attempts"
    id: Mapped[int]=mapped_column(primary_key=True)
    request_id: Mapped[int]=mapped_column(ForeignKey("payment_requests.id"))
    outcome: Mapped[str]=mapped_column(String(12))
    created_at: Mapped[datetime]=mapped_column(DateTime,default=now)
class Receipt(Base):
    __tablename__="receipts"
    id: Mapped[int]=mapped_column(primary_key=True)
    request_id: Mapped[int]=mapped_column(ForeignKey("payment_requests.id"),unique=True)
    number: Mapped[str]=mapped_column(String(40),unique=True)
class AuditEvent(Base):
    __tablename__="audit_events"
    id: Mapped[int]=mapped_column(primary_key=True)
    actor_id: Mapped[int|None]=mapped_column(ForeignKey("users.id"),nullable=True)
    request_id: Mapped[int|None]=mapped_column(ForeignKey("payment_requests.id"),nullable=True)
    action: Mapped[str]=mapped_column(String(60))
    detail: Mapped[str]=mapped_column(Text,default="")
    created_at: Mapped[datetime]=mapped_column(DateTime,default=now)
class LoginSession(Base):
    __tablename__="login_sessions"
    digest: Mapped[str]=mapped_column(String(64),primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime]=mapped_column(DateTime)
''')
put('backend/app/main.py','''import csv, hashlib, io, os, re, secrets, time
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from pwdlib import PasswordHash
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from .models import *

app=FastAPI(title="ParkReceipt Research MVP")
hasher=PasswordHash.recommended()
IST=ZoneInfo("Asia/Kolkata")
DEMO=os.getenv("PAYMENT_MODE","demo")=="demo"
ORIGIN=os.getenv("APP_ORIGIN","http://localhost:5173")
limits=defaultdict(deque)

def db():
    with Session() as s: yield s

def limit(req, bucket, maximum):
    # Per-process pilot limiter. Run one worker; use a shared limiter before public deployment.
    key=(req.client.host if req.client else "unknown",bucket)
    q=limits[key]; t=time.monotonic()
    while q and q[0]<t-60: q.popleft()
    if len(q)>=maximum: raise HTTPException(429,"Too many attempts. Wait one minute and retry.")
    q.append(t)

@app.middleware("http")
async def security(req:Request, call_next):
    if req.method not in ("GET","HEAD","OPTIONS") and req.headers.get("origin") not in (None,ORIGIN):
        return Response("Untrusted origin",403)
    response=await call_next(req)
    response.headers["Cache-Control"]="no-store"
    response.headers["Referrer-Policy"]="no-referrer"
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["X-Frame-Options"]="DENY"
    return response

def current(req:Request,s=Depends(db)):
    token=req.cookies.get("session","")
    auth=s.get(LoginSession,hashlib.sha256(token.encode()).hexdigest())
    if not auth or auth.expires_at<now(): raise HTTPException(401,"Please sign in.")
    return s.get(User,auth.user_id)
def owner(u=Depends(current)):
    if u.role!="owner": raise HTTPException(403,"Owner access required.")
    return u

def audit(s,action,r=None,u=None,detail=""):
    s.add(AuditEvent(action=action,request_id=r.id if r else None,actor_id=u.id if u else None,detail=detail))
def scoped(u,r):
    if u.role!="owner" and u.location_id!=r.location_id: raise HTTPException(403,"This request belongs to another location.")
def get_request(s,token):
    r=s.scalar(select(PaymentRequest).where(PaymentRequest.token==token))
    if not r: raise HTTPException(404,"Request not found.")
    return r
def iso(t): return t.replace(tzinfo=timezone.utc).isoformat() if t else None
def payload(s,r):
    receipt=s.scalar(select(Receipt).where(Receipt.request_id==r.id))
    loc=s.get(Location,r.location_id)
    return dict(token=r.token,reference=r.reference,vehicle=r.vehicle,location=loc.name,location_id=r.location_id,
        amount=r.amount,method=r.method,state=r.state,created_at=iso(r.created_at),confirmed_at=iso(r.confirmed_at),
        receipt_number=receipt.number if receipt else None,demo=r.method=="demo")
def loc_payload(l): return dict(id=l.id,slug=l.slug,name=l.name,rate=l.rate)

class LoginIn(BaseModel):
    username:str=Field(min_length=1,max_length=80)
    password:str=Field(min_length=1,max_length=200)
class NewRequest(BaseModel):
    location_slug:str=Field(max_length=60)
    vehicle:str=Field(min_length=2,max_length=40)
    phone:str|None=Field(default=None,max_length=20)
    method:Literal["cash","demo"]
    idempotency_key:str=Field(min_length=20,max_length=100)
class Simulation(BaseModel):
    outcome:Literal["confirmed","failed","pending","cancelled"]
class RateIn(BaseModel):
    rate:int=Field(ge=100,le=10000000)
class Assignment(BaseModel):
    location_id:int

@app.get("/api/locations")
def locations(s=Depends(db)): return [loc_payload(l) for l in s.scalars(select(Location))]
@app.get("/api/locations/{slug}")
def location(slug:str,s=Depends(db)):
    l=s.scalar(select(Location).where(Location.slug==slug))
    if not l: raise HTTPException(404,"Location not found.")
    return {**loc_payload(l),"demo_enabled":DEMO}
@app.post("/api/login")
def login(data:LoginIn,req:Request,res:Response,s=Depends(db)):
    limit(req,"login",10)
    u=s.scalar(select(User).where(User.username==data.username))
    if not u or not hasher.verify(data.password,u.password_hash): raise HTTPException(401,"Incorrect username or password.")
    token=secrets.token_urlsafe(32)
    s.add(LoginSession(digest=hashlib.sha256(token.encode()).hexdigest(),user_id=u.id,expires_at=now()+timedelta(hours=8))); s.commit()
    res.set_cookie("session",token,httponly=True,secure=os.getenv("COOKIE_SECURE","false")=="true",samesite="strict",max_age=28800)
    return dict(role=u.role,username=u.username,location_id=u.location_id)
@app.post("/api/logout")
def logout(req:Request,res:Response,s=Depends(db)):
    auth=s.get(LoginSession,hashlib.sha256(req.cookies.get("session","").encode()).hexdigest())
    if auth: s.delete(auth); s.commit()
    res.delete_cookie("session"); return {"ok":True}
@app.get("/api/me")
def me(u=Depends(current)): return dict(role=u.role,username=u.username,location_id=u.location_id)

@app.post("/api/requests")
def create(data:NewRequest,req:Request,s=Depends(db)):
    limit(req,"create",30)
    vehicle=re.sub(r"\\s+","",data.vehicle.upper())
    if not re.fullmatch(r"[A-Z0-9-]{2,32}",vehicle): raise HTTPException(422,"Use 2–32 letters, numbers or hyphens for the vehicle registration.")
    if data.phone and not re.fullmatch(r"[+0-9 ()-]{7,20}",data.phone): raise HTTPException(422,"Check the optional phone number.")
    loc=s.scalar(select(Location).where(Location.slug==data.location_slug))
    if not loc: raise HTTPException(404,"Location not found.")
    if data.method=="demo" and not DEMO: raise HTTPException(404,"Online simulation is disabled.")
    old=s.scalar(select(PaymentRequest).where(PaymentRequest.idempotency_key==data.idempotency_key))
    def replay(old):
        if (old.location_id,old.vehicle,old.method,old.phone)!=(loc.id,vehicle,data.method,data.phone or None): raise HTTPException(409,"This retry key was already used for a different request.")
        return payload(s,old)
    if old: return replay(old)
    r=PaymentRequest(token=secrets.token_urlsafe(32),reference=secrets.token_hex(5).upper(),idempotency_key=data.idempotency_key,
        location_id=loc.id,vehicle=vehicle,phone=data.phone or None,amount=loc.rate,method=data.method)
    s.add(r)
    try:
        s.flush(); audit(s,"request_created",r); s.commit()
    except IntegrityError:
        s.rollback(); old=s.scalar(select(PaymentRequest).where(PaymentRequest.idempotency_key==data.idempotency_key))
        if old: return replay(old)
        raise HTTPException(409,"Reference collision. Please retry.")
    return payload(s,r)
@app.get("/api/requests/{token}")
def status(token:str,s=Depends(db)): return payload(s,get_request(s,token))

def transition(s,r,state,u=None):
    # Conditional write is the concurrency arbiter on MySQL and SQLite.
    changed=s.execute(update(PaymentRequest).where(PaymentRequest.id==r.id,PaymentRequest.state=="pending").values(
        state=state,confirmed_at=now() if state=="confirmed" else None,confirmed_by=u.id if u and state=="confirmed" else None)).rowcount
    if changed:
        s.add(PaymentAttempt(request_id=r.id,outcome=state))
        if state=="confirmed": s.add(Receipt(request_id=r.id,number="PR-"+secrets.token_hex(10).upper()))
        audit(s,"payment_"+state,r,u)
    s.commit(); s.refresh(r)
    if r.state!=state and r.state!="confirmed": raise HTTPException(409,f"Request is already {r.state}.")
    return payload(s,r)
@app.post("/api/requests/{token}/cancel")
def cancel(token:str,s=Depends(db)):
    r=get_request(s,token)
    if r.state=="confirmed": raise HTTPException(409,"Confirmed payments cannot be cancelled.")
    return transition(s,r,"cancelled")
@app.post("/api/requests/{token}/simulate")
def simulate(token:str,data:Simulation,s=Depends(db)):
    if not DEMO: raise HTTPException(404,"Simulation is disabled.")
    r=get_request(s,token)
    if r.method!="demo": raise HTTPException(400,"Cash requests cannot use online simulation.")
    if data.outcome=="pending":
        if r.state!="pending": raise HTTPException(409,"Request is already terminal.")
        s.add(PaymentAttempt(request_id=r.id,outcome="pending")); s.commit(); return payload(s,r)
    return transition(s,r,data.outcome)
@app.get("/api/receipts/{token}")
def receipt(token:str,s=Depends(db)):
    r=get_request(s,token)
    if r.state!="confirmed": raise HTTPException(409,"Payment has not been confirmed.")
    return payload(s,r)
@app.get("/api/staff/requests")
def staff_requests(s=Depends(db),u=Depends(current)):
    q=select(PaymentRequest).where(PaymentRequest.method=="cash")
    if u.role!="owner": q=q.where(PaymentRequest.location_id==u.location_id)
    return [payload(s,r) for r in s.scalars(q.order_by(PaymentRequest.created_at.desc()).limit(200))]
@app.post("/api/staff/requests/{token}/approve")
def approve(token:str,s=Depends(db),u=Depends(current)):
    r=get_request(s,token); scoped(u,r)
    if r.method!="cash": raise HTTPException(400,"Only cash can be approved by staff.")
    return transition(s,r,"confirmed",u)
@app.patch("/api/owner/locations/{id}")
def rate(id:int,data:RateIn,s=Depends(db),u=Depends(owner)):
    loc=s.get(Location,id)
    if not loc: raise HTTPException(404,"Location not found.")
    old=loc.rate; loc.rate=data.rate; audit(s,"rate_changed",u=u,detail=f"Location {id}: {old} -> {data.rate} paise"); s.commit()
    return loc_payload(loc)
@app.get("/api/owner/users")
def users(s=Depends(db),u=Depends(owner)):
    return [dict(id=x.id,username=x.username,location_id=x.location_id) for x in s.scalars(select(User).where(User.role=="staff"))]
@app.patch("/api/owner/users/{id}")
def assign(id:int,data:Assignment,s=Depends(db),u=Depends(owner)):
    x=s.get(User,id)
    if not x or x.role!="staff" or not s.get(Location,data.location_id): raise HTTPException(422,"Invalid staff or location.")
    audit(s,"staff_assigned",u=u,detail=f"User {id}: {x.location_id} -> {data.location_id}"); x.location_id=data.location_id; s.commit(); return {"ok":True}

def filtered(s,start,end,location_id,method,search):
    if end<start: raise HTTPException(422,"End date must follow start date.")
    a=datetime.combine(start,datetime.min.time(),IST).astimezone(timezone.utc).replace(tzinfo=None)
    b=datetime.combine(end+timedelta(days=1),datetime.min.time(),IST).astimezone(timezone.utc).replace(tzinfo=None)
    q=select(PaymentRequest).outerjoin(Receipt).where(func.coalesce(PaymentRequest.confirmed_at,PaymentRequest.created_at)>=a,func.coalesce(PaymentRequest.confirmed_at,PaymentRequest.created_at)<b)
    if location_id: q=q.where(PaymentRequest.location_id==location_id)
    if method: q=q.where(PaymentRequest.method==method)
    if search:
        needle="%"+search.replace("!","!!").replace("%","!%").replace("_","!_")+"%"
        q=q.where(PaymentRequest.vehicle.ilike(needle,escape="!")|Receipt.number.ilike(needle,escape="!"))
    return list(s.scalars(q.order_by(PaymentRequest.created_at.desc())))
@app.get("/api/owner/report")
def report(start:date,end:date,location_id:int|None=None,method:Literal["cash","demo"]|None=None,search:str="",page:int=1,s=Depends(db),u=Depends(owner)):
    if page<1: raise HTTPException(422,"Invalid page.")
    rows=filtered(s,start,end,location_id,method,search)
    confirmed=[r for r in rows if r.state=="confirmed"]
    groups={}
    for r in confirmed:
        day=r.confirmed_at.replace(tzinfo=timezone.utc).astimezone(IST).date().isoformat()
        key=(r.location_id,r.method,day)
        g=groups.setdefault(key,dict(location=s.get(Location,r.location_id).name,method=r.method,date=day,count=0,amount=0))
        g["count"]+=1; g["amount"]+=r.amount
    waits=[(r.confirmed_at-r.created_at).total_seconds() for r in confirmed if r.method=="cash"]
    return dict(cash_total=sum(r.amount for r in confirmed if r.method=="cash"),cash_count=sum(r.method=="cash" for r in confirmed),
        demo_total=sum(r.amount for r in confirmed if r.method=="demo"),demo_count=sum(r.method=="demo" for r in confirmed),
        pending_cash=sum(r.method=="cash" and r.state=="pending" for r in rows),total=len(rows),page=page,
        completion_rate=round(len(confirmed)/len(rows)*100,1) if rows else 0,
        average_cash_wait_seconds=round(sum(waits)/len(waits)) if waits else None,
        failed=sum(r.state=="failed" for r in rows),cancelled=sum(r.state=="cancelled" for r in rows),
        breakdown=list(groups.values()),rows=[payload(s,r) for r in rows[(page-1)*25:page*25]],refreshed_at=iso(now()))
@app.get("/api/owner/export")
def export(start:date,end:date,location_id:int|None=None,method:Literal["cash","demo"]|None=None,search:str="",s=Depends(db),u=Depends(owner)):
    rows=filtered(s,start,end,location_id,method,search); out=io.StringIO(); w=csv.writer(out)
    w.writerow(["Environment","Receipt","Reference","Location","Vehicle","Amount INR","Method","State","Created IST","Confirmed IST"])
    def safe(x):
        x=str(x or "")
        return "'"+x if x.lstrip().startswith(("=","+","-","@","\\t","\\r")) else x
    for r in rows:
        p=payload(s,r)
        vals=["RESEARCH PROTOTYPE",p["receipt_number"],r.reference,p["location"],r.vehicle,f"{r.amount/100:.2f}","DEMO NO MONEY COLLECTED" if r.method=="demo" else "cash",r.state,
          r.created_at.replace(tzinfo=timezone.utc).astimezone(IST).isoformat(),r.confirmed_at.replace(tzinfo=timezone.utc).astimezone(IST).isoformat() if r.confirmed_at else ""]
        w.writerow([safe(x) for x in vals])
    return Response(out.getvalue(),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=parkreceipt-research.csv"})
''')
put('backend/app/seed.py','''import os
from sqlalchemy import select
from pwdlib import PasswordHash
from .models import Session, Location, User
password=os.environ.get("SEED_PASSWORD")
if not password or len(password)<12: raise SystemExit("Set SEED_PASSWORD to a unique password of at least 12 characters.")
with Session() as s:
    for letter in "abc":
        slug="parking-"+letter
        loc=s.scalar(select(Location).where(Location.slug==slug))
        if not loc:
            loc=Location(slug=slug,name="Parking "+letter.upper(),rate=3000); s.add(loc); s.flush()
        username="staff-"+letter
        if not s.scalar(select(User).where(User.username==username)):
            s.add(User(username=username,password_hash=PasswordHash.recommended().hash(password),role="staff",location_id=loc.id))
    if not s.scalar(select(User).where(User.username=="owner")):
        s.add(User(username="owner",password_hash=PasswordHash.recommended().hash(password),role="owner"))
    s.commit()
print("Seeded locations and missing accounts: owner, staff-a, staff-b, staff-c. Existing passwords unchanged.")
''')
put('backend/alembic.ini','''[alembic]
script_location = migrations
prepend_sys_path = .
''')
put('backend/migrations/env.py','''from alembic import context
from app.models import engine, Base
with engine.connect() as connection:
    context.configure(connection=connection,target_metadata=Base.metadata)
    with context.begin_transaction(): context.run_migrations()
''')
put('backend/migrations/versions/001_initial.py','''"""Initial prototype schema."""
from alembic import op
from app.models import Base
revision="001"
down_revision=None
branch_labels=None
depends_on=None
def upgrade(): Base.metadata.create_all(op.get_bind())
def downgrade(): Base.metadata.drop_all(op.get_bind())
''')
put('.env.example','''MYSQL_DATABASE=parkreceipt
MYSQL_USER=parkreceipt
MYSQL_PASSWORD=replace-with-local-db-password
MYSQL_ROOT_PASSWORD=replace-with-local-root-password
DATABASE_URL=mysql+pymysql://parkreceipt:replace-with-local-db-password@db:3306/parkreceipt
SEED_PASSWORD=replace-with-unique-12-plus-character-password
PAYMENT_MODE=demo
APP_ORIGIN=http://localhost:5173
COOKIE_SECURE=false
''')
put('compose.yaml','''services:
  db:
    image: mysql:8.4
    environment:
      MYSQL_DATABASE: ${MYSQL_DATABASE}
      MYSQL_USER: ${MYSQL_USER}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
    volumes: [mysql_data:/var/lib/mysql]
    healthcheck:
      test: [CMD-SHELL, 'mysqladmin ping -h localhost -u root -p"$$MYSQL_ROOT_PASSWORD"']
      interval: 5s
      timeout: 5s
      retries: 30
  api:
    build: ./backend
    env_file: .env
    depends_on:
      db: {condition: service_healthy}
    command: sh -c "alembic upgrade head && python -m app.seed && uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log"
  web:
    build: ./frontend
    ports: ["5173:80"]
    depends_on: [api]
volumes:
  mysql_data:
''')
put('backend/Dockerfile','''FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
''')
put('.gitignore','''.env
.venv/
__pycache__/
.pytest_cache/
*.db
node_modules/
dist/
''')
put('frontend/package.json','''{"name":"parkreceipt","version":"0.1.0","private":true,"type":"module","scripts":{"dev":"vite --host 127.0.0.1","build":"tsc --noEmit && vite build"},"dependencies":{"react":"^19.0.0","react-dom":"^19.0.0","qrcode":"^1.5.4"},"devDependencies":{"@types/react":"^19.0.0","@types/react-dom":"^19.0.0","@types/qrcode":"^1.5.5","typescript":"^5.8.0","vite":"^6.3.0"}}''')
put('frontend/tsconfig.json','''{"compilerOptions":{"target":"ES2022","lib":["ES2022","DOM","DOM.Iterable"],"module":"ESNext","moduleResolution":"bundler","jsx":"react-jsx","strict":true,"skipLibCheck":true,"noEmit":true},"include":["src"]}''')
put('frontend/vite.config.js','''import {defineConfig} from 'vite';
export default defineConfig({server:{proxy:{'/api':'http://127.0.0.1:8000'}}});
''')
put('frontend/index.html','''<!doctype html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><meta name="referrer" content="no-referrer"><title>ParkReceipt · Research prototype</title></head><body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body></html>''')
put('frontend/Dockerfile','''FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
''')
put('frontend/nginx.conf','''server {
 listen 80;
 root /usr/share/nginx/html;
 location /api/ { proxy_pass http://api:8000; }
 location / { try_files $uri /index.html; }
}
''')
