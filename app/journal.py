"""Owner-entered journal records, separate from licensed market-data retention."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
import csv
import io
import uuid
from zoneinfo import ZoneInfo

from .scanner import reference_groups

TZ=ZoneInfo('Asia/Kolkata')


def amount(value, name, *, optional=False, zero=False, places=4):
    if optional and value in (None,''):
        return None
    try:
        if isinstance(value,bool):
            raise ValueError()
        result=Decimal(str(value))
        quantum=Decimal(1).scaleb(-places)
        if not result.is_finite() or result<0 or (result==0 and not zero) or result>Decimal('10000000000') or result!=result.quantize(quantum):
            raise ValueError()
        return format(result,'f')
    except (InvalidOperation,ValueError,TypeError):
        raise ValueError(f'{name} must be a valid {"nonnegative" if zero else "positive"} amount with at most {places} decimal places.') from None


def normalize(body):
    groups=reference_groups()
    symbol=str(body.get('symbol','')).strip().upper()
    memberships=[g for g in groups if any('NSE:'+s[0]==symbol for s in g['stocks'])]
    if not memberships:
        raise ValueError('Choose an existing approved instrument.')
    sector=str(body.get('sector') or memberships[0]['id'])
    if sector not in {g['id'] for g in memberships}:
        raise ValueError('Sector must be an existing membership of this instrument.')
    try:
        raw=str(body.get('traded_at') or '')
        stamp=datetime.fromisoformat(raw)
        stamp=(stamp.replace(tzinfo=TZ) if stamp.tzinfo is None else stamp.astimezone(TZ)).isoformat()
    except ValueError:
        raise ValueError('Provide a valid trade date/time in IST.') from None
    quantity=body.get('quantity')
    if isinstance(quantity,bool) or not str(quantity).isdigit() or not 1<=int(quantity)<=1000000000:
        raise ValueError('Quantity must be a whole number from 1 to 1,000,000,000.')
    side=body.get('side','long')
    if side not in {'long','short'}:
        raise ValueError('Side must be long or short.')
    result={'traded_at':stamp,'symbol':symbol,'sector':sector,'setup':str(body.get('setup','')).strip(),
            'side':side,'entry':amount(body.get('entry'),'Entry'),'exit':amount(body.get('exit'),'Exit',optional=True),
            'quantity':int(quantity),'stop_loss':amount(body.get('stop_loss'),'Stop loss',optional=True),
            'target':amount(body.get('target'),'Target',optional=True),'charges':amount(body.get('charges',0),'Charges',zero=True,places=2),
            'notes':str(body.get('notes','')).strip(),'lessons':str(body.get('lessons','')).strip()}
    if len(result['setup'])>120 or len(result['notes'])>4000 or len(result['lessons'])>4000:
        raise ValueError('Setup is limited to 120 characters; notes and lessons to 4,000 each.')
    return result


def pnl(record):
    if record['exit'] is None:
        return None
    direction=1 if record['side']=='long' else -1
    return ((Decimal(record['exit'])-Decimal(record['entry']))*record['quantity']*direction-Decimal(record['charges'])).quantize(Decimal('.01'))


def summary(records):
    closed=[r for r in records if r['exit'] is not None]
    values=[pnl(r) for r in closed]
    wins=[v for v in values if v>0];losses=[v for v in values if v<0]
    def money(value):return format(value.quantize(Decimal('.01')),'f')
    total=sum(values,Decimal(0));gains=sum(wins,Decimal(0));loss=-sum(losses,Decimal(0))
    result={'closed_trades':len(closed),'open_trades':len(records)-len(closed),'realized_pnl':money(total),
            'win_rate':len(wins)/len(closed)*100 if closed else None,
            'average_win':money(gains/len(wins)) if wins else None,
            'average_loss':money(-loss/len(losses)) if losses else None,
            'profit_factor':float(gains/loss) if loss else None,
            'profit_factor_note':'No realized losses' if closed and not loss else 'Insufficient closed trades' if not closed else '',
            'expectancy':money(total/len(closed)) if closed else None}
    for field,label in [('setup','by_setup'),('sector','by_sector'),('hour','by_trading_time')]:
        buckets={}
        for record in closed:
            key=f"{datetime.fromisoformat(record['traded_at']).hour:02d}:00 IST" if field=='hour' else record[field] or 'Unspecified'
            buckets.setdefault(key,[]).append(pnl(record))
        result[label]=[{'group':key,'trades':len(items),'realized_pnl':money(sum(items,Decimal(0))),
                        'win_rate':sum(v>0 for v in items)/len(items)*100} for key,items in sorted(buckets.items())]
    return result


class Journal:
    def __init__(self,store):self.store=store

    def initialize(self):
        with self.store.connection() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS personal_journal_v1(
                id TEXT PRIMARY KEY,traded_at TEXT NOT NULL,symbol TEXT NOT NULL,sector TEXT NOT NULL,
                setup TEXT NOT NULL,side TEXT NOT NULL,entry TEXT NOT NULL,exit TEXT,quantity INTEGER NOT NULL,
                stop_loss TEXT,target TEXT,charges TEXT NOT NULL,notes TEXT NOT NULL,lessons TEXT NOT NULL,
                created_at TEXT NOT NULL,updated_at TEXT NOT NULL)''')
            db.execute('CREATE INDEX IF NOT EXISTS personal_journal_time ON personal_journal_v1(traded_at)')

    def records(self):
        self.initialize()
        with self.store.connection() as db:
            rows=[dict(r) for r in db.execute('SELECT * FROM personal_journal_v1 ORDER BY traded_at DESC,id')]
        return [{**r,'realized_pnl':format(pnl(r),'f') if pnl(r) is not None else None} for r in rows]

    def save(self,body,record_id=None):
        data=normalize(body)
        key=str(uuid.UUID(record_id or body.get('id') or str(uuid.uuid4())))
        self.initialize()
        now=datetime.now(TZ).isoformat()
        with self.store.connection() as db:
            existing=db.execute('SELECT * FROM personal_journal_v1 WHERE id=?',(key,)).fetchone()
            if record_id:
                if not existing:raise LookupError('Journal record not found.')
                assignments=','.join(f'{column}=?' if column!='exit' else '"exit"=?' for column in data)
                db.execute(f'UPDATE personal_journal_v1 SET {assignments},updated_at=? WHERE id=?',(*data.values(),now,key))
            elif existing:
                if any(existing[column]!=value for column,value in data.items()):
                    raise ValueError('This entry identifier already exists with different values.')
            else:
                columns=','.join('"exit"' if column=='exit' else column for column in data)
                placeholders=','.join('?' for _ in range(len(data)+3))
                db.execute(f'INSERT INTO personal_journal_v1(id,{columns},created_at,updated_at) VALUES({placeholders})',(key,*data.values(),now,now))
        return next(r for r in self.records() if r['id']==key)

    def delete(self,key):
        self.initialize()
        with self.store.connection() as db:
            if db.execute('DELETE FROM personal_journal_v1 WHERE id=?',(key,)).rowcount!=1:
                raise LookupError('Journal record not found.')

    def export(self):
        stream=io.StringIO(newline='');writer=csv.writer(stream)
        columns=['traded_at','symbol','sector','setup','side','entry','exit','quantity','stop_loss','target','charges','realized_pnl','notes','lessons']
        writer.writerow(columns)
        for record in self.records():
            values=[]
            for key in columns:
                value=str(record.get(key) if record.get(key) is not None else '')
                values.append("'"+value if value.lstrip().startswith(('=','+','-','@','\t','\r')) else value)
            writer.writerow(values)
        return '\ufeff'+stream.getvalue()
