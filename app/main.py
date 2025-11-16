from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
import os
from pathlib import Path
import aiofiles
from sqlalchemy.orm import Session
from datetime import datetime
from app.pdf_processor import PDFProcessor
from app.data_extractor import InvoiceDataExtractor
from app.database import Invoice, UserSettings, init_db, get_db
from app.stats import StatisticsService
from app.excel_export import ExcelExporter

app = FastAPI(title="Invoice Processing API", version="1.0.0")

Path("uploads").mkdir(exist_ok=True)
Path("data").mkdir(exist_ok=True)

init_db()

pdf_processor = PDFProcessor()
data_extractor = InvoiceDataExtractor()


class ProcessingResponse(BaseModel):
    success: bool
    data: dict
    message: str = ""


@app.get("/")
async def root():
    return {"message": "Invoice Processing API", "status": "running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


class ProcessInvoiceRequest(BaseModel):
    user_id: int
    user_name: str = None


@app.post("/process-invoice")
async def process_invoice(
    file: UploadFile = File(...),
    user_id: int = None,
    user_name: str = None,
    db: Session = Depends(get_db)
):
    """
    Обрабатывает загруженный PDF-файл счета и возвращает структурированные данные
    """
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Файл должен быть в формате PDF")
    
    file_path = f"uploads/{file.filename}"
    async with aiofiles.open(file_path, 'wb') as out_file:
        content = await file.read()
        await out_file.write(content)
    
    try:
        text = pdf_processor.extract_text(file_path)
        tables = pdf_processor.extract_tables(file_path)
        
        if not text:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "data": {},
                    "message": "Не удалось извлечь текст из PDF"
                }
            )
        
        structured_data = data_extractor.extract_invoice_data(text, tables=tables, pdf_path=file_path)
        
        if user_id:
            invoice = Invoice(
                user_id=user_id,
                user_name=user_name,
                file_name=file.filename,
                invoice_number=structured_data.get('invoice_number'),
                date=structured_data.get('date'),
                seller=structured_data.get('seller'),
                buyer=structured_data.get('buyer'),
                total_amount=structured_data.get('total_amount'),
                currency=structured_data.get('currency', 'RUB'),
                extracted_data=structured_data,
                processed_at=datetime.utcnow()
            )
            db.add(invoice)
            db.commit()
            db.refresh(invoice)
            structured_data['invoice_id'] = invoice.id
        
        return JSONResponse(
            content={
                "success": True,
                "data": structured_data,
                "message": "Данные успешно извлечены"
            }
        )
    
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "data": {},
                "message": f"Ошибка обработки: {str(e)}"
            }
        )
    
    finally:
        # Clean up uploaded file
        if os.path.exists(file_path):
            os.remove(file_path)


@app.post("/process-image")
async def process_image(
    file: UploadFile = File(...),
    user_id: int = None,
    user_name: str = None,
    db: Session = Depends(get_db)
):
    """
    Обработка изображений (JPG, PNG) с помощью OCR
    """
    allowed_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']
    file_ext = os.path.splitext(file.filename.lower())[1]
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400, 
            detail=f"Файл должен быть изображением. Поддерживаемые форматы: {', '.join(allowed_extensions)}"
        )
    
    file_path = f"uploads/{file.filename}"
    async with aiofiles.open(file_path, 'wb') as out_file:
        content = await file.read()
        await out_file.write(content)
    
    try:
        print(f"Обрабатываю изображение: {file.filename}")
        text = pdf_processor.extract_text_from_image(file_path)
        
        if not text or len(text.strip()) < 10:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "data": {},
                    "message": "Не удалось извлечь текст из изображения. Убедитесь, что изображение четкое и содержит текст."
                }
            )
        
        structured_data = data_extractor.extract_invoice_data(text, tables=[], pdf_path=file_path)
        
        if user_id:
            invoice = Invoice(
                user_id=user_id,
                user_name=user_name,
                file_name=file.filename,
                invoice_number=structured_data.get('invoice_number'),
                date=structured_data.get('date'),
                seller=structured_data.get('seller'),
                buyer=structured_data.get('buyer'),
                total_amount=structured_data.get('total_amount'),
                currency=structured_data.get('currency', 'RUB'),
                extracted_data=structured_data,
                processed_at=datetime.utcnow()
            )
            db.add(invoice)
            db.commit()
            db.refresh(invoice)
            structured_data['invoice_id'] = invoice.id
        
        return JSONResponse(
            content={
                "success": True,
                "data": structured_data,
                "message": "Данные успешно извлечены из изображения"
            }
        )
    
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "data": {},
                "message": f"Ошибка обработки изображения: {str(e)}"
            }
        )
    
    finally:
        # Clean up uploaded file
        if os.path.exists(file_path):
            os.remove(file_path)


@app.get("/history/{user_id}")
async def get_history(user_id: int, limit: int = 10, db: Session = Depends(get_db)):
    invoices = StatisticsService.get_recent_invoices(db, user_id, limit)
    return JSONResponse(content={"success": True, "data": invoices})


@app.get("/invoice/{invoice_id}/json")
async def get_invoice_json(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Счет не найден")
    
    return JSONResponse(content={
        "success": True,
        "data": invoice.extracted_data,
        "invoice_id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "created_at": invoice.created_at.isoformat()
    })


@app.get("/stats/{user_id}")
async def get_stats(user_id: int, days: int = 30, db: Session = Depends(get_db)):
    stats = StatisticsService.get_user_stats(db, user_id, days)
    return JSONResponse(content={"success": True, "data": stats})


@app.get("/export/excel/{user_id}")
async def export_to_excel(user_id: int, db: Session = Depends(get_db)):
    excel_file = ExcelExporter.export_invoices(db, user_id)
    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=invoices_{user_id}_{datetime.now().strftime('%Y%m%d')}.xlsx"}
    )


@app.get("/export/stats/{user_id}")
async def export_stats_to_excel(user_id: int, days: int = 30, db: Session = Depends(get_db)):
    stats = StatisticsService.get_user_stats(db, user_id, days)
    excel_file = ExcelExporter.export_statistics(db, user_id, stats)
    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=stats_{user_id}_{datetime.now().strftime('%Y%m%d')}.xlsx"}
    )


@app.get("/notifications/pending/{user_id}")
async def get_pending_notifications(user_id: int, days: int = 7, db: Session = Depends(get_db)):
    from app.notifications import NotificationService
    pending = NotificationService.get_pending_invoices(db, user_id, days)
    return JSONResponse(content={"success": True, "data": pending})


@app.get("/settings/{user_id}")
async def get_user_settings(user_id: int, db: Session = Depends(get_db)):
    from app.notifications import NotificationService
    settings = NotificationService.get_user_settings(db, user_id)
    return JSONResponse(content={
        "success": True,
        "data": {
            "notifications_enabled": settings.notifications_enabled,
            "notification_time": settings.notification_time,
            "language": settings.language
        }
    })


@app.post("/settings/notifications/{user_id}/toggle")
async def toggle_notifications(user_id: int, db: Session = Depends(get_db)):
    from app.notifications import NotificationService
    enabled = NotificationService.toggle_notifications(db, user_id)
    return JSONResponse(content={"success": True, "enabled": enabled})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

