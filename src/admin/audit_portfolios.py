"""Read-only migration inventory. Never reads credentials, initializes schema or resets data."""
import json
import os
import sqlite3
from pathlib import Path
from src.config import DATA_DIR


def main():
    path=Path(os.getenv('PAPER_DB_PATH',str(DATA_DIR/'paper/workspace.sqlite3'))).resolve()
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        columns={row['name'] for row in db.execute('PRAGMA table_info(users)')}
        if 'username' not in columns:
            print(json.dumps({'database':str(path),'status':'PRE_USERNAME_SCHEMA','action':'No changes made'}));return
        result=[]
        for user in db.execute("SELECT id,username,role FROM users WHERE username IN ('admin1','user1')"):
            legs=[]
            for row in db.execute('SELECT id,market,currency,starting_cash,cash FROM portfolios WHERE user_id=?',(user['id'],)):
                leg=dict(row)
                for table in ['positions','orders','snapshots']:
                    leg[table+'_count']=db.execute(f'SELECT COUNT(*) FROM {table} WHERE portfolio_id=?',(row['id'],)).fetchone()[0]
                legs.append(leg)
            result.append({**dict(user),'currency_subledgers_minor_units':legs})
        print(json.dumps({'database':str(path),'accounts':result,'action':'READ_ONLY_NO_CHANGES'},indent=2))


if __name__=='__main__':main()
