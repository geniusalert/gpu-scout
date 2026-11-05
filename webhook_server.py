"""Maritime-compatible HTTP entry point for Telegram webhook delivery."""
import asyncio, json, os, logging, secrets
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException, Request
from telegram import Update
from telegram.ext import Application, MessageHandler, filters
import bot

application = None
log=logging.getLogger(__name__)

async def process_queued_updates():
    """Acknowledge webhooks quickly; preserve accepted work across restarts."""
    while True:
        db=bot.scout.db
        row=db.execute("SELECT update_id,payload FROM telegram_updates WHERE state='queued' ORDER BY update_id LIMIT 1").fetchone()
        if not row:
            await asyncio.sleep(0.25)
            continue
        update_id,payload=row
        db.execute("UPDATE telegram_updates SET state='processing' WHERE update_id=?",(update_id,));db.commit()
        try:
            await application.process_update(Update.de_json(json.loads(payload),application.bot))
        except asyncio.CancelledError:
            db.execute("UPDATE telegram_updates SET state='queued' WHERE update_id=?",(update_id,));db.commit()
            raise
        except Exception as error:
            log.error('Queued update failed (%s)',type(error).__name__)
            db.execute("UPDATE telegram_updates SET state='failed',payload='{}' WHERE update_id=?",(update_id,));db.commit()
        else:
            db.execute("UPDATE telegram_updates SET state='done',payload='{}' WHERE update_id=?",(update_id,));db.commit()

@asynccontextmanager
async def lifespan(app):
    global application
    token=os.environ['TELEGRAM_BOT_TOKEN']
    if not os.getenv('TELEGRAM_WEBHOOK_SECRET'):
        raise RuntimeError('TELEGRAM_WEBHOOK_SECRET must be configured')
    bot.scout=bot.Scout()
    bot.scout.db.execute("CREATE TABLE IF NOT EXISTS telegram_updates(update_id INTEGER PRIMARY KEY,payload TEXT NOT NULL,state TEXT NOT NULL)")
    bot.scout.db.execute("UPDATE telegram_updates SET state='queued' WHERE state='processing'")
    bot.scout.db.commit()
    application=Application.builder().token(token).build()
    application.add_handler(MessageHandler(filters.TEXT,bot.handle))
    application.add_error_handler(bot.on_error)
    await application.initialize()
    await application.start()
    worker=asyncio.create_task(process_queued_updates())
    try:
        yield
    finally:
        worker.cancel()
        try: await worker
        except asyncio.CancelledError: pass
        await application.stop()
        await application.shutdown()
        bot.scout.db.close()

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
    if not secrets.compare_digest(x_telegram_bot_api_secret_token or '',os.environ['TELEGRAM_WEBHOOK_SECRET']):
        raise HTTPException(403,'Invalid Telegram webhook secret')
    raw=await request.body()
    if len(raw)>1_000_000: raise HTTPException(413,'Update too large')
    try:
        payload=json.loads(raw)
        update_id=payload['update_id']
        if not isinstance(update_id,int):raise ValueError('Invalid update id')
    except (ValueError,KeyError,TypeError):raise HTTPException(400,'Invalid Telegram update')
    bot.scout.db.execute("INSERT OR IGNORE INTO telegram_updates VALUES(?,?,'queued')",(update_id,json.dumps(payload)))
    bot.scout.db.commit()
    return {'ok':True}

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='0.0.0.0',port=int(os.environ.get('PORT','8080')))
