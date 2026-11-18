import sqlite3,json
from pathlib import Path
from app.config import DATA_DIR
from app.errors import DomainError
def connect():
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(DATA_DIR/"records.db",timeout=20)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY,payload TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,decision TEXT NOT NULL DEFAULT '待复核')")
    db.execute("CREATE TABLE IF NOT EXISTS days (day TEXT PRIMARY KEY,payload TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,sealed INTEGER NOT NULL DEFAULT 0)")
    db.execute("CREATE TABLE IF NOT EXISTS day_files (day TEXT NOT NULL,seq INTEGER NOT NULL,name TEXT NOT NULL,sha256 TEXT NOT NULL,text TEXT NOT NULL,metrics TEXT NOT NULL,PRIMARY KEY(day,seq))")
    return db
def save(run_id,payload):
    with connect() as db:
        db.execute("INSERT OR IGNORE INTO runs(id,payload) VALUES (?,?)",(run_id,json.dumps(payload,ensure_ascii=False)))
    return get(run_id)
def get(run_id):
    with connect() as db: row=db.execute("SELECT payload,version,decision FROM runs WHERE id=?",(run_id,)).fetchone()
    if not row: raise DomainError("NOT_FOUND","批次不存在",404)
    return {**json.loads(row[0]),"version":row[1],"decision":row[2]}
def latest():
    with connect() as db: row=db.execute("SELECT id FROM runs ORDER BY rowid DESC LIMIT 1").fetchone()
    return get(row[0]) if row else None
def history():
    with connect() as db: return [{"run_id":i,"version":v,"decision":d} for i,v,d in db.execute("SELECT id,version,decision FROM runs ORDER BY rowid DESC")]
def review(run_id,version,decision):
    if decision not in {"已复核","退回复核"}: raise DomainError("BAD_DECISION","复核状态无效")
    with connect() as db:
        cursor=db.execute("UPDATE runs SET version=version+1,decision=? WHERE id=? AND version=?",(decision,run_id,version))
        if cursor.rowcount!=1:
            if not db.execute("SELECT 1 FROM runs WHERE id=?",(run_id,)).fetchone(): raise DomainError("NOT_FOUND","批次不存在",404)
            raise DomainError("STALE_VERSION","版本已更新，请刷新",409)
    return get(run_id)
def _day_out(row):
    payload=json.loads(row[0]);sealed=bool(row[2])
    return {**payload,"version":row[1],"sealed":sealed,"state":"完整" if sealed else "暂定"}
def get_day(day):
    with connect() as db: row=db.execute("SELECT payload,version,sealed FROM days WHERE day=?",(day,)).fetchone()
    return _day_out(row) if row else None
def latest_day():
    with connect() as db: row=db.execute("SELECT payload,version,sealed FROM days ORDER BY rowid DESC LIMIT 1").fetchone()
    return _day_out(row) if row else None
def list_days():
    with connect() as db:
        return [_day_out(row) for row in db.execute("SELECT payload,version,sealed FROM days ORDER BY rowid DESC")]
def day_files(day):
    with connect() as db:
        return [{"seq":s,"name":n,"sha256":h,"text":t,"metrics":json.loads(m)} for s,n,h,t,m in db.execute("SELECT seq,name,sha256,text,metrics FROM day_files WHERE day=? ORDER BY seq",(day,))]
def add_day_file(day,file_record,payload,expected_version):
    "同一事务内登记来源文件并改写日结单；版本不符或已封存时拒绝。"
    with connect() as db:
        try:
            if expected_version is None:
                db.execute("INSERT INTO days(day,payload) VALUES (?,?)",(day,json.dumps(payload,ensure_ascii=False)))
            else:
                cursor=db.execute("UPDATE days SET payload=?,version=version+1 WHERE day=? AND version=? AND sealed=0",(json.dumps(payload,ensure_ascii=False),day,expected_version))
                if cursor.rowcount!=1:
                    row=db.execute("SELECT sealed FROM days WHERE day=?",(day,)).fetchone()
                    if not row: raise DomainError("NOT_FOUND","日结不存在",404)
                    if row[0]: raise DomainError("DAY_SEALED","日结已封存，不能再并入文件",409)
                    raise DomainError("STALE_VERSION","版本已更新，请刷新",409)
            db.execute("INSERT INTO day_files(day,seq,name,sha256,text,metrics) VALUES (?,?,?,?,?,?)",(day,file_record["seq"],file_record["name"],file_record["sha256"],file_record["text"],json.dumps(file_record["metrics"],ensure_ascii=False)))
        except sqlite3.IntegrityError:
            raise DomainError("STALE_VERSION","版本已更新，请刷新",409)
    return get_day(day)
def seal_day(day,payload,version):
    with connect() as db:
        cursor=db.execute("UPDATE days SET payload=?,sealed=1,version=version+1 WHERE day=? AND version=? AND sealed=0",(json.dumps(payload,ensure_ascii=False),day,version))
        if cursor.rowcount!=1:
            row=db.execute("SELECT sealed FROM days WHERE day=?",(day,)).fetchone()
            if not row: raise DomainError("NOT_FOUND","日结不存在",404)
            if row[0]: raise DomainError("DAY_SEALED","日结已封存",409)
            raise DomainError("STALE_VERSION","版本已更新，请刷新",409)
    return get_day(day)
