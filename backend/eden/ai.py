"""Optional OpenAI-compatible structured action provider. No keys are bundled."""
import json, os, time, urllib.error, urllib.request
from pathlib import Path
from dotenv import load_dotenv
from .engine import Action

load_dotenv(Path(__file__).resolve().parents[1] / '.env')

def decide(observation: dict) -> Action:
    """Request one schema-validated action; return safe baseline if unconfigured."""
    provider=os.getenv('EDEN_LLM_PROVIDER','gemini').lower()
    if provider=='groq':
        key=os.getenv('GROQ_API_KEY'); endpoint=os.getenv('EDEN_LLM_ENDPOINT') or 'https://api.groq.com/openai/v1'; model=os.getenv('EDEN_LLM_MODEL') or 'llama-3.3-70b-versatile'
    else:
        key=os.getenv('GEMINI_API_KEY'); endpoint=os.getenv('EDEN_LLM_ENDPOINT') or 'https://generativelanguage.googleapis.com/v1beta/openai'; model=os.getenv('EDEN_LLM_MODEL') or 'gemini-2.5-flash'
    # Preserve compatibility with a custom OpenAI-compatible provider configuration.
    if not key: key=os.getenv('EDEN_LLM_API_KEY')
    if not key or not endpoint:
        return Action(type='OBSERVE',explanation='No LLM provider configured; safe baseline observation.')
    schema=Action.model_json_schema()
    payload={'model':model,'messages':[{'role':'system','content':'Choose one valid action for this agent. Return JSON only. Explanations must be concise decision summaries, never private chain-of-thought.'},{'role':'user','content':json.dumps(observation)}],'response_format':{'type':'json_schema','json_schema':{'name':'eden_action','strict':True,'schema':schema}}}
    req=urllib.request.Request(endpoint.rstrip('/')+'/chat/completions',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req,timeout=30) as response: result=json.loads(response.read())
            break
        except urllib.error.HTTPError as exc:
            if exc.code not in (429,500,502,503,504) or attempt==2: raise
            time.sleep(min(8,2**attempt))
        except urllib.error.URLError:
            if attempt==2: raise
            time.sleep(min(8,2**attempt))
    return Action.model_validate_json(result['choices'][0]['message']['content'])
