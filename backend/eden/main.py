import asyncio
import json
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from .engine import Action, connect, execute, init_db, metrics, reset, snapshot, step, policy_action
from .ai import decide

app=FastAPI(title='EDEN Research Simulator',version='0.1.0')
app.add_middleware(CORSMiddleware,allow_origins=['*'],allow_methods=['*'],allow_headers=['*'])
class ResetRequest(BaseModel): seed:int=42; condition:str='C'
class ActRequest(BaseModel): actor_id:str; action:Action
class TrialsRequest(BaseModel): condition:str='C'; seed:int=42; trials:int=Field(default=5,ge=1,le=100); days:int=Field(default=7,ge=1,le=365)
@app.on_event('startup')
def startup(): init_db()
@app.get('/api/health')
def health(): return {'ok':True,'service':'eden'}
@app.get('/api/state')
def state(): return snapshot()
@app.get('/api/agents/{agent_id}/history')
def history(agent_id:str):
    with connect() as d:
        if not d.execute('SELECT 1 FROM agents WHERE id=?',(agent_id,)).fetchone(): raise HTTPException(404,'Unknown inhabitant')
        rows=d.execute('SELECT * FROM events WHERE actor=? OR target=? ORDER BY id DESC LIMIT 100',(agent_id,agent_id)).fetchall()
        return [dict(r)|{'data':json.loads(r['data'])} for r in rows]
@app.post('/api/reset')
def reset_api(request:ResetRequest):
    if request.condition not in ('A','B','C'): raise HTTPException(400,'Condition must be A, B, or C')
    reset(seed=request.seed,condition=request.condition); return snapshot()
@app.post('/api/step')
def advance(): return step()
@app.post('/api/act')
def act(request:ActRequest):
    with connect() as d:
        if not d.execute('SELECT 1 FROM agents WHERE id=?',(request.actor_id,)).fetchone(): raise HTTPException(404,'Unknown inhabitant')
        return execute(d,request.actor_id,request.action)
@app.post('/api/agent/{agent_id}/decide')
def agent_decide(agent_id:str):
    state=snapshot(); a=next((x for x in state['agents'] if x['id']==agent_id),None)
    if not a: raise HTTPException(404,'Unknown inhabitant')
    observation={'environment':{'day':state['day'],'condition':state['condition'],'population':state['agents']},'agent':a,'objective':a['goal'],'recent_memories':[e['data'].get('result','') for e in state['events'] if e.get('actor')==agent_id][-8:],'available_actions':['WORK','TRADE','NEGOTIATE','HELP','SOCIALIZE','BUILD','REST','OBSERVE']}
    with connect() as d: d.execute('INSERT INTO observations(day,agent_id,data) VALUES(?,?,?)',(state['day'],agent_id,json.dumps(observation)))
    return decide(observation)
@app.post('/api/experiments/run')
def run_trials(request:TrialsRequest):
    if request.condition not in ('A','B','C'): raise HTTPException(400,'Condition must be A, B, or C')
    results=[]
    for i in range(request.trials):
        reset(seed=request.seed+i,condition=request.condition)
        for _ in range(request.days): step(seed=request.seed+i)
        s=snapshot(); result={'trial':i+1,'seed':request.seed+i,'metrics':s['metrics']}; results.append(result)
        with connect() as d: d.execute('INSERT INTO experiments(condition,seed,days,result) VALUES(?,?,?,?)',(request.condition,request.seed+i,request.days,json.dumps(result)))
    return {'condition':request.condition,'trials':results}
@app.get('/api/experiments')
def experiments():
    with connect() as d:
        return [dict(r)|{'result':json.loads(r['result'])} for r in d.execute('SELECT * FROM experiments ORDER BY id DESC LIMIT 100')]
@app.websocket('/ws')
async def websocket(ws:WebSocket):
    await ws.accept()
    try:
        while True:
            await ws.send_json(snapshot()); await asyncio.sleep(1)
    except WebSocketDisconnect: pass
