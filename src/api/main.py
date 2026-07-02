from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes.jobs import router as jobs_router
from src.api.routes.meta import router as meta_router

app = FastAPI(title="Diffpype API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs_router)
app.include_router(meta_router)
