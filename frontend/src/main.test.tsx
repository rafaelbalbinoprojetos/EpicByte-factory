import {describe,it,expect,vi,beforeEach,afterEach} from 'vitest';

import {act,render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';

import '@testing-library/jest-dom/vitest';

import {App,progress,title} from './main';

vi.mock('echarts/core',()=>({use:vi.fn(),init:()=>({setOption:vi.fn(),dispose:vi.fn(),resize:vi.fn()})}));

const mission={id:'mission_real',source:'# Missão real',state:'CREATED',created:new Date().toISOString(),workspace:'workspaces/mission_real',elapsed:10,active_since:null,pause:0,tasks:[]};

const state={missions:[mission],events:[],executions:[],evidence:[],agents:[],diagnostic:{isolation_certified:false},workspaces:[{id:'managed',label:'Workspace autorizado'}],limits:{},versions:{}};

beforeEach(()=>{sessionStorage.setItem('epicbyte-access','local');vi.stubGlobal('fetch',vi.fn(async (url:string)=>({ok:true,json:async()=>url==='/api/state'?state:{dry_run:true},body:{getReader:()=>({read:async()=>({done:true})})}})))});

afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.useRealTimers()});

describe('contratos e controles',()=>{

 it('não inventa progresso',()=>{expect(progress(mission)).toBe(0);expect(title(mission)).toBe('Missão real')});

 it('exibe dados reais e certificação pendente',async()=>{render(<App/>);expect(await screen.findByText('Missão real')).toBeInTheDocument();expect(screen.getByText('Certificação necessária')).toBeInTheDocument()});

 it('início chama backend e pausa é operacional',async()=>{render(<App/>);fireEvent.click(await screen.findByText('Missão real'));fireEvent.click(screen.getByRole('button',{name:'Iniciar'}));await waitFor(()=>expect(fetch).toHaveBeenCalledWith('/api/missions/mission_real/start',expect.objectContaining({method:'POST'})));expect(screen.getByRole('button',{name:'Retomar'})).toBeDisabled()});

 it('creator usa raiz autorizada e dry-run',async()=>{render(<App/>);await screen.findByText('Missão real');fireEvent.click(screen.getByRole('button',{name:'Mission Creator'}));fireEvent.change(screen.getByLabelText('Nome da missão'),{target:{value:'Teste'}});fireEvent.change(screen.getByLabelText('Descrição detalhada'),{target:{value:'Objetivo'}});fireEvent.change(screen.getByLabelText('Critérios de aceite'),{target:{value:'Testes'}});fireEvent.click(screen.getByRole('button',{name:'Criar missão'}));await waitFor(()=>expect(fetch).toHaveBeenCalledWith('/api/missions',expect.objectContaining({body:expect.stringContaining('"dry_run":true')})));expect(screen.getByText('Dry-run validado')).toBeInTheDocument()});

 it('mostra rejeição de segurança do backend',async()=>{render(<App/>);fireEvent.click(await screen.findByText('Missão real'));vi.mocked(fetch).mockResolvedValueOnce({ok:false,json:async()=>({error:'Isolamento não certificado'})} as Response);fireEvent.click(screen.getByRole('button',{name:'Iniciar'}));expect(await screen.findByRole('alert')).toHaveTextContent('Isolamento não certificado')});

});

 it('pausa e retomada usam operações do backend',async()=>{
   const paused={...state,missions:[{...mission,state:'PAUSED',pause:1}]};
   vi.mocked(fetch).mockImplementation(async (url)=>({ok:true,json:async()=>String(url)==='/api/state'?paused:{accepted:'mission_real'},body:{getReader:()=>({read:async()=>({done:true})})}} as unknown as Response));
   render(<App/>);fireEvent.click(await screen.findByText('Missão real'));
   expect(screen.getByRole('button',{name:'Iniciar'})).toBeDisabled();
   fireEvent.click(screen.getByRole('button',{name:'Retomar'}));
   await waitFor(()=>expect(fetch).toHaveBeenCalledWith('/api/missions/mission_real/resume',expect.objectContaining({method:'POST'})));
 });
 it('solicita pausa de uma missão em execução',async()=>{
   const active={...state,missions:[{...mission,state:'RUNNING'}]};
   vi.mocked(fetch).mockImplementation(async (url)=>({ok:true,json:async()=>String(url)==='/api/state'?active:{pause_requested:'mission_real'},body:{getReader:()=>({read:async()=>({done:true})})}} as unknown as Response));
   render(<App/>);fireEvent.click(await screen.findByText('Missão real'));fireEvent.click(screen.getByRole('button',{name:'Pausar'}));
   await waitFor(()=>expect(fetch).toHaveBeenCalledWith('/api/missions/mission_real/pause',expect.objectContaining({method:'POST'})));
 });

 it('detecta SSE sem heartbeat e informa reconexão',async()=>{
   vi.useFakeTimers();
   vi.mocked(fetch).mockImplementation(async(url,options)=>String(url)==='/api/state'?{ok:true,json:async()=>state} as Response:{ok:true,body:{getReader:()=>({read:()=>new Promise((_resolve,reject)=>options?.signal?.addEventListener('abort',()=>reject(new DOMException('Abortado','AbortError')),{once:true}))})}} as unknown as Response);
   render(<App/>);
   await act(async()=>{await vi.advanceTimersByTimeAsync(1)});
   await act(async()=>{await vi.advanceTimersByTimeAsync(30001)});
   expect(screen.getByRole('alert')).toHaveTextContent('timeout de heartbeat');
 });
