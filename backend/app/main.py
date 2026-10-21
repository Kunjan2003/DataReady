from pathlib import Path
from uuid import uuid4
import io, csv, json
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Request, Response, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, case, or_, cast, Text
from collections import defaultdict, deque
from threading import Lock
from time import monotonic
from alembic import command
from alembic.config import Config
from app.core.config import settings
from app.api.deps import get_db, current_user
from app.models.models import User, Project, UploadedFile, Record, AuditLog
from app.db.session import engine
from app.services.auth import hash_password, verify_password, create_token
from app.services.processing import process_file
from app.services.cleaning import SCHEMA, suggest_mapping
from app.services.dedup import merge_records
from app.core.security import validate_upload

app = FastAPI(title="DataReady API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
ALLOWED = {".xlsx", ".xls", ".csv", ".pdf", ".jpg", ".jpeg", ".png"}
_auth_attempts = defaultdict(deque)
_auth_lock = Lock()

def auth_rate_limit(request: Request):
    now = monotonic()
    key = request.client.host if request.client else "unknown"
    with _auth_lock:
        attempts = _auth_attempts[key]
        while attempts and now - attempts[0] > 900:
            attempts.popleft()
        if len(attempts) >= 10:
            raise HTTPException(429, "Too many sign-in attempts. Try again in 15 minutes.")
        attempts.append(now)

@app.middleware("http")
async def protect_cookie_mutations(request: Request, call_next):
    if request.method in {"POST","PUT","PATCH","DELETE"} and request.cookies.get("dataready_session"):
        origin=request.headers.get("origin","").rstrip("/")
        if not origin or origin not in settings.allowed_origins:
            return Response("Request origin is not allowed",status_code=403)
    return await call_next(request)

@app.on_event("startup")
def startup():
    settings.upload_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    alembic_cfg=Config(str(Path(__file__).resolve().parents[1]/"alembic.ini"))
    alembic_cfg.set_main_option("script_location",str(Path(__file__).resolve().parents[1]/"alembic"))
    from sqlalchemy import inspect
    schema=inspect(engine)
    if schema.has_table("users") and not schema.has_table("alembic_version"):
        # Upgrade databases created by the original MVP schema in place.
        command.stamp(alembic_cfg,"0001_initial")
    command.upgrade(alembic_cfg,"head")

@app.get("/health")
def health(): return {"status": "ok"}

def auth_cookie(response: Response, token: str):
    response.set_cookie("dataready_session",token,max_age=86400,httponly=True,secure=settings.cookie_secure,samesite="strict",path="/")

@app.post("/api/auth/signup")
def signup(payload: dict, response: Response, request: Request, db: Session = Depends(get_db)):
    auth_rate_limit(request)
    email = str(payload.get("email", "")).strip().lower(); password = str(payload.get("password", ""))
    if "@" not in email or len(email) > 320: raise HTTPException(422, "Enter a valid email address")
    try: password_hash = hash_password(password)
    except ValueError as exc: raise HTTPException(422, str(exc))
    if db.query(User).filter_by(email=email).first(): raise HTTPException(409, "An account with this email already exists")
    user = User(email=email, password_hash=password_hash); db.add(user); db.commit(); db.refresh(user)
    auth_cookie(response,create_token(user.id))
    return {"user": {"id": user.id, "email": user.email}}

@app.post("/api/auth/login")
def login(payload: dict, response: Response, request: Request, db: Session = Depends(get_db)):
    auth_rate_limit(request)
    email = str(payload.get("email", "")).strip().lower(); user = db.query(User).filter_by(email=email).first()
    if not user or not verify_password(str(payload.get("password", "")), user.password_hash): raise HTTPException(401, "Email or password is incorrect")
    auth_cookie(response,create_token(user.id))
    return {"user": {"id": user.id, "email": user.email}}

@app.post("/api/auth/logout")
def logout(response:Response):
    response.delete_cookie("dataready_session",path="/",httponly=True,secure=settings.cookie_secure,samesite="strict")
    return {"ok":True}

@app.get("/api/me")
def me(user: User = Depends(current_user)): return {"id": user.id, "email": user.email}

def owned_project(db, project_id, user):
    project = db.query(Project).filter_by(id=project_id, user_id=user.id).first()
    if not project: raise HTTPException(404, "Project not found")
    return project

@app.get("/api/projects")
def projects(db: Session = Depends(get_db), user: User = Depends(current_user)):
    result=[]
    for p in db.query(Project).filter_by(user_id=user.id).order_by(Project.created_at.desc()).all():
        total = db.query(func.count(Record.id)).filter_by(project_id=p.id, status="active").scalar() or 0
        result.append({"id":p.id,"name":p.name,"created_at":p.created_at,"records":total,"files":len(p.files)})
    return result

@app.post("/api/projects")
def create_project(payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    name = str(payload.get("name", "")).strip()
    if not name or len(name)>180: raise HTTPException(422, "Project name must be between 1 and 180 characters")
    p=Project(user_id=user.id,name=name);db.add(p);db.commit();db.refresh(p);return {"id":p.id,"name":p.name,"records":0,"files":0}

@app.delete("/api/projects/{project_id}")
def delete_project(project_id:int, db:Session=Depends(get_db), user:User=Depends(current_user)):
    p=owned_project(db,project_id,user)
    for f in p.files:
        try: Path(f.storage_path).unlink(missing_ok=True)
        except OSError: pass
    db.delete(p);db.commit();return {"ok":True}

@app.post("/api/projects/{project_id}/files")
async def upload(project_id:int, background:BackgroundTasks, files:list[UploadFile]=File(...), allow_ai:bool=Form(False), db:Session=Depends(get_db), user:User=Depends(current_user)):
    p=owned_project(db,project_id,user)
    if not files or len(files)>20: raise HTTPException(422,"Upload between 1 and 20 files at a time")
    responses=[]
    for item in files:
        suffix=Path(item.filename or "").suffix.lower()
        if suffix not in ALLOWED: raise HTTPException(415,"Supported files: Excel, CSV, PDF, JPG, PNG")
        folder=settings.upload_dir/str(user.id)/str(project_id);folder.mkdir(parents=True,exist_ok=True,mode=0o700)
        path=folder/f"{uuid4().hex}{suffix}";size=0
        try:
            with path.open("wb") as out:
                while chunk:=await item.read(1024*1024):
                    size+=len(chunk)
                    if size>settings.max_upload_mb*1024*1024: raise HTTPException(413,f"Each file must be under {settings.max_upload_mb} MB")
                    out.write(chunk)
            if size==0: raise HTTPException(422,"Empty files cannot be uploaded")
            try:
                validate_upload(path, suffix, settings.max_expanded_upload_mb)
            except ValueError as exc:
                raise HTTPException(415, str(exc)) from exc
            f=UploadedFile(project_id=p.id,original_name=Path(item.filename or "upload").name[:255],storage_path=str(path),status="queued",allow_ai=allow_ai);db.add(f);db.commit();db.refresh(f)
            try:
                from redis import Redis
                from rq import Queue
                Queue("default", connection=Redis.from_url(settings.redis_url, socket_connect_timeout=1)).enqueue("app.worker.tasks.process_file_job", f.id)
            except Exception:
                # Keeps direct local development usable without Redis.
                background.add_task(run_processing, f.id)
            responses.append({"id":f.id,"name":f.original_name,"status":f.status,"progress":f.progress})
        except Exception:
            path.unlink(missing_ok=True);raise
    return responses

def run_processing(file_id):
    from app.db.session import SessionLocal
    db=SessionLocal()
    try: process_file(db,file_id)
    finally: db.close()

@app.get("/api/projects/{project_id}/files")
def list_files(project_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    p=owned_project(db,project_id,user)
    return [{"id":f.id,"name":f.original_name,"status":f.status,"progress":f.progress,"error":f.error,"rows":f.row_count,"mapping":f.mapping or (suggest_mapping(list((db.query(Record).filter_by(file_id=f.id).first() or Record(raw_data={})).raw_data.keys())) if f.row_count else {})} for f in p.files]

@app.put("/api/projects/{project_id}/files/{file_id}/mapping")
def save_mapping(project_id:int,file_id:int,payload:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    owned_project(db,project_id,user); f=db.query(UploadedFile).filter_by(id=file_id,project_id=project_id).first()
    if not f: raise HTTPException(404,"File not found")
    mapping=payload.get("mapping")
    if not isinstance(mapping,dict) or any(k not in SCHEMA for k in mapping.values() if k): raise HTTPException(422,"Choose a supported field for every mapped column")
    if len([x for x in mapping.values() if x]) != len(set(x for x in mapping.values() if x)): raise HTTPException(422,"Each standard field can only be used once")
    f.mapping={k:v for k,v in mapping.items() if v};
    # Rebuild cleaned records from preserved source rows so changing a mapping is reversible.
    from app.services.cleaning import clean_record
    for r in db.query(Record).filter_by(file_id=f.id).all():
        previous=dict(r.data);cleaned,_,flags=clean_record(r.raw_data,f.mapping);r.data=cleaned;r.quality_flags=flags
        for field in SCHEMA:
            old,new=previous.get(field),cleaned.get(field)
            if old!=new: db.add(AuditLog(project_id=project_id,record_id=r.id,field=field,old_value=None if old is None else str(old),new_value=None if new is None else str(new),reason="Column mapping changed this field"))
    db.commit();return {"mapping":f.mapping}

@app.get("/api/projects/{project_id}/records")
def records(project_id:int, limit:int=50, offset:int=0, status:str="active", q:str="", db:Session=Depends(get_db), user:User=Depends(current_user)):
    owned_project(db,project_id,user); limit=max(1,min(limit,200)); query=db.query(Record).filter_by(project_id=project_id,status=status)
    if q.strip():
        needle=f"%{q.strip()[:120]}%"
        query=query.filter(cast(Record.data,Text).ilike(needle))
    total=query.count(); rows=query.order_by(Record.id).offset(offset).limit(limit).all()
    return {"total":total,"items":[{"id":r.id,"file_id":r.file_id,"row_number":r.row_number,"raw":r.raw_data,"data":r.data,"flags":r.quality_flags,"duplicate_of":r.duplicate_of,"score":r.duplicate_score,"status":r.status} for r in rows]}

@app.patch("/api/projects/{project_id}/records/{record_id}")
def edit_record(project_id:int,record_id:int,payload:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    owned_project(db,project_id,user); record=db.query(Record).filter_by(id=record_id,project_id=project_id,status="active").first()
    changes=payload.get("data")
    if not record: raise HTTPException(404,"Record not found")
    if not isinstance(changes,dict) or not changes or any(k not in SCHEMA for k in changes): raise HTTPException(422,"Provide valid record fields")
    data=dict(record.data or {})
    for field,value in changes.items():
        value=None if value is None else str(value).strip() or None
        previous=data.get(field)
        if previous!=value:
            db.add(AuditLog(project_id=project_id,record_id=record.id,field=field,old_value=None if previous is None else str(previous),new_value=None if value is None else str(value),reason="Field corrected by user"))
            data[field]=value
    record.data=data;db.commit();return {"id":record.id,"data":record.data}

@app.post("/api/projects/{project_id}/undo-change/{audit_id}")
def undo_change(project_id:int,audit_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    owned_project(db,project_id,user);entry=db.query(AuditLog).filter_by(id=audit_id,project_id=project_id).first()
    if not entry or entry.field not in SCHEMA or entry.record_id is None: raise HTTPException(404,"Undoable change not found")
    record=db.query(Record).filter_by(id=entry.record_id,project_id=project_id).first()
    if not record: raise HTTPException(404,"Record not found")
    data=dict(record.data or {});current=data.get(entry.field)
    if (None if current is None else str(current)) != entry.new_value: raise HTTPException(409,"This field changed again. Undo the newest change first.")
    previous=entry.old_value;data[entry.field]=previous;record.data=data
    db.add(AuditLog(project_id=project_id,record_id=record.id,field=entry.field,old_value=entry.new_value,new_value=previous,reason=f"Undid change {entry.id}"));db.commit();return {"ok":True}

@app.get("/api/projects/{project_id}/review")
def review(project_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    owned_project(db,project_id,user); items=[]
    rows=db.query(Record).filter_by(project_id=project_id,status="review").all()
    for r in rows:
        other=db.get(Record,r.duplicate_of) if r.duplicate_of else None
        if other: items.append({"record":{"id":r.id,"data":r.data},"match":{"id":other.id,"data":other.data},"score":r.duplicate_score})
    return items

@app.post("/api/projects/{project_id}/review/{record_id}")
def resolve_review(project_id:int,record_id:int,payload:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    owned_project(db,project_id,user); record=db.query(Record).filter_by(id=record_id,project_id=project_id,status="review").first()
    if not record: raise HTTPException(404,"Review item not found")
    action=payload.get("action"); matched=db.get(Record,record.duplicate_of)
    if action=="merge" and matched:
        before=dict(matched.data); matched.data=merge_records(matched.data,record.data);record.status="merged"
        db.add(AuditLog(project_id=project_id,record_id=matched.id,field=f"merge:{record.id}",old_value=json.dumps(before),new_value=json.dumps(matched.data),reason="User approved duplicate merge"))
    elif action=="separate": record.status="active";record.duplicate_of=None;record.duplicate_score=None
    else: raise HTTPException(422,"Choose merge or separate")
    db.commit();return {"ok":True}

@app.post("/api/projects/{project_id}/undo-merge/{duplicate_id}")
def undo_merge(project_id:int,duplicate_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    owned_project(db,project_id,user)
    duplicate=db.query(Record).filter_by(id=duplicate_id,project_id=project_id,status="merged").first()
    if not duplicate or not duplicate.duplicate_of: raise HTTPException(404,"Merged record not found")
    target=db.get(Record,duplicate.duplicate_of)
    merge=db.query(AuditLog).filter_by(project_id=project_id,record_id=target.id,field=f"merge:{duplicate.id}").order_by(AuditLog.created_at.desc()).first()
    if not merge: raise HTTPException(409,"Merge history is unavailable")
    later=db.query(AuditLog).filter(AuditLog.project_id==project_id,AuditLog.record_id==target.id,AuditLog.field.like("merge:%"),AuditLog.id>merge.id).first()
    if later: raise HTTPException(409,"Undo newer merges first")
    previous=json.loads(merge.old_value or "{}")
    target.data=previous;duplicate.status="active";duplicate.duplicate_of=None;duplicate.duplicate_score=None
    db.add(AuditLog(project_id=project_id,record_id=target.id,field="undo_merge",old_value=merge.new_value,new_value=json.dumps(previous),reason=f"Undid merge of record {duplicate.id}"))
    db.commit();return {"ok":True}

@app.post("/api/projects/{project_id}/clean")
def clean_project(project_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    owned_project(db,project_id,user); count=0
    for r in db.query(Record).filter_by(project_id=project_id,status="active").all():
        data=dict(r.raw_data); mapping=suggest_mapping(data.keys()); from app.services.cleaning import clean_record
        cleaned,changes,flags=clean_record(data,mapping); r.data=cleaned;r.quality_flags=flags
        for field,old,new,reason in changes: db.add(AuditLog(project_id=project_id,record_id=r.id,field=field,old_value=None if old is None else str(old),new_value=str(new),reason=reason))
        count+=1
    db.commit();return {"processed":count}

@app.get("/api/projects/{project_id}/report")
def report(project_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    p=owned_project(db,project_id,user); all_records=db.query(Record).filter_by(project_id=p.id).all(); active=[r for r in all_records if r.status=="active"]
    duplicate=sum(r.status in ("review","merged") for r in all_records); fixes=db.query(AuditLog).filter_by(project_id=p.id).count(); missing=sum(1 for r in active for v in r.data.values() if v in (None,"")); cells=max(1,len(active)*9); score=round(100*(cells-missing)/cells)
    return {"records":len(active),"duplicates":duplicate,"fields_fixed":fixes,"missing_fields":missing,"quality_score":score,"files":len(p.files),"pending_review":sum(r.status=="review" for r in all_records)}

@app.get("/api/projects/{project_id}/export/{kind}")
def export(project_id:int,kind:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    owned_project(db,project_id,user)
    if kind not in ("csv","json","xlsx"): raise HTTPException(404,"Choose csv, json, or xlsx")
    rows=[r.data for r in db.query(Record).filter_by(project_id=project_id,status="active").order_by(Record.id).all()]
    if kind=="json": data=json.dumps(rows,ensure_ascii=False,indent=2).encode();mime="application/json"
    else:
        frame=__import__("pandas").DataFrame(rows,columns=SCHEMA)
        buffer=io.BytesIO()
        if kind=="csv": frame.to_csv(buffer,index=False);mime="text/csv"
        else: frame.to_excel(buffer,index=False);mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        data=buffer.getvalue()
    return StreamingResponse(io.BytesIO(data),media_type=mime,headers={"Content-Disposition":f"attachment; filename=project-{project_id}.{kind}"})

@app.get("/api/projects/{project_id}/audit")
def audit(project_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    owned_project(db,project_id,user); rows=db.query(AuditLog).filter_by(project_id=project_id).order_by(AuditLog.created_at.desc()).limit(1000).all()
    return [{"id":r.id,"record_id":r.record_id,"field":r.field,"old_value":r.old_value,"new_value":r.new_value,"reason":r.reason,"created_at":r.created_at} for r in rows]

@app.get("/api/projects/{project_id}/audit/export")
def export_audit(project_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    owned_project(db,project_id,user)
    rows=db.query(AuditLog).filter_by(project_id=project_id).order_by(AuditLog.created_at.asc()).all()
    output=io.StringIO();writer=csv.writer(output);writer.writerow(["timestamp","record_id","field","original_value","new_value","reason"])
    for row in rows: writer.writerow([row.created_at.isoformat(),row.record_id,row.field,row.old_value,row.new_value,row.reason])
    return StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")),media_type="text/csv",headers={"Content-Disposition":f"attachment; filename=project-{project_id}-audit.csv"})
