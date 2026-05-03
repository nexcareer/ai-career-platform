from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine
from models import Base
from routes.auth_routes import router as auth_router
from routes.cv_routes import router as cv_router
from routes.student_routes import router as student_router
from routes.professional_routes import router as professional_router
from routes.employer_routes import router as employer_router
from routes.job_routes import router as job_router

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="NexCareer API",
    description="AI Career Intelligence Platform",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(cv_router)
app.include_router(student_router)
app.include_router(professional_router)
app.include_router(employer_router)
app.include_router(job_router)


@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "app": "NexCareer API", "version": "2.0.0", "docs": "/docs"}


@app.get("/health", tags=["Health"])
def health():
    from datetime import datetime
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
