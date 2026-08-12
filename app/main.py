import threading
import logging
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from .database import get_session
from .services import (
    init_db,
    create_operation,
    submit_operation,
    get_operation,
    get_events,
    handle_receipt
)
from sqlalchemy.exc import IntegrityError
from .worker import Worker

app = FastAPI()


class CreateRequest(BaseModel):
    operationId: str
    amount: str
    currency: str
    description: Optional[str]


class Receipt(BaseModel):
    providerPaymentId: str
    operationId: str
    result: str
    message: Optional[str]
    occurredAt: Optional[str]


stop_event = threading.Event()
worker = None


@app.on_event("startup")
def startup():
    global worker
    init_db()
    logging.basicConfig(level=logging.INFO)
    stop_event.clear()
    worker = Worker(stop_event)
    worker.start()


@app.on_event("shutdown")
def shutdown():
    stop_event.set()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/operations", status_code=201)
def create_op(req: CreateRequest, db=Depends(get_session)):
    try:
        op = create_operation(
            db,
            req.operationId,
            req.amount,
            req.currency,
            req.description
        )
    except Exception as e:
        if isinstance(e, IntegrityError):
            raise HTTPException(status_code=409, detail="operation exists")
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "operationId": op.operation_id,
        "amount": op.amount,
        "currency": op.currency,
        "description": op.description,
        "status": op.status,
        "providerPaymentId": op.provider_payment_id,
    }


@app.post("/operations/{operation_id}/submit")
def submit(operation_id: str, db=Depends(get_session)):
    op = submit_operation(db, operation_id)
    if not op:
        raise HTTPException(status_code=404, detail="operation not found")
    code = status.HTTP_200_OK if op.status != "PROCESSING" else status.HTTP_202_ACCEPTED
    return JSONResponse(status_code=code, content={
        "operationId": op.operation_id,
        "status": op.status,
        "providerPaymentId": op.provider_payment_id,
    })


@app.post("/receipts", status_code=204)
def receipts(r: Receipt, db=Depends(get_session)):
    op, code = handle_receipt(
        db,
        r.providerPaymentId,
        r.operationId,
        r.result,
        r.message or "",
        r.occurredAt
    )
    if code == 404:
        raise HTTPException(status_code=404, detail="operation not found")
    if code == 409:
        raise HTTPException(status_code=409, detail="providerPaymentId mismatch")
    return None


@app.get("/operations/{operation_id}")
def get_op(operation_id: str, db=Depends(get_session)):
    op = get_operation(db, operation_id)
    if not op:
        raise HTTPException(status_code=404, detail="operation not found")
    return {
        "operationId": op.operation_id,
        "amount": op.amount,
        "currency": op.currency,
        "description": op.description,
        "status": op.status,
        "providerPaymentId": op.provider_payment_id,
    }


@app.get("/operations/{operation_id}/events")
def op_events(operation_id: str, db=Depends(get_session)):
    evs = get_events(db, operation_id)
    return [
        {
            "eventId": e.seq,
            "type": e.type,
            "fromStatus": e.from_status,
            "toStatus": e.to_status,
            "message": e.message,
            "occurredAt": e.occurred_at.isoformat() + "Z",
        }
        for e in evs
    ]
