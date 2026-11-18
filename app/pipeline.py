import time
from app.config import ROOT,MODULES
from app.errors import DomainError
from app.values import scalar
from app.manifest import digest,manifest
from app import store
from app.modules.m1_taps.rules import evaluate as stage1
from app.modules.m2_routes.rules import evaluate as stage2
from app.modules.m3_fares.rules import evaluate as stage3
from app.modules.m4_journeys.rules import evaluate as stage4
from app.modules.m5_discounts.rules import evaluate as stage5
from app.modules.m6_clearing.rules import evaluate as stage6
from app.modules.m7_settlement.rules import evaluate as stage7
STAGES=[stage1,stage2,stage3,stage4,stage5,stage6,stage7]
def load_sample(name):
    if name not in {"dirty.csv","clean.csv","legacy.csv"}: raise DomainError("BAD_SAMPLE","样例不存在",404)
    return (ROOT/"sample_data"/name).read_bytes()
def _tag(result,slug):
    for entry in result.get("quarantine",[]): entry.setdefault("_stage",slug)
def _advance(context,functions,offset,rows=None):
    results=[]
    for index,stage in enumerate(functions,offset):
        result=stage(context["raw"] if index==0 else rows,context)
        result=scalar(result);rows=result["rows"]
        _tag(result,MODULES[index][0])
        context["quarantine"].extend(result.get("quarantine",[]))
        if index==0: context["intake"]=result["metrics"]
        result["cumulative_quarantine"]=list(context["quarantine"])
        context[MODULES[index][0]]=result
        results.append(result)
    return results
def calculate(raw,params=None,stop=6):
    params=params or {};started=time.monotonic();context={"parameters":params,"raw":raw,"quarantine":[]}
    stages=_advance(context,STAGES[:stop+1],0)
    return {"run_id":digest(raw,params)[:20],"stages":stages,"manifest":manifest(raw,params,started),"parameters":params}
def calculate_rows(intake_stage,params=None,identity=b""):
    "日结合并后的采信结果作为第一级，继续跑二至七级；identity为来源文件摘要序列。"
    params=params or {};started=time.monotonic()
    first=scalar(intake_stage);_tag(first,MODULES[0][0])
    first["cumulative_quarantine"]=list(first.get("quarantine",[]))
    context={"parameters":params,"raw":b"","quarantine":list(first.get("quarantine",[])),"intake":first["metrics"],MODULES[0][0]:first}
    stages=[first]+_advance(context,STAGES[1:],1,first["rows"])
    return {"run_id":digest(identity,params)[:20],"stages":stages,"manifest":manifest(identity,params,started),"parameters":params}
def execute(raw,params=None):
    result=calculate(raw,params);return store.save(result["run_id"],result)
def stage_preview(index,payload):
    if "rows" in payload and index>0:
        if not isinstance(payload["rows"],list) or any(not isinstance(row,dict) for row in payload["rows"]): raise DomainError("BAD_ROWS","记录需要对象列表")
        if not isinstance(payload.get("context",{}),dict): raise DomainError("BAD_CONTEXT","上下文需要对象")
        return scalar(STAGES[index](payload["rows"],payload.get("context",{"parameters":{},"quarantine":[]})))
    raw=payload.get("csv")
    raw=raw.encode() if isinstance(raw,str) else load_sample(payload.get("sample","dirty.csv"))
    return calculate(raw,payload.get("parameters",{}),index)["stages"][-1]
