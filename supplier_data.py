"""Import and query the supplied supplier audit as reference evidence."""
import hashlib, json, sqlite3, re
from pathlib import Path

def schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS supplier_audit(sheet TEXT, row_number INTEGER, source_hash TEXT, data TEXT, PRIMARY KEY(sheet,row_number,source_hash))')
    db.execute('CREATE TABLE IF NOT EXISTS supplier_imports(source_hash TEXT PRIMARY KEY, filename TEXT, imported_at TEXT)')
    db.commit()

def import_workbook(db, path):
    import openpyxl
    path=Path(path)
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    book=openpyxl.load_workbook(path,read_only=True,data_only=True)
    schema(db)
    total=0
    for sheet in book:
        rows=sheet.values
        headers=[str(x or f'column_{i}') for i,x in enumerate(next(rows),1)]
        for number,row in enumerate(rows,2):
            if not any(x is not None for x in row): continue
            record=dict(zip(headers,(str(x) if x is not None else '' for x in row)))
            db.execute('INSERT OR REPLACE INTO supplier_audit VALUES(?,?,?,?)',(sheet.title,number,digest,json.dumps(record,ensure_ascii=False)))
            total+=1
    db.execute("INSERT OR REPLACE INTO supplier_imports VALUES(?,?,datetime('now'))",(digest,path.name))
    db.commit()
    return digest,total

def lookup(db,owner,term):
    schema(db)
    term=term.strip().lower()
    if len(term)<2: return 'Use /suppliers <company name or GPU model>.'
    rows=db.execute("SELECT row_number,data FROM supplier_audit WHERE sheet='Companies' ORDER BY row_number").fetchall()
    matches=[]
    for number,raw in rows:
        item=json.loads(raw)
        if term in json.dumps(item,ensure_ascii=False).lower():
            if '[redacted' in item.get('Company','').lower(): continue
            matches.append((number,item))
    if not matches:return 'No matching company in the imported audit.'
    out=['Imported supplier audit — historical evidence, not current inventory or a verified quote.']
    for number,item in matches[:5]:
        out.append(f"{item['Company']} (audit row {number})\nStatus: {item.get('H100 / response status','')}\nPricing evidence: {item.get('Pricing and evidence','')[:450]}\nConditions: {item.get('Conditions / availability','')[:350]}\nNext action: {item.get('Your next action','')[:250]}")
    if len(matches)>5:out.append(f'{len(matches)-5} more matches; narrow your search.')
    return '\n\n'.join(out)[:3900]

def candidates(db, criteria, limit=5):
    """Stable historical leads, never promoted to current inventory or quotes."""
    schema(db)
    model=criteria.gpu.upper().replace('_',' ').split()[0]
    matches={}
    for number,digest,raw in db.execute("SELECT row_number,source_hash,data FROM supplier_audit WHERE sheet='Companies' ORDER BY source_hash,row_number"):
        item=json.loads(raw); name=item.get('Company','').strip()
        status=item.get('H100 / response status','')
        text=' '.join(item.values())
        if not name or '[redacted' in name.lower() or not re.search(r'\b'+re.escape(model)+r'\b',text,re.I): continue
        if any(x in status.lower() for x in ('delivery failed','delivery delayed','no response','automated acknowledgment')): continue
        if model=='H100' and any(x in status.lower() for x in ('no current h100','no h100','no h100 stock')): continue
        conditions=item.get('Conditions / availability','')
        region=criteria.region.upper()
        region_terms={'US':('usa','united states','us region','omaha'),'IN':('india','noida'),'EU':('europe','eu region')}.get(region,())
        region_seen=any(x in conditions.lower() for x in region_terms)
        rank=(not region_seen,'offered / quoted' not in status.lower(),'offered' not in status.lower(),name.casefold())
        entry={'name':name,'domain':'','sources':[], 'emails':[], 'pricing_evidence':[],
               'source_type':'audit','source_ref':f'Imported supplier audit, Companies row {number}',
               'status':'Historical supplier record; current capacity needs confirmation',
               'audit_status':status,'audit_evidence':item.get('Pricing and evidence',''),
               'conditions':conditions,'next_action':item.get('Your next action',''),
               'gpu_mentioned':True,'fit':'Region mentioned in audit' if region_seen else 'Region, quantity and variant require confirmation'}
        key=name.casefold()
        if key not in matches or rank<matches[key][0]:matches[key]=(rank,entry)
    return [entry for rank,entry in sorted(matches.values(),key=lambda x:x[0])[:limit]]
