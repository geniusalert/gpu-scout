import asyncio, json, os, re, secrets, time
from urllib.parse import quote
import httpx

async def lambda_search(c, request):
    data=await request('GET','https://cloud.lambda.ai/api/v1/instance-types',os.environ['LAMBDA_API_KEY'])
    out=[]
    tokens=c.gpu.upper().replace('_',' ').split()
    for item in data['data'].values():
        t=item['instance_type']; n=t['specs']['gpus']; price=t['price_cents_per_hour']/100
        if n!=c.count or not all(x in t['gpu_description'].upper() for x in tokens) or not 0<price/n<=c.max_price: continue
        for region in item['regions_with_capacity_available']:
            if c.region and not region['name'].lower().startswith(c.region.lower()+'-'): continue
            out.append(dict(id=t['name']+':'+region['name'],gpu_name=t['gpu_description'],num_gpus=n,dph_total=price,geolocation=region['name'],provider='Lambda',url='https://cloud.lambda.ai/instances'))
    return out

class Outreach:
    def __init__(self, db, request):
        self.db=db; self.request=request
        db.execute('CREATE TABLE IF NOT EXISTS inquiries(id TEXT PRIMARY KEY, owner INTEGER, task INTEGER, recipient TEXT, subject TEXT, body TEXT, created REAL, state TEXT, thread TEXT)')
        db.commit()
    def draft(self,owner,task,recipient,body):
        if not re.fullmatch(r'[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',recipient): raise ValueError('Provide one supplier email address.')
        token=secrets.token_hex(8)
        subject=f'GPU capacity inquiry — Scout task {task}'
        self.db.execute('INSERT INTO inquiries VALUES(?,?,?,?,?,?,?, ?,?)',(token,owner,task,recipient,subject,body,time.time(),'draft',''))
        self.db.commit()
        return f'DRAFT {token}\nTo: {recipient}\nSubject: {subject}\n\n{body}\n\nSend exactly this email: /approve {token}\nCancel: /cancel {token}\nApproval expires in 30 minutes.'
    async def approve(self,owner,token,demo):
        row=self.db.execute('SELECT recipient,subject,body,created FROM inquiries WHERE id=? AND owner=? AND state="draft"',(token,owner)).fetchone()
        if not row: raise ValueError('Draft not found or already processed.')
        if time.time()-row[3]>1800: raise ValueError('Approval expired. Create a new draft.')
        if demo: raise ValueError('Sending disabled in demo mode.')
        key=os.environ['AGENTMAIL_API_KEY']; inbox=os.environ['AGENTMAIL_INBOX_ID']
        # Claim before network I/O. Ambiguous failures are never retried automatically.
        changed=self.db.execute('UPDATE inquiries SET state="sending" WHERE id=? AND state="draft"',(token,)).rowcount
        self.db.commit()
        if not changed: raise ValueError('Already processed.')
        try:
            sent=await self.request('POST',f'https://api.agentmail.to/inboxes/{quote(inbox,safe="")}/messages/send',key,json={'to':[row[0]],'subject':row[1],'text':row[2]})
        except Exception:
            self.db.execute('UPDATE inquiries SET state="unknown" WHERE id=?',(token,));self.db.commit()
            raise ValueError('Delivery outcome unknown. Check AgentMail before creating another draft; no automatic retry.')
        self.db.execute('UPDATE inquiries SET state="sent",thread=? WHERE id=?',(sent['thread_id'],token));self.db.commit()
        return 'Inquiry sent. Reference: '+token
