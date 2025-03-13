from fastapi import FastAPI
import uvicorn
from fastapi.middleware.cors import CORSMiddleware

# Import routers
from app.api.routes.upload import router as upload_router
from app.api.routes.chatbot import router as chat_router
from app.api.routes.delete import router as delete_router

app = FastAPI()

# CORS middleware (adjust origins for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change this to the frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include different routers for modularity
app.include_router(upload_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(delete_router, prefix="/api")

@app.get("/")
def home():
    return {"message": "Welcome to the TelepracticePro Multi-Tenant Chatbot built on FastAPI"}

# Run the app
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
