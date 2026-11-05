import argparse, sqlite3
from supplier_data import import_workbook

parser=argparse.ArgumentParser()
parser.add_argument('workbook')
parser.add_argument('--database',default='scout.db')
args=parser.parse_args()
db=sqlite3.connect(args.database)
digest,count=import_workbook(db,args.workbook)
print(f'Imported {count} nonempty audit rows across all sheets. SHA256: {digest}')
