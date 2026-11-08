import pytest
from obsidiandroid.features.av_lineage import identifier, lineage_components, PUBLIC_TEST_CERTIFICATES


@pytest.mark.parametrize('value',[None,float('nan'),'', 'none', ' None ', 'null', 'unknown', 'N/A', 'TNULL'])
def test_missing_values_never_become_shared_identifiers(value):
    assert identifier(value)==''
    groups=lineage_components([{'sample_id':1,'package':value},{'sample_id':2,'package':value}])
    assert groups[1]!=groups[2]


@pytest.mark.parametrize('signer', sorted(PUBLIC_TEST_CERTIFICATES))
def test_public_test_certificate_is_not_author_identity(signer):
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


def test_public_platform_certificate_fixture_matches_pinned_aosp_identity():
    import hashlib
    from pathlib import Path
    import ssl
    pem = (Path(__file__).parent / 'fixtures/aosp_platform_695b28f.x509.pem').read_text()
    der = ssl.PEM_cert_to_DER_cert(pem)
    assert hashlib.sha1(der).hexdigest() == '27196e386b875e76adf700e7ea84e4c6eee33dfa'
    assert hashlib.sha256(der).hexdigest() == 'c8a2e9bccf597c2fb6dc66bee293fc13f2fc47ec77bc6b2b0d52c11f51192ab8'
    assert hashlib.sha1(der).hexdigest() in PUBLIC_TEST_CERTIFICATES
