import csv, hashlib, io, os, re, secrets, time
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
    vehicle=re.sub(r"\s+","",data.vehicle.upper())
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
    pending=list(s.scalars(q.where(PaymentRequest.state=="pending").order_by(PaymentRequest.created_at.asc()).limit(200)))
    confirmed=list(s.scalars(q.where(PaymentRequest.state=="confirmed").order_by(PaymentRequest.confirmed_at.desc()).limit(50)))
    return [payload(s,r) for r in pending+confirmed]
@app.post("/api/staff/requests")
def staff_create(data:NewRequest,req:Request,s=Depends(db),u=Depends(current)):
    loc=s.scalar(select(Location).where(Location.slug==data.location_slug))
    if not loc: raise HTTPException(404,"Location not found.")
    if u.role!="owner" and u.location_id!=loc.id: raise HTTPException(403,"Use your assigned location.")
    if data.method!="cash": raise HTTPException(400,"Staff entry supports cash requests only.")
    return create(data,req,s)

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
        return "'"+x if x.lstrip().startswith(("=","+","-","@","\t","\r")) else x
    for r in rows:
        p=payload(s,r)
        vals=["RESEARCH PROTOTYPE",p["receipt_number"],r.reference,p["location"],r.vehicle,f"{r.amount/100:.2f}","DEMO NO MONEY COLLECTED" if r.method=="demo" else "cash",r.state,
          r.created_at.replace(tzinfo=timezone.utc).astimezone(IST).isoformat(),r.confirmed_at.replace(tzinfo=timezone.utc).astimezone(IST).isoformat() if r.confirmed_at else ""]
        w.writerow([safe(x) for x in vals])
    return Response(out.getvalue(),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=parkreceipt-research.csv"})
