"""Data management: CSV import, templates, demo dataset."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import jobs
from app.db import get_db
from app.models import Product, Sale, StockSnapshot
from app.schemas import SeedIn
from app.services.demo import load_demo
from app.services.ingest import SCHEMAS, ImportValidationError, import_csv

router = APIRouter(tags=["data"])
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

TEMPLATES = {
    "products": "sku,name,category,unit_cost,unit_price,lead_time_days,lead_time_std_days,order_cost,holding_rate,moq\n"
    "SKU-1000,Classic Chef Knife,Kitchen,12.50,29.99,7,1.5,60,0.25,6\n",
    "sales": "date,sku,quantity\n2026-01-01,SKU-1000,4\n2026-01-02,SKU-1000,2\n",
    "stock": "date,sku,on_hand,on_order\n2026-01-31,SKU-1000,35,0\n",
}


@router.get("/data/status")
def data_status(db: Session = Depends(get_db)):
    products = db.execute(select(func.count()).select_from(Product)).scalar()
    sales_rows, first, last = db.execute(select(func.count(), func.min(Sale.date), func.max(Sale.date))).one()
    stock_date = db.execute(select(func.max(StockSnapshot.date))).scalar()
    return {
        "products": products,
        "sales_rows": sales_rows,
        "first_sale": first,
        "last_sale": last,
        "stock_as_of": stock_date,
        "schemas": SCHEMAS,
    }


@router.get("/imports/templates/{kind}", response_class=PlainTextResponse)
def template(kind: str):
    if kind not in TEMPLATES:
        raise HTTPException(404, "Unknown template")
    return PlainTextResponse(
        TEMPLATES[kind],
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{kind}_template.csv"'},
    )


@router.post("/imports/{kind}")
async def upload(kind: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    if kind not in SCHEMAS:
        raise HTTPException(404, "Unknown import kind. Use products, sales or stock.")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large (max 20 MB)")
    try:
        report = import_csv(db, kind, content)  # type: ignore[arg-type]
        db.commit()
    except ImportValidationError as exc:
        db.rollback()
        raise HTTPException(
            422, {"message": "Validation failed", "errors": exc.report.errors, "rows": exc.report.rows}
        ) from exc
    return {"kind": kind, "rows": report.rows, "inserted": report.inserted, "updated": report.updated}


@router.post("/demo/seed")
def seed_demo(body: SeedIn | None = None, db: Session = Depends(get_db)):
    body = body or SeedIn()
    counts = load_demo(db, skus=body.skus, days=body.days, seed=body.seed)
    db.commit()
    job_id = jobs.submit("pipeline", trigger="manual")
    return {"loaded": counts, "job_id": job_id}
