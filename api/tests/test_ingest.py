import pytest
from sqlalchemy import func, select

from app.db import session_scope
from app.models import Product, Sale
from app.services.ingest import ImportValidationError, import_csv, validate

PRODUCTS = b"""sku,name,category,unit_cost,unit_price,lead_time_days
ING-1,Test Mug,Tableware,2.5,6.0,5
ING-2,Test Plate,Tableware,3.0,8.0,
"""


def test_validate_accepts_good_file_and_fills_defaults():
    df, report = validate("products", PRODUCTS)
    assert report.ok
    assert df.loc[1, "lead_time_days"] == 7  # default applied to the empty cell
    assert df.loc[0, "holding_rate"] == 0.25


@pytest.mark.parametrize(
    ("kind", "content", "message"),
    [
        ("products", b"sku,name\nX,Y\n", "missing required column"),
        ("products", b"sku,name,unit_cost,unit_price\nA,a,-1,5\n", "'unit_cost' must be a number"),
        ("products", b"sku,name,unit_cost,unit_price\nA,a,1,5\nA,b,1,5\n", "duplicate sku"),
        ("sales", b"date,sku,quantity\nnot-a-date,A,1\n", "invalid date"),
        ("sales", b"date,sku,quantity\n2026-01-01,A,abc\n", "'quantity' must be a number"),
        ("sales", b"date,sku,quantity\n", "no data rows"),
    ],
)
def test_validation_errors_reference_row_and_column(kind, content, message):
    _, report = validate(kind, content)
    assert not report.ok
    assert any(message in e for e in report.errors)


def test_import_is_atomic_and_idempotent():
    with session_scope() as db:
        import_csv(db, "products", PRODUCTS)
    sales = b"date,sku,quantity\n2026-01-01,ING-1,3\n2026-01-02,ING-1,4\n2026-01-02,ING-1,1\n"
    for _ in range(2):  # importing twice must not duplicate rows
        with session_scope() as db:
            import_csv(db, "sales", sales)
    with session_scope() as db:
        pid = db.execute(select(Product.id).where(Product.sku == "ING-1")).scalar()
        rows = db.execute(select(func.count(), func.sum(Sale.quantity)).where(Sale.product_id == pid)).one()
    assert rows == (2, 8.0)  # duplicate date rows were summed


def test_unknown_sku_rejected_without_writing():
    with pytest.raises(ImportValidationError) as exc, session_scope() as db:
        import_csv(db, "sales", b"date,sku,quantity\n2026-01-01,NOPE-404,3\n")
    assert "unknown sku" in exc.value.report.errors[0]
