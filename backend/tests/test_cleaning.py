from app.services.cleaning import clean_record, suggest_mapping

def test_mapping_understands_common_business_headers():
    assert suggest_mapping(["Party Name", "Mobile No", "GSTIN", "Invoice Date"])=={"Party Name":"name","Mobile No":"phone","GSTIN":"gst_number","Invoice Date":"date"}

def test_cleaning_preserves_original_and_normalizes_indian_values():
    raw={"Party Name":"  SHAH   traders ","Mobile":"98765 43210","Email":" SALES@EXAMPLE.IN ","GSTIN":"24AAACC1206D1ZM","Date":"31/03/2025","Amount":"₹1,250"}
    mapping={"Party Name":"name","Mobile":"phone","Email":"email","GSTIN":"gst_number","Date":"date","Amount":"amount"}
    data,changes,flags=clean_record(raw,mapping)
    assert data["name"]=="Shah Traders"
    assert data["phone"]=="+919876543210"
    assert data["email"]=="sales@example.in"
    assert data["date"]=="2025-03-31"
    assert data["amount"]=="1250.00"
    assert data["gst_number"]=="24AAACC1206D1ZM"
    assert not flags and changes and raw["Party Name"].startswith("  ")

def test_invalid_values_are_flagged_not_guessed():
    data,_,flags=clean_record({"Phone":"not a phone","GST":"bad"},{"Phone":"phone","GST":"gst_number"})
    assert data["phone"]=="not a phone" and "phone needs review" in flags
    assert "invalid GST format or checksum" in flags
