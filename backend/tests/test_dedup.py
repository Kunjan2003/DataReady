from app.services.dedup import score_records, should_compare, merge_records

def test_similar_party_records_score_and_block():
    a={"name":"Shah Traders","phone":"+919876543210","email":"info@shah.in","address":"Market Road Ahmedabad"}
    b={"name":"M/s Shah Trading Co","phone":"+919876543210","email":"info@shah.in","address":"Market Road Ahmedabad"}
    assert should_compare(a,b)
    assert score_records(a,b)>80

def test_merge_prefers_existing_nonempty_values():
    assert merge_records({"name":"A","city":""},{"name":"B","city":"Surat"})=={"name":"A","city":"Surat"}
