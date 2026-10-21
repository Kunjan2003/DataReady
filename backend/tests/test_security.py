import pytest
from app.core.security import validate_upload

def test_csv_rejects_binary_content(tmp_path):
    path=tmp_path/"sample.csv"
    path.write_bytes(b"name,email\nA,a@example.com\n")
    validate_upload(path,".csv")
    path.write_bytes(b"PK\x03\x04binary")
    with pytest.raises(ValueError):
        validate_upload(path,".csv")

def test_upload_extension_must_match_contents(tmp_path):
    path=tmp_path/"wrong.pdf"
    path.write_bytes(b"not a pdf")
    with pytest.raises(ValueError,match="do not match"):
        validate_upload(path,".pdf")

def test_xlsx_must_be_a_workbook_and_within_expanded_limit(tmp_path):
    import zipfile
    path=tmp_path/"book.xlsx"
    with zipfile.ZipFile(path,"w") as archive:
        archive.writestr("xl/workbook.xml","<workbook/>")
    validate_upload(path,".xlsx")
    with pytest.raises(ValueError,match="expanded workbook is too large"):
        validate_upload(path,".xlsx",max_expanded_mb=0)
