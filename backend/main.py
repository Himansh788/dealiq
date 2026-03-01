from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import auth, deals, analysis, ai_rep, forecast, alerts, signals, trackers, coaching, activities, health
from routers.ask import router as ask_router
from routers.ask_demo import router as ask_demo_router
import uvicorn

app = FastAPI(
    title="DealIQ API",
    description="AI-powered deal clarity system for B2B SaaS revenue teams",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(deals.router, prefix="/deals", tags=["Deals"])
app.include_router(analysis.router, prefix="/analysis", tags=["Analysis"])
app.include_router(ai_rep.router, prefix="/ai-rep", tags=["AI Sales Rep"])
app.include_router(forecast.router, prefix="/forecast", tags=["Forecast"])
app.include_router(alerts.router, prefix="/alerts", tags=["Alerts"])
app.include_router(signals.router, prefix="/signals", tags=["Signal Detector"])
app.include_router(trackers.router, prefix="/trackers", tags=["Smart Trackers"])
app.include_router(coaching.router, prefix="/coaching", tags=["Coaching"])
app.include_router(activities.router, prefix="/activities", tags=["Activities"])
app.include_router(health.router, tags=["Health"])
app.include_router(ask_router)
app.include_router(ask_demo_router)


@app.on_event("startup")
async def startup_event():
    from database.init_db import create_tables
    await create_tables()


@app.get("/")
def root():
    return {"message": "DealIQ API is running", "version": "1.0.0"}

@app.get("/debug/env")
def debug_env():
    import os
    db_url = os.getenv("DATABASE_URL")
    return {"db_url_set": db_url is not None, "db_url_prefix": db_url[:30] if db_url else None}

@app.get("/debug/routes")
def debug_routes():
    routes = [{"path": r.path, "methods": r.methods} for r in app.routes]
    return routes    

@app.get("/health")
def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)