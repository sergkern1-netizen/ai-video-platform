from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db
from backend.routers.videos import router as videos_router
from backend.routers.youtube import router as youtube_router

app = FastAPI(title="AI Video Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    init_db()

app.include_router(videos_router, prefix="/videos")
app.include_router(youtube_router, prefix="/youtube")
