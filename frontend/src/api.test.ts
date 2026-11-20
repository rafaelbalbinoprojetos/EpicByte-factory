import {afterEach,describe,expect,it,vi} from 'vitest';
import {apiRequest} from './api';
afterEach(()=>{vi.unstubAllGlobals();vi.useRealTimers()});
describe('recuperação de rede',()=>{
 it('traduz Failed to fetch sem ocultar falha',async()=>{vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));await expect(apiRequest('local','state')).rejects.toThrow('Falha de conexão')});
 it('identifica sessão e origem negadas',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValue({status:403,ok:false}));await expect(apiRequest('old','state')).rejects.toThrow('Sessão expirada ou acesso negado')});
 it('preserva erro operacional',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValue({status:409,ok:false,json:async()=>({error:'Certificação necessária'})}));await expect(apiRequest('local','missions',{})).rejects.toThrow('Certificação necessária')});
 it('identifica backend indisponível',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValue({status:503,ok:false}));await expect(apiRequest('local','state')).rejects.toThrow('temporariamente indisponível')});
 it('identifica resposta de porta incorreta',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValue({status:200,ok:true,json:async()=>{throw Error('HTML')}}));await expect(apiRequest('local','state')).rejects.toThrow('Resposta inválida')});
 it('aborta timeout e explica recuperação',async()=>{vi.useFakeTimers();vi.stubGlobal('fetch',vi.fn((_url,options)=>new Promise((_resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('aborted','AbortError'))))));const pending=expect(apiRequest('local','state')).rejects.toThrow('Tempo de resposta excedido');await vi.advanceTimersByTimeAsync(15001);await pending});
 it('permite recuperar após falha',async()=>{const fetcher=vi.fn().mockRejectedValueOnce(new TypeError('Failed to fetch')).mockResolvedValueOnce({ok:true,json:async()=>({recovered:true})});vi.stubGlobal('fetch',fetcher);await expect(apiRequest('local','state')).rejects.toThrow();await expect(apiRequest('local','state')).resolves.toEqual({recovered:true})});
});
