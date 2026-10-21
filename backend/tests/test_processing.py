from openpyxl import Workbook
from app.services.processing import read_rows

def test_xlsx_reader_streams_large_sheet_in_chunks(tmp_path):
    path=tmp_path/"large.xlsx"
    workbook=Workbook(write_only=True);sheet=workbook.create_sheet()
    sheet.append(["Name","City"])
    for index in range(10001): sheet.append([f"Customer {index}","Ahmedabad"])
    workbook.save(path)
    batches=list(read_rows(path))
    assert [len(batch) for batch in batches]==[10000,1]
