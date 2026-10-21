from pathlib import Path
import zipfile

SIGNATURES = {
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".xls": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    ".xlsx": (b"PK\x03\x04",),
}

def validate_upload(path: Path, suffix: str, max_expanded_mb: int = 200) -> None:
    with path.open("rb") as f:
        head = f.read(8192)
    if suffix == ".csv":
        if any(byte < 32 and byte not in (9, 10, 13) for byte in head):
            raise ValueError("This does not look like a CSV file")
        try:
            head.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                head.decode("cp1252")
            except UnicodeDecodeError as exc:
                raise ValueError("CSV text encoding is not supported") from exc
        return
    if not any(head.startswith(s) for s in SIGNATURES.get(suffix, ())):
        raise ValueError("The file contents do not match its extension")
    if suffix == ".xlsx":
        try:
            with zipfile.ZipFile(path) as archive:
                if "xl/workbook.xml" not in archive.namelist():
                    raise ValueError("This is not a valid Excel workbook")
                if sum(x.file_size for x in archive.infolist()) > max_expanded_mb * 1024 * 1024:
                    raise ValueError("The expanded workbook is too large")
        except zipfile.BadZipFile as exc:
            raise ValueError("This is not a valid Excel workbook") from exc
