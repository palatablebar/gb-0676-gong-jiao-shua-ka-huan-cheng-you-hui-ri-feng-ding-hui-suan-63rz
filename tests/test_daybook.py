import csv,io,pytest
from app import store,daybook
from app.pipeline import load_sample
from app.errors import DomainError
DAY="2026-11-16"
HEADER="event_id,card,route,event_time,result,reported,note\n"
SUPPLEMENT=(HEADER
    +"0093,0009,01,2026-11-16T08:05:00+08:00,success,2.50,补件\n"
    +"0090,0009,02,2026-11-16T08:10:00+08:00,success,2.50,补件\n"
    +"0091,0009,03,2026-11-16T08:20:00+08:00,success,2.50,补件\n").encode()
@pytest.fixture
def dirty(): return load_sample("dirty.csv")
@pytest.fixture
def day_with_dirty(dirty): return daybook.add_file(DAY,"dirty.csv",dirty)["day"]
def test_provisional_day_with_attributable_gaps(day_with_dirty):
    "裁决：按期先出带缺口的暂定日结，缺口逐行可归因到来源文件与行号"
    d=day_with_dirty
    assert d["state"]=="暂定" and d["sealed"] is False and d["ready_to_seal"] is False
    open_keys={e["key"] for e in d["ledger"] if e["gap"]=="open"}
    assert open_keys=={"0093","0090","0091"} and d["gaps"]["open"]==3
    entry=[e for e in d["ledger"] if e["key"]=="0093"][0]
    assert entry["file_name"]=="dirty.csv" and entry["line"]==41 and entry["reason"]=="BAD_COLUMNS"
def test_every_source_line_has_exactly_one_disposition(day_with_dirty):
    "采信与未采信来源逐行有去向，且与输入行数守恒"
    d=day_with_dirty
    assert len(d["ledger"])==d["metrics"]["input"]==39
    counts={}
    for e in d["ledger"]: counts[e["disposition"]]=counts.get(e["disposition"],0)+1
    assert counts=={"accepted":32,"quarantine":5,"duplicate":1,"repeated_header":1}
    conflict=[e for e in d["ledger"] if e["reason"]=="DUPLICATE_CONFLICT"][0]
    assert conflict["gap"]=="covered" and "留证" in conflict["note"]
    failed=[e for e in d["ledger"] if e["reason"]=="FAILED_TAP"][0]
    assert failed["gap"]=="terminal"
def test_same_file_retry_never_creates_second_settlement(dirty):
    first=daybook.add_file(DAY,"a.csv",dirty)["day"];runs_before=len(store.history())
    again=daybook.add_file(DAY,"a-renamed.csv",dirty)
    assert again["added"] is False
    day=again["day"]
    assert len(day["files"])==1 and day["run_id"]==first["run_id"] and day["version"]==first["version"]
    assert len(store.history())==runs_before
def test_supplement_closes_gaps_without_losing_any_record(day_with_dirty):
    result=daybook.add_file(DAY,"fix.csv",SUPPLEMENT)
    assert result["added"] is True
    d=result["day"]
    assert d["gaps"]["open"]==0 and d["ready_to_seal"] is True and d["metrics"]["balanced"] is True
    assert len(d["ledger"])==39+3
    covered=[e for e in d["ledger"] if e["key"]=="0093" and e["disposition"]=="quarantine"][0]
    assert covered["gap"]=="covered" and "补件" in covered["note"]
    superseded={e["key"] for e in d["ledger"] if e["disposition"]=="superseded"}
    assert superseded=={"0090","0091"}
    accepted=[e for e in d["ledger"] if e["file_name"]=="fix.csv" and e["disposition"]=="accepted"]
    assert len(accepted)==3
    run=store.get(d["run_id"])
    ids={row["event_id"] for row in run["stages"][-1]["rows"]}
    assert {"0093","0090","0091"}<=ids and "0092" not in ids
def test_seal_blocked_until_reconciled(day_with_dirty):
    with pytest.raises(DomainError) as e: daybook.seal(DAY,day_with_dirty["version"])
    assert e.value.code=="OPEN_GAPS" and e.value.status==409
    assert store.get_day(DAY)["sealed"] is False
def test_seal_after_reconcile_then_day_locked(day_with_dirty):
    d=daybook.add_file(DAY,"fix.csv",SUPPLEMENT)["day"]
    sealed=daybook.seal(DAY,d["version"])
    assert sealed["sealed"] is True and sealed["state"]=="完整" and sealed["sealed_at"]
    with pytest.raises(DomainError) as e: daybook.add_file(DAY,"late.csv",SUPPLEMENT)
    assert e.value.code=="DAY_SEALED"
    with pytest.raises(DomainError) as e: daybook.seal(DAY,sealed["version"])
    assert e.value.code=="DAY_SEALED"
