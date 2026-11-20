export class ApiError extends Error {
  constructor(message:string, public status=0){super(message);this.name='ApiError'}
}
export async function apiRequest(access:string,path:string,body?:unknown,signal?:AbortSignal){
 const controller=new AbortController();
 const abort=()=>controller.abort();
 signal?.addEventListener('abort',abort,{once:true});
 if(signal?.aborted)controller.abort();
 const timeout=setTimeout(()=>controller.abort(),path.endsWith('/analyze')?200000:15000);
 try{
  const response=await fetch('/api/'+path,{method:body===undefined?'GET':'POST',headers:{Authorization:'Bearer '+access,...(body===undefined?{}:{'Content-Type':'application/json'})},body:body===undefined?undefined:JSON.stringify(body),signal:controller.signal});
  if(response.status===401||response.status===403)throw new ApiError('Sessão expirada ou acesso negado. Reconecte com o endereço exibido pelo servidor; confirme a origem local.',response.status);
  if(response.status===503)throw new ApiError('Backend temporariamente indisponível. Tente novamente.',503);
  let result;
  try{result=await response.json()}catch{throw new ApiError('Resposta inválida do backend. Confirme que abriu a porta 8765.')}
  if(!response.ok)throw new ApiError(result.error||'Requisição negada pelo servidor.',response.status);
  return result;
 }catch(error){
  if(error instanceof ApiError)throw error;
  if(controller.signal.aborted){if(signal?.aborted)throw new DOMException('Cancelado','AbortError');throw new ApiError('Tempo de resposta excedido. Verifique o backend e tente novamente.')}
  throw new ApiError('Falha de conexão com o backend local. Inicie python scripts/start_local.py e tente novamente.');
 }finally{clearTimeout(timeout);signal?.removeEventListener('abort',abort)}
}
