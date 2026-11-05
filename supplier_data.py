"""Import and query the supplied supplier audit as reference evidence."""
import hashlib, json, sqlite3
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