def test_seal_requires_current_version(day_with_dirty):
    daybook.add_file(DAY,"fix.csv",SUPPLEMENT)
    with pytest.raises(DomainError) as e: daybook.seal(DAY,day_with_dirty["version"])
    assert e.value.code=="STALE_VERSION"
def test_cross_file_duplicate_and_supersede_are_itemized():
    first=(HEADER+"9001,0001,01,2026-11-16T07:00:00+08:00,success,2.50,首件\n").encode()
    second=(HEADER+"9001,0001,01,2026-11-16T07:00:00+08:00,success,2.50,首件\n"
        +"9002,0001,02,2026-11-16T07:10:00+08:00,success,2.50,次件\n").encode()
    third=(HEADER+"9001,0001,01,2026-11-16T07:00:00+08:00,success,9.00,改\n").encode()
    daybook.add_file(DAY,"f1.csv",first)
    d=daybook.add_file(DAY,"f2.csv",second)["day"]
    assert d["metrics"]["duplicate"]==1 and d["metrics"]["input"]==3
    dup=[e for e in d["ledger"] if e["disposition"]=="duplicate"][0]
    assert dup["file_name"]=="f2.csv" and "文件1" in dup["note"]
    d=daybook.add_file(DAY,"f3.csv",third)["day"]
    old=[e for e in d["ledger"] if e["disposition"]=="superseded"][0]
    assert old["file_name"]=="f1.csv" and old["key"]=="9001" and "文件3" in old["note"]
    run=store.get(d["run_id"])
    row=[r for r in run["stages"][-1]["rows"] if r["event_id"]=="9001"][0]
    assert row["reported"]=="9.00"
def test_invalid_file_rejected_atomically(day_with_dirty):
    files_before=len(store.day_files(DAY))
    for raw,code in [(b"bad","BAD_HEADER"),(b"","EMPTY_FILE"),(HEADER.encode(),"HEADER_ONLY")]:
        with pytest.raises(DomainError) as e: daybook.add_file(DAY,"bad.csv",raw)
        assert e.value.code==code
    assert len(store.day_files(DAY))==files_before
def test_bad_day_name(dirty):
    with pytest.raises(DomainError) as e: daybook.add_file("20261116","a.csv",dirty)
    assert e.value.code=="BAD_DAY"
def test_day_archive_lists_every_line(day_with_dirty):
    from app.archive import build_day_archive
    rows=list(csv.reader(io.StringIO(build_day_archive(day_with_dirty).lstrip("\ufeff"))))
    assert rows[0]==["day","run_id","state","file","file_name","file_line","key","disposition","reason","stage","gap","note"]
    assert len(rows)-1==day_with_dirty["metrics"]["input"]
    assert any(r[7]=="quarantine" and r[10]=="open" for r in rows[1:])
def test_day_api_flow(client,dirty):
    text=dirty.decode("utf-8")
    r=client.post(f"/api/days/{DAY}/files",json={"csv":text,"name":"dirty.csv"})
    assert r.status_code==200 and r.get_json()["added"] is True
    again=client.post(f"/api/days/{DAY}/files",json={"csv":text,"name":"dirty.csv"})
    assert again.status_code==200 and again.get_json()["added"] is False
    assert client.post(f"/api/days/{DAY}/seal",json={"version":1}).status_code==409
    r=client.post(f"/api/days/{DAY}/files",json={"csv":SUPPLEMENT.decode(),"name":"fix.csv"})
    version=r.get_json()["day"]["version"]
    assert client.post(f"/api/days/{DAY}/seal",json={"version":version-1}).status_code==409
    sealed=client.post(f"/api/days/{DAY}/seal",json={"version":version})
    assert sealed.status_code==200 and sealed.get_json()["state"]=="完整"
    assert client.post(f"/api/days/{DAY}/files",json={"csv":SUPPLEMENT.decode()}).status_code==409
    archive=client.get(f"/api/days/{DAY}/archive")
    assert archive.status_code==200 and len(list(csv.reader(io.StringIO(archive.data.decode("utf-8-sig")))))==42+1
    listing=client.get("/api/days").get_json()["days"]
    assert listing[0]["day"]==DAY and listing[0]["state"]=="完整"
    assert client.get("/api/days/1999-01-01").status_code==404
    assert client.post("/api/days/not-a-day/files",json={"csv":text}).status_code==422
def test_day_api_multipart_upload(client,dirty):
    r=client.post(f"/api/days/{DAY}/files",data={"file":(io.BytesIO(dirty),"ops.csv")},content_type="multipart/form-data")
    assert r.status_code==200 and r.get_json()["day"]["files"][0]["name"]=="ops.csv"
