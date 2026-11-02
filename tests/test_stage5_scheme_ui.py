import hashlib
import json
from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_source_catalogue_page_displays_both_schemes_without_model_calls(tmp_path):
    folder = tmp_path / "modules/l0l4-memory/data/experiments/development-identity-audit-v3-20261101"
    folder.mkdir(parents=True)
    docs = []
    for ident, month in (("S1", "01"), ("S2", "02")):
        text = f"2024年{int(month)}月1日，公司召开董事会会议，审议通过《关于回购股份方案的议案》。"
        docs.append({"id": ident, "stock_code": "600001", "company": "Example", "title": "回购报告书", "text": text,
                     "text_sha256": hashlib.sha256(text.encode()).hexdigest(), "disclosure_date": f"2024-{month}-02",
                     "source_url": "https://example.test/" + ident, "split_candidate": "development"})
    (folder / "development-source-corpus.jsonl").write_text("".join(json.dumps(d) + "\n" for d in docs), encoding="utf-8")
    app = AppTest.from_string(f"from pathlib import Path\nfrom stage5_scheme_ui import render_scheme_catalogue\nrender_scheme_catalogue(Path({str(tmp_path)!r}))").run(timeout=25)
    assert not app.exception
    assert len(app.dataframe[0].value) == 2
    assert set(app.dataframe[0].value["board_date_candidate"]) == {"2024-01-01", "2024-02-01"}
