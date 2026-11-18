import csv,io,json
def build_archive(run):
    stream=io.StringIO(newline="");writer=csv.writer(stream)
    writer.writerow(["run_id","input_sha256","rule_version","kind","source_lines","reason","evidence"])
    meta=run["manifest"]
    for row in run["stages"][-1]["rows"]:
        writer.writerow([run["run_id"],meta["input_sha256"],meta["rule_version"],"accepted",json.dumps(row.get("_sources",[])),row.get("status",""),json.dumps(row,ensure_ascii=False)])
    for row in run["stages"][-1].get("cumulative_quarantine",[]):
        writer.writerow([run["run_id"],meta["input_sha256"],meta["rule_version"],"quarantine",json.dumps(row.get("_sources",[])),row.get("reason",""),json.dumps(row,ensure_ascii=False)])
    return "\ufeff"+stream.getvalue()
def build_day_archive(day):
    "日结证据：每个来源文件的每一行都有去向，采信与未采信逐行可查。"
    stream=io.StringIO(newline="");writer=csv.writer(stream)
    writer.writerow(["day","run_id","state","file","file_name","file_line","key","disposition","reason","stage","gap","note"])
    for e in day["ledger"]:
        writer.writerow([day["day"],day["run_id"],day["state"],e["file"],e["file_name"],e["line"],e.get("key") or "",e["disposition"],e.get("reason") or "",e.get("stage") or "",e.get("gap") or "",e["note"]])
    return "\ufeff"+stream.getvalue()
