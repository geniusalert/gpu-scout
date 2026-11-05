"""Google discovery and evidence-backed supplier inquiries."""
import asyncio, ipaddress, json, os, re, socket, time
from html.parser import HTMLParser
from urllib.parse import urlsplit, urljoin
import httpx

class Page(HTMLParser):
    def __init__(self):
        super().__init__(); self.text=[]; self.links=[]; self.hidden=0
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style'): self.hidden+=1
        if tag=='a': self.links.extend(v for k,v in attrs if k=='href')
    def handle_endtag(self, tag):
        if tag in ('script','style'): self.hidden=max(0,self.hidden-1)
    def handle_data(self, data):
        if not self.hidden: self.text.append(data)

async def fetch_page(url):
    for _ in range(4):
        p=urlsplit(url)
        if p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in (None,443):
            raise ValueError('Only public HTTPS pages supported')
        addresses=await asyncio.to_thread(socket.getaddrinfo,p.hostname,443,type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError('Non-public host blocked')
        async with httpx.AsyncClient(timeout=20,trust_env=False) as client:
            async with client.stream('GET',url,follow_redirects=False) as r:
                if r.is_redirect:
                    url=urljoin(url,r.headers['location']); continue
                r.raise_for_status()
                if 'text/html' not in r.headers.get('content-type',''): raise ValueError('Not HTML')
                chunks=[]; size=0
                async for chunk in r.aiter_bytes():
                    size+=len(chunk)
                    if size>1000000: raise ValueError('Page too large')
                    chunks.append(chunk)
        page=Page(); page.feed(b''.join(chunks).decode('utf-8',errors='replace'))
        return url,page
    raise ValueError('Too many redirects')

async def google(query):
    async with httpx.AsyncClient(timeout=40) as client:
        r=await client.get('https://serpapi.com/search',params={'engine':'google','q':query,'num':10,'api_key':os.environ['SERPAPI_API_KEY']})
        r.raise_for_status(); data=r.json()
        if data.get('error'): raise ValueError('Google search service failed')
        return data.get('organic_results',[])

class Research:
    def __init__(self,db):
        self.db=db
        db.execute('CREATE TABLE IF NOT EXISTS research(task INTEGER PRIMARY KEY, owner INTEGER, report TEXT)'); db.commit()
    async def run(self,task,owner,c):
        gpu=c.gpu.replace('_',' ')
        queries=[f'{gpu} GPU cloud rental {c.region} pricing',f'{c.count} {gpu} GPU dedicated cluster {c.region} {c.duration}',f'{gpu} GPU rental provider sales contact quote {c.region}']
        found={}; coverage=[]
        for query in queries:
            try:
                results=await google(query); coverage.append({'query':query,'status':f'searched: {len(results)} results'})
                for r in results:
                    host=urlsplit(r.get('link','')).hostname
                    if host and r['link'].startswith('https://'): found.setdefault(host,r)
            except Exception: coverage.append({'query':query,'status':'unavailable'})
        suppliers=[]
        for host,r in list(found.items())[:10]:
            item={'name':r.get('title',host),'domain':host,'sources':[],'emails':[],'pricing_evidence':[],'status':'unverified lead','checked_at':time.time()}
            try:
                url,page=await fetch_page(r['link'])
                if urlsplit(url).hostname!=host: raise ValueError('Domain changed')
                pages=[(url,page)]; links=[]
                for link in page.links:
                    target=urljoin(url,link)
                    if urlsplit(target).hostname==host and re.search('contact|pricing|sales',urlsplit(target).path,re.I) and target not in links: links.append(target)
                for target in links[:2]:
                    try:
                        final,p=await fetch_page(target)
                        if urlsplit(final).hostname==host: pages.append((final,p))
                    except Exception: pass
                for source,p in pages:
                    text=' '.join(' '.join(p.text).split())
                    item['sources'].append({'url':source,'excerpt':text[:1800]})
                    candidates=re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',text+' '+' '.join(p.links))
                    for email in candidates:
                        email=email.strip('.')
                        if email.split('@')[1].lower() in (host,host.removeprefix('www.')) and re.match(r'^(sales|contact|info|hello|support|business|partnerships)@',email,re.I):
                            evidence={'email':email,'source':source}
                            if evidence not in item['emails']: item['emails'].append(evidence)
                    for match in re.finditer(r'\$\s*\d+(?:\.\d+)?',text):
                        if len(item['pricing_evidence'])>=5: break
                        item['pricing_evidence'].append({'text':text[max(0,match.start()-90):match.end()+140],'source':source})
                item['gpu_mentioned']=gpu.split()[0].upper() in ' '.join(x['excerpt'] for x in item['sources']).upper()
            except Exception: item['status']='page unavailable; search lead only'
            suppliers.append(item)
        suppliers.sort(key=lambda x:(not x.get('gpu_mentioned',False),not bool(x['emails'])))
        report={'queries':coverage,'suppliers':suppliers,'created':time.time(),'note':'Web prices are excerpts, not comparable verified offers. Confirm capacity, region, topology and terms.'}
        self.db.execute('INSERT OR REPLACE INTO research VALUES(?,?,?)',(task,owner,json.dumps(report))); self.db.commit()
        return report
    def get(self,task,owner):
        row=self.db.execute('SELECT report FROM research WHERE task=? AND owner=?',(task,owner)).fetchone()
        if not row: raise ValueError('No research for this task. Run /research first.')
        return json.loads(row[0])
    def draft_body(self,task,owner,index,c):
        suppliers=self.get(task,owner)['suppliers']
        if not 1<=index<=len(suppliers): raise ValueError('Choose a supplier number from the report.')
        item=suppliers[index-1]
        if not item['emails']: raise ValueError('No published business email found. Review the contact page or use /quote with a verified address.')
        email=item['emails'][0]
        body=f"Hello {item['domain']} sales team,\n\nI am contacting you on behalf of a GPU Scout user evaluating GPU rental capacity. We found your service at {item['sources'][0]['url']}.\n\nPlease quote:\nGPU model: {c.gpu}\nQuantity: {c.count}\nRegion: {c.region or 'please list available regions'}\nDuration: {c.duration}\nTarget: USD {c.max_price}/GPU-hour\nNetworking: {c.networking}\n\nPlease confirm current capacity, earliest start date, single-node versus multi-node layout, interconnect/topology, all-in pricing including storage/networking/setup, minimum commitment, SLA, cancellation terms and quote validity. Clearly identify any alternative configurations.\n\nThis is an inquiry only, not an order or authorization to provision resources.\nThank you,\nGPU Scout, on behalf of the requesting user"
        return email['email'],body,email['source']

def summaries(report):
    yield 'Google supplier research\n'+report['note']+'\n'+'\n'.join(q['status']+': '+q['query'] for q in report['queries'])
    for i,s in enumerate(report['suppliers'],1):
        yield f"Supplier {i}: {s['name']}\n{s['status']} | GPU mentioned: {s.get('gpu_mentioned',False)}\n"+'\n'.join('Source: '+x['url'] for x in s['sources'])+'\nPublished business contacts: '+(', '.join(x['email'] for x in s['emails']) or 'none found')+'\nPrice excerpts (unverified):\n'+'\n'.join(x['text']+'\n'+x['source'] for x in s['pricing_evidence'])
