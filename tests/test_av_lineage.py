import pytest
from obsidiandroid.features.av_lineage import identifier, lineage_components, PUBLIC_TEST_CERTIFICATES


@pytest.mark.parametrize('value',[None,float('nan'),'', 'none', ' None ', 'null', 'unknown', 'N/A', 'TNULL'])
def test_missing_values_never_become_shared_identifiers(value):
    assert identifier(value)==''
    groups=lineage_components([{'sample_id':1,'package':value},{'sample_id':2,'package':value}])
    assert groups[1]!=groups[2]


def test_public_test_certificate_is_not_author_identity():
    signer=next(iter(PUBLIC_TEST_CERTIFICATES))
    rows=[{'sample_id':1,'package':'pkg.one','signer_sha1':signer},
          {'sample_id':2,'package':'pkg.two','signer_sha1':signer}]
    assert len(set(lineage_components(rows).values()))==2
    rows[1]['package']='pkg.one'
    assert len(set(lineage_components(rows).values()))==1


def test_nonpublic_signer_and_valid_similarity_constraints_remain():
    rows=[{'sample_id':1,'package':'a','signer_sha1':'a'*40},
          {'sample_id':2,'package':'b','signer_sha1':'a'*40,'tlsh':'matching-fuzzy-hash'},
          {'sample_id':3,'tlsh':'matching-fuzzy-hash'}]
    assert len(set(lineage_components(rows).values()))==1


def test_structural_vhash_alone_does_not_assert_lineage():
    rows=[{'sample_id':1,'package':'one','vhash':'same'},
          {'sample_id':2,'package':'two','vhash':'same'}]
    assert len(set(lineage_components(rows).values()))==2
    rows[1]['signer_sha1']=rows[0]['signer_sha1']='a'*40
    assert len(set(lineage_components(rows).values()))==1
