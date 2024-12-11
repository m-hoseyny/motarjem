import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from telegram import Update
from telegram.ext import Application
from dotenv import load_dotenv
from models.database import get_db
from models.models import User
from sqlalchemy.orm import Session
from bot_handler import setup_handlers

# Load environment variables
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(env_path)
print(f"Loading .env from: {env_path}")

# Environment variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MAIN_BOT = os.getenv("MAIN_BOT")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
print(os.getenv("TELEGRAM_TOKEN"))
# Telegram bot application
application = Application.builder().token(TELEGRAM_TOKEN).build()

# Setup bot handlers
setup_handlers(application)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events handler for FastAPI"""
    # Startup event
    await application.initialize()
    await application.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
    
    yield
    
    # Shutdown event
    await application.shutdown()

# FastAPI app
app = FastAPI(lifespan=lifespan)

@app.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    """Handle incoming webhook requests from Telegram"""
    data = await request.json()
    update = Update.de_json(data=data, bot=application.bot)
    await application.process_update(update)
    return {"ok": True}

@app.get("/")
async def root():
    """Root endpoint"""
    return {"status": "running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, debug=True)
