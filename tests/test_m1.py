import pytest,csv,io
from app.pipeline import load_sample
from app.modules.m1_taps.rules import evaluate,decode
from app.config import COLUMNS
from app.errors import DomainError
def test_bom_real_sample(sample):
    "TRAP-02"
    r=evaluate(sample);assert r["metrics"]["encoding"]=="utf-8-sig" and r["rows"][0][COLUMNS[0]].startswith("00")
def test_legacy_encoding_real_sample():
    "TRAP-01"
    r=evaluate(load_sample("legacy.csv"));assert r["metrics"]["encoding"]=="gb18030" and r["metrics"]["accepted"]>=30
def test_bad_columns_real_sample(sample):
    "TRAP-05"
    assert any(r["reason"]=="BAD_COLUMNS" for r in evaluate(sample)["quarantine"])
def test_duplicate_conflict_real_sample(sample):
    "TRAP-14"
    assert any(r["reason"]=="DUPLICATE_CONFLICT" for r in evaluate(sample)["quarantine"])
def test_identifier_preserved_real_sample(sample):
    "TRAP-08"
    r=evaluate(sample)["rows"][0];assert r[COLUMNS[0]].startswith("00")
def test_three_empty_states():
    "TRAP-18"
    for raw,code in [(b"","EMPTY_FILE"),(b"\n\r\n","BLANK_ONLY"),((",".join(COLUMNS)+"\n").encode(),"HEADER_ONLY")]:
        with pytest.raises(DomainError) as e:evaluate(raw)
        assert e.value.code==code
def test_intake_conservation_real_sample(sample):
    r=evaluate(sample);m=r["metrics"]
    assert m["input"]==m["accepted"]+m["quarantine"]+m["duplicate"]+m["blank"]+m["repeated_headers"]
def test_quoted_newline_is_one_record(sample):
    "TRAP-03"
    r=evaluate(sample);assert any("\n" in str(x) for row in r["rows"] for x in row.values())
def test_ledger_covers_every_input_line(sample):
    "每个来源行恰好一个去向，采信与未采信逐行可查"
    from collections import Counter
    r=evaluate(sample);m=r["metrics"]
    assert len(r["ledger"])==m["input"]
    c=Counter(e["disposition"] for e in r["ledger"])
    assert c["accepted"]==m["accepted"] and c["quarantine"]==m["quarantine"]
    assert c["duplicate"]==m["duplicate"] and c["blank"]==m["blank"] and c["repeated_header"]==m["repeated_headers"]
    assert all(e["reason"] for e in r["ledger"] if e["disposition"]=="quarantine")
