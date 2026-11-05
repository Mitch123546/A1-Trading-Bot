import csv
import io
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.auth import (
    COOKIE_NAME,
    SESSION_SECONDS,
    create_session_token,
    require_owner,
    verify_password,
)
from app.config import get_settings
from app.database import Database
from app.models import ConfirmRequest, LoginRequest, TradingSettings
from app.trader import TradingEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

config = get_settings()
database = Database(config.database_path)
database.initialize()
engine = TradingEngine(config, database)
scheduler = BackgroundScheduler(timezone="UTC")


@asynccontextmanager
async def lifespan(_: FastAPI):
    scheduler.add_job(
        engine.scheduled_cycle,
        "interval",
        minutes=1,
        id="paper-trading-cycle",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.start()
    logger.info("A1 Trading Bot started in PAPER-ONLY mode")
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="A1 Trading Bot",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")
Owner = Annotated[str, Depends(require_owner)]


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "ok": True,
        "mode": "paper",
        "configured": config.credentials_configured and config.secure_configuration,
    }


@app.post("/api/login")
def login(payload: LoginRequest, response: Response) -> dict[str, bool]:
    if not config.secure_configuration:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Set a strong DASHBOARD_PASSWORD and SESSION_SECRET in .env",
        )
    if not verify_password(payload.password):
        raise HTTPException(status_code=401, detail="Incorrect password")
    response.set_cookie(
        COOKIE_NAME,
        create_session_token(),
        max_age=SESSION_SECONDS,
        httponly=True,
        samesite="strict",
        secure=False,
    )
    return {"ok": True}


@app.post("/api/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@app.get("/api/dashboard")
def dashboard(_: Owner) -> dict[str, object]:
    return engine.dashboard_snapshot()


@app.post("/api/control/test")
def test_connection(_: Owner) -> dict[str, object]:
    try:
        return engine.test_connection()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/control/start")
def start(_: Owner) -> dict[str, object]:
    try:
        return engine.start()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/control/pause")
def pause(_: Owner) -> dict[str, bool]:
    engine.pause()
    return {"ok": True}


@app.post("/api/control/emergency-stop")
def emergency_stop(_: Owner) -> dict[str, bool]:
    engine.emergency_stop()
    return {"ok": True}


@app.post("/api/control/resume")
def resume(payload: ConfirmRequest, _: Owner) -> dict[str, bool]:
    if payload.confirmation != "RESUME PAPER TRADING":
        raise HTTPException(status_code=400, detail="Confirmation phrase did not match")
    try:
        engine.resume_after_emergency()
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/control/run-now")
def run_now(_: Owner) -> dict[str, object]:
    try:
        return engine.run_cycle()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/settings")
def get_trading_settings(_: Owner) -> TradingSettings:
    return database.get_settings()


@app.put("/api/settings")
def update_trading_settings(payload: TradingSettings, _: Owner) -> TradingSettings:
    database.save_settings(payload)
    database.add_event("SETTINGS", "Trading and risk settings updated")
    return payload


@app.post("/api/backtest")
def backtest(_: Owner) -> dict[str, object]:
    try:
        return engine.backtest()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/reports/monthly.csv")
def monthly_report(_: Owner, month: str | None = None) -> Response:
    try:
        start = (
            datetime.strptime(month, "%Y-%m").replace(tzinfo=UTC)
            if month
            else datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Month must use YYYY-MM") from exc
    end = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    equity = database.rows_between("equity_snapshots", start.isoformat(), end.isoformat())
    events = database.rows_between("trade_events", start.isoformat(), end.isoformat())

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["A1 Trading Bot monthly paper report", start.strftime("%Y-%m")])
    writer.writerow(["Environment", "PAPER ONLY"])
    writer.writerow(["Starting virtual equity", equity[0]["virtual_equity"] if equity else ""])
    writer.writerow(["Ending virtual equity", equity[-1]["virtual_equity"] if equity else ""])
    writer.writerow(["Observation count", len(equity)])
    writer.writerow([])
    writer.writerow(
        ["Timestamp", "Event", "Symbol", "Side", "Quantity", "Notional", "Price", "Message"]
    )
    for event in events:
        writer.writerow(
            [
                event["created_at"],
                event["event_type"],
                event["symbol"],
                event["side"],
                event["quantity"],
                event["notional"],
                event["price"],
                event["message"],
            ]
        )
    return Response(
        output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="a1-paper-report-{start:%Y-%m}.csv"'
        },
    )
