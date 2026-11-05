"""Google discovery and evidence-backed supplier inquiries."""
import asyncio, ipaddress, json, os, re, socket, time, logging
from html.parser import HTMLParser
from urllib.parse import urlsplit, urljoin
import httpx
from supplier_data import candidates as supplier_candidates

log=logging.getLogger(__name__)

def search_configured():
    return bool(os.getenv('SERPER_API_KEY') or os.getenv('SERPAPI_API_KEY'))

def hit_score(result, criteria):
    """Exclude general GPU explainers; prefer rental providers over comparisons."""
    title=result.get('title','')
    link=result.get('link','')
    text=(title+' '+result.get('snippet','')+' '+link).lower()
    model=criteria.gpu.replace('_',' ').split()[0].lower()
    if not re.search(r'\b'+re.escape(model)+r'\b',text): return None
    if not re.search(r'rent|cloud|pric|\bhour|dedicated|cluster|quote|compute',text): return None
    if any(x in link.lower() for x in ('wikipedia.org/','youtube.com/','reddit.com/','/what-is/','/think/topics/')): return None
    comparison=bool(re.search(r'comparison|compare|across providers|\bguide\b|/blog/|/kb/',text))
    full_variant=all(token.lower() in text for token in criteria.gpu.replace('_',' ').split())
    return (comparison,not full_variant)

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
        if os.getenv('SERPER_API_KEY'):
            r=await client.post('https://google.serper.dev/search',headers={'X-API-KEY':os.environ['SERPER_API_KEY']},json={'q':query,'num':10})
            field='organic'
        else:
            r=await client.get('https://serpapi.com/search',params={'engine':'google','q':query,'num':10,'api_key':os.environ['SERPAPI_API_KEY']})
            field='organic_results'
        r.raise_for_status(); data=r.json()
        if data.get('error'): raise ValueError('Google search service failed')
        return data.get(field,[])

class Research:
    def __init__(self,db):
        self.db=db
        db.execute('CREATE TABLE IF NOT EXISTS research(task INTEGER PRIMARY KEY, owner INTEGER, report TEXT)'); db.commit()
    async def run(self,task,owner,c,deep=True):
        gpu=c.gpu.replace('_',' ')
        model=' '.join('"'+part+'"' for part in gpu.split())
        queries=[f'{model} GPU cloud rental {c.region} pricing',f'{model} {c.count} GPU dedicated cluster rental {c.region}',f'{model} GPU cloud provider rental sales contact quote {c.region}']
        found={}; coverage=[]
        results_by_query=await asyncio.gather(*(google(q) for q in queries),return_exceptions=True)
        for query,results in zip(queries,results_by_query):
            if isinstance(results,BaseException):
                coverage.append({'query':query,'status':'unavailable'})
                log.warning('Google search failed (%s)',type(results).__name__)
                continue
            coverage.append({'query':query,'status':f'searched: {len(results)} results'})
            for r in results:
                host=urlsplit(r.get('link','')).hostname
                score=hit_score(r,c)
                if host and r['link'].startswith('https://') and score is not None:
                    key=host.removeprefix('www.')
                    if key not in found or score<hit_score(found[key],c): found[key]=r
        found=dict(sorted(found.items(),key=lambda pair:hit_score(pair[1],c)))
        suppliers=[]
        for normalized_host,r in list(found.items())[:10]:
            host=urlsplit(r['link']).hostname
            snippet=r.get('snippet','')
            item={'name':r.get('title',host),'domain':host,'sources':[{'url':r['link'],'excerpt':snippet}],'emails':[],'pricing_evidence':[],'status':'Google result; capacity and terms need confirmation','source_type':'web','checked_at':time.time()}
            item['source_kind']='comparison' if hit_score(r,c)[0] else 'supplier lead'
            item['gpu_mentioned']=gpu.split()[0].upper() in (item['name']+' '+snippet).upper()
            for match in re.finditer(r'\$\s*\d+(?:\.\d+)?',snippet):
                item['pricing_evidence'].append({'text':snippet[max(0,match.start()-90):match.end()+140],'source':r['link']})
            if not deep:
                suppliers.append(item)
                continue
            try:
                url,page=await asyncio.wait_for(fetch_page(r['link']),timeout=15)
                if urlsplit(url).hostname!=host: raise ValueError('Domain changed')
                pages=[(url,page)]; links=[]
                for link in page.links:
                    target=urljoin(url,link)
                    if urlsplit(target).hostname==host and re.search('contact|pricing|sales',urlsplit(target).path,re.I) and target not in links: links.append(target)
                for target in links[:2]:
                    try:
                        final,p=await asyncio.wait_for(fetch_page(target),timeout=10)
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
            except Exception: item['status']='Google result; website could not be read'
            suppliers.append(item)
        suppliers.sort(key=lambda x:(x.get('source_kind')=='comparison',not x.get('gpu_mentioned',False),not bool(x['emails'])))
        # Imported records are a stable backup and do not depend on Google availability.
        historical=supplier_candidates(self.db,c)
        suppliers.extend(historical)
        report={'queries':coverage,'suppliers':suppliers,'created':time.time(),'deep':deep,'note':'Web prices are excerpts; imported records are historical. Confirm region, GPU variant, quantity, current capacity and total cost.'}
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
        if s.get('source_type')=='audit':
            yield f"Supplier {i}: {s['name']}\nHistorical supplier record: {s.get('audit_status','')}\n{s.get('source_ref','')}\nPricing evidence: {s.get('audit_evidence','')[:500]}\nConditions: {s.get('conditions','')[:350]}\n{s.get('fit','')}"
            continue
        yield f"Supplier {i}: {s['name']}\n{s['status']} | GPU mentioned: {s.get('gpu_mentioned',False)}\n"+'\n'.join('Source: '+x['url'] for x in s['sources'])+'\nPublished business contacts: '+(', '.join(x['email'] for x in s['emails']) or 'none found')+'\nPrice excerpts (unverified):\n'+'\n'.join(x['text']+'\n'+x['source'] for x in s['pricing_evidence'])

def shortlist(report,task):
    """One Telegram message with actionable search results and honest provenance."""
    web=[(i,s) for i,s in enumerate(report['suppliers'],1) if s.get('source_type')!='audit']
    audit=[(i,s) for i,s in enumerate(report['suppliers'],1) if s.get('source_type')=='audit']
    lines=[]
    if web:
        lines.append('Google supplier shortlist')
        for i,s in web[:5]:
            source=s['sources'][0]
            label='Price comparison source' if s.get('source_kind')=='comparison' else 'Supplier lead'
            lines.append(f"{i}. {s['name'][:100]}\n{label}\n{source['url']}\n{source.get('excerpt','')[:220]}")
    elif report.get('queries') and not any(q['status'].startswith('searched:') for q in report['queries']):
        lines.append('Google search could not complete this time. Here are saved supplier leads to investigate.')
    if audit:
        lines.append('From your supplier audit — historical leads')
        for i,s in audit[:3]:
            lines.append(f"{i}. {s['name']}\n{s['audit_status']}\n{s.get('conditions','')[:160]}")
    if not web and not audit:lines.append('No supplier leads found for this GPU. Try a broader GPU model or region.')
    if web or audit:
        lines.append('These leads require confirmation of GPU variant, quantity, region, capacity and total price.')
        lines.append(f'Details: /report {task}\nInvestigate pricing and contacts: /research {task}\nPrepare inquiry: /contact {task} <supplier number>')
    return '\n\n'.join(lines)[:3900]
