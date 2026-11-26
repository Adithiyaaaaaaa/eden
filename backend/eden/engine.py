"""Deterministic Eden Valley simulation engine and SQLite event store."""
from __future__ import annotations

import json
import random
import sqlite3
from pathlib import Path
from typing import Literal

import networkx as nx
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(__import__('os').environ.get('EDEN_DB', str(ROOT / 'eden.db')))
PEOPLE = [
    ('Mara Vale', 'Farmer', 'cooperative'), ('Tomas Reed', 'Farmer', 'cautious'),
    ('Iris Bell', 'Merchant', 'opportunistic'), ('Jonah Pike', 'Merchant', 'competitive'),
    ('Sana Okafor', 'Builder', 'cooperative'), ('Eli Chen', 'Builder', 'cautious'),
    ('Nia Sol', 'Researcher', 'opportunistic'), ('Owen Hart', 'Researcher', 'competitive'),
]
GOALS = {'Farmer': 'Keep the village fed', 'Merchant': 'Build a fair and thriving market',
         'Builder': 'Improve shared infrastructure', 'Researcher': 'Understand the valley'}
PROFILES = {'cooperative': 'Shares surplus and offers help when neighbors are in need.',
            'competitive': 'Prioritizes personal goals and seeks favorable exchanges.',
            'cautious': 'Protects reserves and rests when health or energy runs low.',
            'opportunistic': 'Adapts quickly to scarcity and pursues promising openings.'}

class Action(BaseModel):
    type: Literal['WORK','TRADE','NEGOTIATE','HELP','SOCIALIZE','BUILD','REST','OBSERVE']
    target_id: str | None = None
    resource: str | None = None
    amount: int = Field(default=1, ge=1, le=10)
    explanation: str = Field(default='', max_length=200)

def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, factory=ClosingConnection)
    db.row_factory = sqlite3.Row
    return db

class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None: self.commit()
            else: self.rollback()
        finally: self.close()
        return False

def init_db():
    with connect() as d:
        d.executescript('''CREATE TABLE IF NOT EXISTS agents(id TEXT PRIMARY KEY,name TEXT,occupation TEXT,profile TEXT,day INTEGER,food INTEGER,wood INTEGER,stone INTEGER,money REAL,energy INTEGER,health INTEGER,reputation REAL,goal TEXT,policy TEXT);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,day INTEGER,kind TEXT,actor TEXT,target TEXT,data TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS observations(id INTEGER PRIMARY KEY AUTOINCREMENT,day INTEGER,agent_id TEXT,data TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS links(source TEXT,target TEXT,trust REAL,interactions INTEGER,PRIMARY KEY(source,target));
        CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS experiments(id INTEGER PRIMARY KEY AUTOINCREMENT,condition TEXT,seed INTEGER,days INTEGER,result TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);''')
        if not d.execute('SELECT 1 FROM agents LIMIT 1').fetchone(): reset(d)

def event(d,day,kind,actor=None,target=None,**data):
    d.execute('INSERT INTO events(day,kind,actor,target,data) VALUES(?,?,?,?,?)',(day,kind,actor,target,json.dumps(data)))

