"""Register or inspect the Telegram webhook after a hosted deployment is live."""
import argparse, os
import httpx
from dotenv import load_dotenv

load_dotenv()
parser=argparse.ArgumentParser()
parser.add_argument('url',help='Public HTTPS base URL of the hosted bot')
args=parser.parse_args()
base=args.url.rstrip('/')
if not base.startswith('https://'): raise SystemExit('A public HTTPS URL is required')
token=os.environ['TELEGRAM_BOT_TOKEN']
secret=os.environ['TELEGRAM_WEBHOOK_SECRET']
if not secret or not all(c.isalnum() or c in '_-' for c in secret):
    raise SystemExit('Set TELEGRAM_WEBHOOK_SECRET to a random value containing letters, digits, underscore or hyphen')
response=httpx.post(f'https://api.telegram.org/bot{token}/setWebhook',json={'url':base+'/telegram','secret_token':secret,'drop_pending_updates':False},timeout=20)
response.raise_for_status()
data=response.json()
if not data.get('ok'):raise SystemExit('Telegram rejected the webhook registration')
print('Telegram webhook registered at '+base+'/telegram')
