"""FastAPI application factory for the read-only monitoring dashboard."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from src.dashboard.models import DecisionSummaryResponse, HealthResponse, OverviewResponse
from src.dashboard.service import DashboardStateService


def create_dashboard_app(service: DashboardStateService) -> FastAPI:
    """Create a configured, strictly read-only FastAPI dashboard app."""
    app = FastAPI(
        title="XAUUSDT Long-Only Bot Observability API",
        version="0.1.0",
        description="Read-only monitoring dashboard for engine health, regime, and risk.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthResponse, tags=["Health"])
    async def get_health() -> HealthResponse:
        """System health, data health, and execution gate state."""
        return service.get_health()

    @app.get("/", tags=["Dashboard"])
    async def get_dashboard_html() -> HTMLResponse:
        """Serve real-time browser monitoring dashboard."""
        from pathlib import Path

        template_path = Path(__file__).parent / "templates" / "index.html"
        if template_path.exists():
            content = template_path.read_text(encoding="utf-8")
        else:
            content = "<h1>Dashboard template not found</h1>"
        return HTMLResponse(content=content)

    @app.get("/api/overview", response_model=OverviewResponse, tags=["Overview"])
    async def get_overview() -> OverviewResponse:
        """Current market price, mark/index prices, funding, and classified regime."""
        return service.get_overview()

    @app.get("/api/decisions", response_model=list[DecisionSummaryResponse], tags=["Decisions"])
    async def get_decisions(limit: int = 50) -> list[DecisionSummaryResponse]:
        """Historical immutable decision audit trail."""
        return await service.get_recent_decisions(limit=limit)

    return app
