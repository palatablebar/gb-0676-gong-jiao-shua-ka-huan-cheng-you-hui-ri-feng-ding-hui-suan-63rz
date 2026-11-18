import hashlib,re
from datetime import datetime,timezone
from app.config import COLUMNS
from app.errors import DomainError
from app.reasons import TERMINAL
from app.modules.m1_taps.rules import evaluate as intake,decode
from app import pipeline,store
DAY_RE=re.compile(r"\d{4}-\d{2}-\d{2}")
def _gap(entry,final_keys,index):
    "隔离行的缺口去向：终态排除 / 已被采信覆盖 / 待补件。"
    key=entry.get("key");reason=entry.get("reason")
    if reason in TERMINAL:
        entry["gap"]="terminal";entry["note"]="失败刷卡不构成扣费记录，终态排除";return
    if not key:
        entry["gap"]="terminal";entry["note"]="无业务键，不构成记录，终态排除";return
    if key in final_keys:
        g,line=final_keys[key];entry["gap"]="covered"
        earlier=g<index or (g==index and line<entry["line"])
        entry["note"]=f"该键已采信于 文件{g+1} 第{line}行，本行留证不采" if earlier else f"已由 文件{g+1} 第{line}行 补件采信"
    else:
        entry["gap"]="open";entry["note"]="待补件"
def build(day,files):
    "按到达顺序合并全部来源文件：文件内先见为准，跨文件同键以后到补件为准，被取代行留痕。"
    per=[(f,intake(f["text"].encode("utf-8"))) for f in files]
    holder={};superseded={};crossdup={}
    for i,(f,r) in enumerate(per):
        for row in r["rows"]:
            key=row[COLUMNS[0]];raw=tuple(row["_raw"]);line=row["_line"]
            if key not in holder: holder[key]=(i,line,raw)
            elif holder[key][2]==raw: crossdup[(i,line)]=(holder[key][0],holder[key][1])
            else:
                superseded[(holder[key][0],holder[key][1])]=(i,line)
                holder[key]=(i,line,raw)
    merged_rows=[];merged_q=[]
    for i,(f,r) in enumerate(per):
        for row in r["rows"]:
            if (i,row["_line"]) in crossdup or (i,row["_line"]) in superseded: continue
            merged_rows.append({**row,"_file":i,"_sources":[f"{i}:{row['_line']}"]})
        for q in r["quarantine"]:
            merged_q.append({**q,"_file":i,"_sources":[f"{i}:{q['_line']}"]})
    metrics={"input":sum(r["metrics"]["input"] for f,r in per),"accepted":len(merged_rows),"quarantine":len(merged_q),
        "duplicate":sum(r["metrics"]["duplicate"] for f,r in per)+len(crossdup),"blank":sum(r["metrics"]["blank"] for f,r in per),
        "repeated_headers":sum(r["metrics"]["repeated_headers"] for f,r in per),"superseded":len(superseded)}
    identity="\n".join(f["sha256"] for f in files).encode()
    run=pipeline.calculate_rows({"rows":merged_rows,"quarantine":merged_q,"metrics":metrics},identity=identity)
    store.save(run["run_id"],run)
    final_keys={row[COLUMNS[0]]:(row["_file"],row["_line"]) for row in run["stages"][-1]["rows"]}
    downstream={}
    for q in run["stages"][-1]["cumulative_quarantine"]:
        if q.get("_stage")!="taps": downstream[(q["_file"],q["_line"])]=q
    ledger=[]
    for i,(f,r) in enumerate(per):
        for e in r["ledger"]:
            entry={"file":i+1,"file_name":f["name"],"line":e["line"],"key":e.get("key"),"disposition":e["disposition"],
                "reason":e.get("reason"),"stage":None,"gap":None,"note":""}
            kind=e["disposition"]
            if kind=="blank": entry["note"]="空行，不构成记录"
            elif kind=="repeated_header": entry["note"]="分段表头，已跳过"
            elif kind=="duplicate": entry["note"]=f"与 文件{i+1} 第{e['of']}行 完全相同，不重复入账"
            elif kind=="quarantine":
                entry["stage"]="taps";_gap(entry,final_keys,i)
            elif (i,e["line"]) in crossdup:
                g,line=crossdup[(i,e["line"])]
                entry["disposition"]="duplicate";entry["note"]=f"与 文件{g+1} 第{line}行 完全相同，不重复入账"
            elif (i,e["line"]) in superseded:
                g,line=superseded[(i,e["line"])]
                entry["disposition"]="superseded";entry["note"]=f"被 文件{g+1} 第{line}行 取代，以补件为准"
            elif (i,e["line"]) in downstream:
                q=downstream[(i,e["line"])]
                entry["disposition"]="quarantine";entry["reason"]=q["reason"];entry["stage"]=q.get("_stage")
                _gap(entry,final_keys,i)
            else: entry["note"]=f"采信为记录 {e['key']}"
            ledger.append(entry)
    if len(ledger)!=metrics["input"] or len({(e["file"],e["line"]) for e in ledger})!=len(ledger):
        raise DomainError("LEDGER_GAP","来源行登记不完整，拒绝生成日结")
    gaps={"open":sum(e["gap"]=="open" for e in ledger),"covered":sum(e["gap"]=="covered" for e in ledger),"terminal":sum(e["gap"]=="terminal" for e in ledger)}
    clearing=run["stages"][5]["metrics"]
    return {"day":day,"run_id":run["run_id"],
        "files":[{"seq":f["seq"],"name":f["name"],"sha256":f["sha256"],"metrics":f["metrics"]} for f in files],
        "gaps":gaps,"ledger":ledger,
        "metrics":{**metrics,**clearing,"files":len(files)},
        "ready_to_seal":bool(clearing["balanced"]) and gaps["open"]==0,
        "updated_at":datetime.now(timezone.utc).isoformat()}
def add_file(day,name,raw):
    "并入一个来源文件；同内容重试直接返回当前日结，不产生第二份结果。"
    if not DAY_RE.fullmatch(day): raise DomainError("BAD_DAY","日结日期格式应为YYYY-MM-DD")
    existing=store.get_day(day)
    if existing and existing["sealed"]: raise DomainError("DAY_SEALED","日结已封存，不能再并入文件",409)
    files=store.day_files(day)
    sha=hashlib.sha256(raw).hexdigest()
    if any(f["sha256"]==sha for f in files): return {"added":False,"day":existing}
    text,_=decode(raw)
    result=intake(raw)
    record={"seq":(files[-1]["seq"]+1) if files else 1,"name":name or f"文件{len(files)+1}","sha256":sha,"text":text,"metrics":result["metrics"]}
    payload=build(day,files+[record])
    return {"added":True,"day":store.add_day_file(day,record,payload,existing["version"] if existing else None)}
def seal(day,version):
    "对平（行数守恒且无未决缺口）后才允许封存为完整日结。"
    current=store.get_day(day)
    if not current: raise DomainError("NOT_FOUND","日结不存在",404)
    if current["sealed"]: raise DomainError("DAY_SEALED","日结已封存",409)
    if not current["metrics"]["balanced"] or current["gaps"]["open"]>0:
        raise DomainError("OPEN_GAPS","存在未对平缺口，不得封存为完整日结",409)
    payload={k:v for k,v in current.items() if k not in ("version","sealed","state")}
    payload["sealed_at"]=datetime.now(timezone.utc).isoformat()
    return store.seal_day(day,payload,version)
