"""Source locators cannot change identities or establish independent origin."""
import json
import hashlib
import pytest
from obsidiandroid.reporting.source_context import load_context, summarize_context


def test_overlay_bindings_and_unknown_origin(tmp_path):
    m=dict(sample_id=1,sha256='a',event_id=2,payload_hash='b',source_batch_label='batch')
    p=tmp_path/'source.json';p.write_text(json.dumps([dict(sample_id=1,sha256='a',source_url='https://example.org/mirror')]))
    row={k:m[k] for k in ('sample_id','sha256','event_id','payload_hash')}
    row.update(source_ref='catalog',cohort_kind='RETAINED_DESCRIPTIVE')
    overlay=dict(format='retained-source-context-v1',sources={'catalog':dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())},rows=[row])
    def read():return load_context(json.dumps(overlay).encode(),[m])
    result=read();assert result['1']['supported_origin'] is None
    assert summarize_context(result.values())['independent_acquisitions'] is None
    row['event_id']=3
    with pytest.raises(ValueError):read()
    row['event_id']=2;row['accepted_identity']=True
    with pytest.raises(ValueError):read()
    row.pop('accepted_identity');row['source_ref']=None
    result=read();assert result['1']['disposition']=='RECORDED_BATCH_ORIGIN_UNESTABLISHED'
    m['source_batch_label']=''
    assert read()['1']['disposition']=='NO_SUPPORTED_ACQUISITION_CONTEXT_LOCATED'
