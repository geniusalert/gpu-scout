"""Maritime-compatible HTTP entry point for Telegram webhook delivery."""
import json, os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException, Request
from telegram import Update
from telegram.ext import Application, MessageHandler, filters
import bot

application = None

@asynccontextmanager
async def lifespan(app):
    global application
    token=os.environ['TELEGRAM_BOT_TOKEN']
    if not os.getenv('TELEGRAM_WEBHOOK_SECRET'):
        raise RuntimeError('TELEGRAM_WEBHOOK_SECRET must be configured')
    bot.scout=bot.Scout()
    application=Application.builder().token(token).build()
    application.add_handler(MessageHandler(filters.TEXT,bot.handle))
    application.add_error_handler(bot.on_error)
    await application.initialize()
    await application.start()
    try:
        yield
    finally:
        await application.stop()
        await application.shutdown()

app=FastAPI(lifespan=lifespan)

@app.get('/health')
async def health():
    return {'ok': True}

@app.post('/chat')
async def chat(request: Request):
    # Maritime's chat contract; Telegram delivery uses the authenticated webhook.
    return {'response':'GPU Scout is available through its Telegram bot.'}

@app.post('/telegram')
async def telegram(request: Request, x_telegram_bot_api_secret_token: str | None = Header(default=None)):
    if x_telegram_bot_api_secret_token != os.environ['TELEGRAM_WEBHOOK_SECRET']:
        raise HTTPException(403,'Invalid Telegram webhook secret')
    raw=await request.body()
    if len(raw)>1_000_000: raise HTTPException(413,'Update too large')
    update=Update.de_json(json.loads(raw),application.bot)
    await application.process_update(update)
    return {'ok':True}

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='0.0.0.0',port=int(os.environ.get('PORT','8080')))
