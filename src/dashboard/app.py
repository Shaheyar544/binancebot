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
        html_content = (
            "<!DOCTYPE html>\n"
            "<html lang='en'>\n"
            "<head>\n"
            "    <meta charset='UTF-8'>\n"
            "    <title>XAUUSDT Long-Only Observability Dashboard</title>\n"
            "    <style>\n"
            "        body { font-family: -apple-system, sans-serif; background: #0f172a; "
            "color: #f8fafc; margin: 0; padding: 24px; }\n"
            "        .container { max-width: 1000px; margin: 0 auto; }\n"
            "        .card { background: #1e293b; border-radius: 12px; padding: 20px; "
            "margin-bottom: 20px; border: 1px solid #334155; }\n"
            "        .grid { display: grid; grid-template-columns: repeat(auto-fit, "
            "minmax(200px, 1fr)); gap: 16px; }\n"
            "        .stat-label { font-size: 0.85rem; color: #94a3b8; }\n"
            "        .stat-value { font-size: 1.4rem; font-weight: 700; color: #38bdf8; }\n"
            "        .badge-enabled { display: inline-block; padding: 4px 10px; "
            "border-radius: 9999px; background: #16a34a; color: white; font-weight: 600; }\n"
            "        table { width: 100%; border-collapse: collapse; margin-top: 12px; }\n"
            "        th, td { text-align: left; padding: 8px; border-bottom: 1px solid #334155; }\n"
            "    </style>\n"
            "</head>\n"
            "<body>\n"
            "    <div class='container'>\n"
            "        <h1 style='display:flex; justify-content:space-between;'>\n"
            "            <span>⚡ XAUUSDT Adaptive Bot Dashboard</span>\n"
            "            <span id='live-badge' class='badge-disabled'>CHECKING...</span>\n"
            "        </h1>\n"
            "        <div class='card'>\n"
            "            <h2>Market Overview</h2>\n"
            "            <div class='grid'>\n"
            "                <div><div class='stat-label'>Instrument</div>"
            "<div class='stat-value' id='sym'>XAUUSDT</div></div>\n"
            "                <div><div class='stat-label'>Last Price</div>"
            "<div class='stat-value' id='last-price'>--</div></div>\n"
            "                <div><div class='stat-label'>Mark Price</div>"
            "<div class='stat-value' id='mark-price'>--</div></div>\n"
            "                <div><div class='stat-label'>Market Regime</div>"
            "<div class='stat-value' id='regime' style='color:#eab308;'>--</div></div>\n"
            "            </div>\n"
            "        </div>\n"
            "        <div class='card'>\n"
            "            <h2>System Health & Invariants</h2>\n"
            "            <div class='grid'>\n"
            "                <div><div class='stat-label'>Data Feed</div>"
            "<div class='stat-value' id='data-health' style='color:#16a34a;'>HEALTHY</div></div>\n"
            "                <div><div class='stat-label'>News Lock</div>"
            "<div class='stat-value' id='news-lock'>CLEAR</div></div>\n"
            "                <div><div class='stat-label'>DCA Ceiling</div>"
            "<div class='stat-value'>$500.00 Max</div></div>\n"
            "                <div><div class='stat-label'>Direction</div>"
            "<div class='stat-value' style='color:#16a34a;'>LONG ONLY</div></div>\n"
            "            </div>\n"
            "        </div>\n"
            "        <div class='card'>\n"
            "            <h2>Recent Decisions Audit Trail</h2>\n"
            "            <table>\n"
            "                <thead><tr><th>ID</th><th>State</th><th>Regime</th>"
            "<th>Reason</th></tr></thead>\n"
            "                <tbody id='decisions-tbody'><tr><td colspan='4'>"
            "Loading...</td></tr></tbody>\n"
            "            </table>\n"
            "        </div>\n"
            "    </div>\n"
            "    <script>\n"
            "        async function refresh() {\n"
            "            try {\n"
            "                const [healthRes, overRes, decRes] = await Promise.all([\n"
            "                    fetch('/health').then(r => r.json()),\n"
            "                    fetch('/api/overview').then(r => r.json()),\n"
            "                    fetch('/api/decisions').then(r => r.json())\n"
            "                ]);\n"
            "                document.getElementById('last-price').textContent = "
            "'$' + overRes.last_price;\n"
            "                document.getElementById('mark-price').textContent = "
            "'$' + overRes.mark_price;\n"
            "                document.getElementById('regime').textContent = overRes.regime;\n"
            "                document.getElementById('data-health').textContent = "
            "healthRes.data_health;\n"
            "                document.getElementById('news-lock').textContent = "
            "healthRes.news_lock_state;\n"
            "                const badge = document.getElementById('live-badge');\n"
            "                if (healthRes.live_trading_enabled) {\n"
            "                    badge.textContent = 'DEMO LIVE: ENABLED';\n"
            "                    badge.style.background = '#16a34a';\n"
            "                } else {\n"
            "                    badge.textContent = 'LIVE TRADING: DISABLED';\n"
            "                    badge.style.background = '#ea580c';\n"
            "                }\n"
            "                const tbody = document.getElementById('decisions-tbody');\n"
            "                tbody.innerHTML = '';\n"
            "                decRes.slice(0, 10).forEach(d => {\n"
            "                    const row = document.createElement('tr');\n"
            "                    row.innerHTML = `<td><code>${d.decision_id}</code></td>"
            "<td><strong>${d.decision_state}</strong></td><td>${d.regime}</td>"
            "<td>${d.reason}</td>`;\n"
            "                    tbody.appendChild(row);\n"
            "                });\n"
            "            } catch (err) { console.error(err); }\n"
            "        }\n"
            "        refresh();\n"
            "        setInterval(refresh, 5000);\n"
            "    </script>\n"
            "</body>\n"
            "</html>"
        )
        return HTMLResponse(content=html_content)

    @app.get("/api/overview", response_model=OverviewResponse, tags=["Overview"])
    async def get_overview() -> OverviewResponse:
        """Current market price, mark/index prices, funding, and classified regime."""
        return service.get_overview()

    @app.get("/api/decisions", response_model=list[DecisionSummaryResponse], tags=["Decisions"])
    async def get_decisions(limit: int = 50) -> list[DecisionSummaryResponse]:
        """Historical immutable decision audit trail."""
        return await service.get_recent_decisions(limit=limit)

    return app
