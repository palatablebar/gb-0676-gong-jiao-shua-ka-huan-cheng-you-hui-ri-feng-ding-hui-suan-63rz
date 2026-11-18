from app.modules.m7_settlement.rules import evaluate
from app.pipeline import calculate,load_sample
from app.errors import DomainError
import pytest
def test_real_sample_archive_stays_provisional(result):
    "带隔离缺口的批次不得显示为可封存的完整归档"
    m=result["stages"][6]["metrics"];assert m["ready"] is False and m["gaps"]==result["stages"][5]["metrics"]["quarantine_inputs"]>0
def test_clean_sample_archive_ready():
    m=calculate(load_sample("clean.csv"))["stages"][6]["metrics"];assert m["ready"] is True and m["gaps"]==0
def test_real_sample_archive_source_count(result): assert result["stages"][6]["metrics"]["source_lines"]==result["stages"][5]["metrics"]["accepted_inputs"]
def test_real_sample_seal_stable(result):
    rows=result["stages"][5]["rows"];assert evaluate(rows,{})["metrics"]["sha256"]==evaluate(rows,{})["metrics"]["sha256"]
def test_unbalanced_blocked():
    with pytest.raises(DomainError) as e:evaluate([],{"reconcile":{"metrics":{"balanced":False}}})
    assert e.value.code=="UNBALANCED"
def test_duplicate_archive_key():
    with pytest.raises(DomainError):evaluate([{"event_id":"1"},{"event_id":"1"}],{})
def test_real_sample_manifest_has_hash(result): assert len(result["manifest"]["input_sha256"])==64
def test_real_sample_export_rows_match(result): assert result["stages"][6]["rows"]==result["stages"][5]["rows"]
