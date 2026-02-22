from pathlib import Path
from apps.documents.services.pdf_utils import _read_source_bytes


def test_read_source_bytes_accepts_path(tmp_path):
    p = tmp_path / "a.bin"
    p.write_bytes(b"abc")

    data = _read_source_bytes(Path(str(p)))
    assert data == b"abc"


def test_path_bytes_reads_file(tmp_path):
    p = tmp_path / "b.bin"
    p.write_bytes(b"xyz")

    assert Path(str(p)).bytes() == b"xyz"
