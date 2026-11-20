"""Deterministic 2.1 validation; does not certify or execute write missions."""
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
root=Path(__file__).resolve().parents[1]
npm='npm.cmd' if os.name=='nt' else 'npm'
checks=[('python',[sys.executable,'-m','unittest','discover','-s','tests','-q'],root),('react',[npm,'test'],root/'frontend'),('eslint',[npm,'run','lint'],root/'frontend'),('typescript_build',[npm,'run','build'],root/'frontend'),('http',[sys.executable,'-m','scripts.smoke_studio'],root)]
report={'checked_at':datetime.now(timezone.utc).isoformat(),'checks':{},'write_missions_executed':False,'visual_validation':False}
for name,args,cwd in checks:
 result=subprocess.run(args,cwd=cwd,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180)
 report['checks'][name]={'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
 print(name+': '+str(result.returncode),flush=True)
report['passed']=all(c['exit_code']==0 for c in report['checks'].values())
(root/'logs/studio_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
raise SystemExit(0 if report['passed'] else 1)
