"""Optional real vision smoke; no mission and no development writes."""
import json
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw
from epicbyte.provider import CodexProvider
root=Path(__file__).resolve().parents[1]
report={'write':False,'paid_api_fallback':False}
with tempfile.TemporaryDirectory(prefix='epicbyte-vision-') as directory:
 workspace=Path(directory)
 image=Image.new('RGB',(320,200),'#101820');draw=ImageDraw.Draw(image);draw.rectangle((10,10,70,190),fill='#00ced1');image.save(workspace/'reference.png')
 provider=CodexProvider()
 try:
  caps=provider.capabilities();report['capabilities']=caps
  if not caps['images']:report['status']='UNAVAILABLE'
  else:
   result=provider.execute('Analise apenas a imagem anexada. Retorne JSON com visible_colors e layout. Não execute comandos, não escreva arquivos e não infira comportamento invisível.',workspace,timeout=60,images=[workspace/'reference.png'],model=caps['model'])
   report.update(status='COMPLETED',response=result.text,provider=result.provider)
 except Exception as error:report.update(status='FAILED',error=str(error))
(root/'logs/studio_vision_smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