def reset(d=None, seed=42, condition='C'):
    if d is None:
        with connect() as db: return reset(db,seed,condition)
    d.execute('DELETE FROM agents'); d.execute('DELETE FROM events'); d.execute('DELETE FROM links')
    d.execute('DELETE FROM observations')
    d.execute('INSERT OR REPLACE INTO config VALUES(?,?)',('seed',str(seed)))
    d.execute('INSERT OR REPLACE INTO config VALUES(?,?)',('condition',condition))
    for i,(name,job,profile) in enumerate(PEOPLE):
        kind = 'ai' if condition=='A' or (condition=='B' and i<4) else 'human'
        d.execute('INSERT INTO agents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(f'a{i+1}',name,job,profile,0,5 if job=='Farmer' else 3,2,2,10.0,90,100,50,GOALS[job],kind))
    event(d,0,'settlement_founded',None,None,seed=seed,condition=condition)

def snapshot():
    with connect() as d:
        agents=[dict(x) for x in d.execute('SELECT * FROM agents ORDER BY id')]
        events=[dict(x) for x in d.execute('SELECT * FROM events ORDER BY id DESC LIMIT 100')]
        for x in events: x['data']=json.loads(x['data'])
        config={x['key']:x['value'] for x in d.execute('SELECT * FROM config')}
        return {'agents':agents,'events':list(reversed(events)),'day':max((x['day'] for x in agents),default=0),'condition':config.get('condition','C'),'seed':int(config.get('seed',42)),'metrics':metrics(d)}

def policy_action(a, agents, rng):
    # Separate, configurable behavioral policies; never handled by the LLM adapter.
    need_food=a['food']<2
    others=[x for x in agents if x['id']!=a['id']]
    if a['energy']<28: return Action(type='REST',explanation='Recover energy before continuing.')
    if need_food and a['policy']=='cooperative':
        donor=next((x for x in others if x['food']>5),None)
        if donor:return Action(type='HELP',target_id=donor['id'],resource='food',explanation='Ask a neighbor to share food.')
    if a['occupation']=='Farmer': return Action(type='WORK',resource='food',explanation='Grow food for the settlement.')
    if a['occupation']=='Builder' and a['wood']>=2 and a['stone']>=2 and rng.random()<.18:return Action(type='BUILD',explanation='Improve shared infrastructure.')
    if a['occupation']=='Researcher' and rng.random()<.4:return Action(type='OBSERVE',explanation='Study current conditions.')
    if a['occupation']=='Merchant' and need_food:
        seller=next((x for x in others if x['food']>3 and x['money']<a['money']),None)
        if seller:return Action(type='TRADE',target_id=seller['id'],resource='food',amount=1,explanation='Offer a fair exchange for food.')
    if a['policy']=='competitive' and a['money']>8:return Action(type='WORK',resource='money',explanation='Pursue personal prosperity.')
    if a['policy']=='opportunistic' and rng.random()<.3:return Action(type='SOCIALIZE',target_id=rng.choice(others)['id'],explanation='Build a useful connection.')
    return Action(type='WORK',resource='wood' if a['occupation']=='Builder' else 'money',explanation='Contribute through daily work.')

def execute(d, actor, action):
    a=dict(d.execute('SELECT * FROM agents WHERE id=?',(actor,)).fetchone()); day=a['day']+1
    kind=action.type; message=''; target=None; success=True
    if kind=='REST': d.execute('UPDATE agents SET energy=MIN(100,energy+35),health=MIN(100,health+3),day=? WHERE id=?',(day,actor)); message=f"{a['name']} rested and recovered."
    elif kind=='WORK':
        resource=action.resource or ('food' if a['occupation']=='Farmer' else 'wood')
        if resource not in ('food','wood','stone','money'): resource='money'
        amount=2 if resource=='food' and a['occupation']=='Farmer' else 1
        d.execute(f'UPDATE agents SET {resource}={resource}+?,energy=MAX(0,energy-12),day=? WHERE id=?',(amount,day,actor)); message=f"{a['name']} produced {amount} {resource}."
    elif kind in ('TRADE','HELP','NEGOTIATE'):
        b=d.execute('SELECT * FROM agents WHERE id=?',(action.target_id,)).fetchone(); res=action.resource or 'food'; amount=action.amount
        if b and b['id']!=actor and res in ('food','wood','stone') and ((kind=='HELP' and a[res]>=amount) or (kind!='HELP' and b[res]>=amount and a['money']>=1)):
            if kind=='HELP': d.execute(f'UPDATE agents SET {res}={res}-? WHERE id=?',(amount,actor)); d.execute(f'UPDATE agents SET {res}={res}+? WHERE id=?',(amount,b['id']))
            else:
                d.execute(f'UPDATE agents SET {res}={res}-? WHERE id=?',(amount,b['id'])); d.execute(f'UPDATE agents SET {res}={res}+? WHERE id=?',(amount,actor))
                d.execute('UPDATE agents SET money=money-1 WHERE id=?',(actor,)); d.execute('UPDATE agents SET money=money+1 WHERE id=?',(b['id'],))
            target=b['id']; d.execute('INSERT INTO links VALUES(?,?,0.12,1) ON CONFLICT(source,target) DO UPDATE SET trust=MIN(1,trust+0.04),interactions=interactions+1',(actor,b['id']))
            d.execute('INSERT INTO links VALUES(?,?,0.12,1) ON CONFLICT(source,target) DO UPDATE SET trust=MIN(1,trust+0.04),interactions=interactions+1',(b['id'],actor)); message=f"{a['name']} {kind.lower()}d {amount} {res} with {b['name']}."
        else: success=False; message=f"{a['name']}'s {kind.lower()} was declined by deterministic trade rules."
        d.execute('UPDATE agents SET day=?,energy=MAX(0,energy-5) WHERE id=?',(day,actor))
    elif kind=='BUILD':
        if a['wood']>=2 and a['stone']>=2:
            d.execute('UPDATE agents SET wood=wood-2,stone=stone-2,reputation=reputation+2,energy=MAX(0,energy-15),day=? WHERE id=?',(day,actor)); message=f"{a['name']} built a shared storehouse."
        else: message=f"{a['name']} could not build; materials were insufficient."
        if not message: message='Build completed.'
        d.execute('UPDATE agents SET day=? WHERE id=?',(day,actor))
    else:
        b=action.target_id or actor; target=b
        if b!=actor and d.execute('SELECT 1 FROM agents WHERE id=?',(b,)).fetchone():
            d.execute('INSERT INTO links VALUES(?,?,0.08,1) ON CONFLICT(source,target) DO UPDATE SET trust=MIN(1,trust+0.025),interactions=interactions+1',(actor,b)); message=f"{a['name']} connected with {d.execute('SELECT name FROM agents WHERE id=?',(b,)).fetchone()[0]}."
        else: message=f"{a['name']} observed the valley."
        d.execute('UPDATE agents SET day=?,energy=MAX(0,energy-2) WHERE id=?',(day,actor))
    event(d,day,kind,actor,target,success=success,explanation=action.explanation,result=message,action=action.model_dump())
    # Daily consumption/progression is applied once all inhabitants have acted.
    return {'ok':True,'message':message,'day':day}

def step(seed=None):
    with connect() as d:
        agents=[dict(x) for x in d.execute('SELECT * FROM agents ORDER BY id')]
        config={x['key']:x['value'] for x in d.execute('SELECT * FROM config')}; rng=random.Random(int(seed if seed is not None else config.get('seed',42))+max(x['day'] for x in agents)*997)
        day=max(x['day'] for x in agents)+1
        # All inhabitants act once; human-policy agents use explicit deterministic rules.
        for a in agents:
            observation={'environment':{'day':day,'agents':agents},'agent':a,'objective':a['goal'],'recent_memories':[e[0] for e in d.execute('SELECT json_extract(data,\'$.result\') FROM events WHERE actor=? ORDER BY id DESC LIMIT 8',(a['id'],)).fetchall()],'available_actions':['WORK','TRADE','NEGOTIATE','HELP','SOCIALIZE','BUILD','REST','OBSERVE']}
            d.execute('INSERT INTO observations(day,agent_id,data) VALUES(?,?,?)',(day,a['id'],json.dumps(observation)))
            if a['policy']!='ai': act=policy_action(a,agents,rng)
            else:
                import os
                from .ai import decide
                provider=os.getenv('EDEN_LLM_PROVIDER','gemini').lower()
                configured=(os.getenv('GROQ_API_KEY') if provider=='groq' else os.getenv('GEMINI_API_KEY')) or os.getenv('EDEN_LLM_API_KEY')
                if configured:
                    try: act=decide(observation)
                    except Exception as exc:
                        act=policy_action(a,agents,rng); event(d,day,'provider_fallback',a['id'],None,error=type(exc).__name__)
                else: act=policy_action(a,agents,rng)
            execute(d,a['id'],act)
        food=[x[0] for x in d.execute('SELECT food FROM agents')]; available=sum(food)
        for row in d.execute('SELECT id,food,health FROM agents ORDER BY id').fetchall():
            if row['food']>0: d.execute('UPDATE agents SET food=food-1,health=MIN(100,health+1) WHERE id=?',(row['id'],))
            else: d.execute('UPDATE agents SET health=MAX(0,health-12) WHERE id=?',(row['id'],))
        weather_roll=rng.random()
        if weather_roll<.12:
            farmer=d.execute("SELECT id FROM agents WHERE occupation='Farmer' ORDER BY id LIMIT 1").fetchone()[0]
            d.execute('UPDATE agents SET food=MAX(0,food-1) WHERE id=?',(farmer,)); event(d,day,'drought',farmer,None,impact='Reduced one food store.')
        event(d,day,'day_ended',None,None,food_available=available,weather='drought' if weather_roll<.12 else 'clear')
        d.commit()
        return snapshot()

def metrics(d=None):
    own=d is None
    if own:d=connect()
    rows=d.execute('SELECT * FROM agents ORDER BY id').fetchall(); n=len(rows)
    wealth=[max(0,r['money']+r['food']+r['wood']+r['stone']) for r in rows]; total=sum(wealth)
    gini=(sum((i+1)*v for i,v in enumerate(sorted(wealth)))*2/(n*total)-(n+1)/n) if n and total else 0
    interactions=d.execute("SELECT COUNT(*) FROM events WHERE kind IN ('TRADE','HELP','NEGOTIATE','SOCIALIZE') AND target IS NOT NULL").fetchone()[0]
    trade=d.execute("SELECT COALESCE(SUM(json_extract(data,'$.action.amount')),0) FROM events WHERE kind IN ('TRADE','NEGOTIATE') AND json_extract(data,'$.success')=1").fetchone()[0]
    links=d.execute('SELECT source,target,trust FROM links').fetchall(); graph=nx.Graph(); graph.add_nodes_from(r['id'] for r in rows); graph.add_edges_from((r['source'],r['target']) for r in links)
    deaths=sum(r['health']<=0 for r in rows)
    return {'survival_rate':round((n-deaths)/n,3) if n else 0,'cooperation_rate':round(interactions/max(1,d.execute('SELECT COUNT(*) FROM events WHERE kind NOT IN (\'settlement_founded\',\'day_ended\')').fetchone()[0]),3),'trade_volume':trade,'wealth_gini':round(max(0,min(1,gini)),3),'network_density':round(nx.density(graph),3),'resource_efficiency':round(sum(r['food']+r['wood']+r['stone'] for r in rows)/max(1,n)),'mean_trust':round(sum(r['trust'] for r in links)/len(links),3) if links else 0,'social_inequality':round((max(wealth)-min(wealth))/total,3) if total else 0,'measured_events':d.execute('SELECT COUNT(*) FROM events').fetchone()[0]}
