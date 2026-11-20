# EpicByte Factory 2.1 — Intelligent Product Studio

Implementação incremental sobre a Factory 2.0. O backend continua sendo a autoridade de execução. Não houve reconstrução, deploy, push, alteração de credenciais ou execução de missões de escrita nesta evolução. O projeto principal está versionado no Git (branch `main`); repositórios e branches dos workspaces existentes foram preservados.

## Iniciar

```powershell
cd C:\EpicByte-Factory\EpicByte-Factory
python -m pip install -r requirements.txt
python scripts/start_local.py
```

Abra **o endereço completo exibido pelo servidor**, em `http://127.0.0.1:8780`, com o fragmento temporário da sessão. Não use `localhost`, a porta de desenvolvimento Vite ou uma chave de servidor anterior. A proteção de Host e Origin permanece exata; não foi habilitado CORS externo. A interface e a API são servidas juntas. O primeiro comando só é necessário para preparar a dependência Pillow de validação de imagens.

## Fluxo implementado

1. Mission Creator → descreva livremente a ideia e crie uma concepção sem workspace de desenvolvimento.
2. Anexe referências e informe descrição, o que aproveitar/evitar, prioridade e proximidade visual. As preferências se aplicam aos próximos arquivos selecionados; remova e reenvie antes de aprovar para alterá-las.
3. Solicite análise ao **Solution Strategist**, com especialidade integrada **Visual Design Analyst**. Usa o Codex App Server local em read-only; sem API paga alternativa. A análise tem limite de 180 segundos e histórico real de execução e falha.
4. Revise resumo, problema, usuários, hipóteses, dúvidas essenciais, alternativas, riscos, oportunidades, MVP, fases futuras, arquitetura e Design Brief.
5. Marque funcionalidades, revise o Design Brief e aprove a versão. REQUESTED e RECOMMENDED são origens; somente as selecionadas tornam-se APPROVED. Nenhuma recomendação é selecionada por padrão.
6. Crie a missão com a versão aprovada. Exige certificação atual antes de criar workspace; depois use Iniciar no Mission Control. Criar ou aprovar uma concepção não inicia desenvolvimento.

O campo de respostas registra decisões em linguagem natural em `client_decisions`, com nova versão. A análise seguinte recebe essas decisões sem permitir que o modelo invente outras. A revisão avançada em JSON permite corrigir requisitos e diretrizes ou continuar quando o modelo está indisponível. Salvar cria nova versão, que precisa de nova aprovação. Aprovações são imutáveis. Referências ficam congeladas após a primeira aprovação. Um briefing encaminhado não pode ser alterado ou encaminhado duas vezes. Para nova demanda após encaminhamento, crie outra concepção.

O formulário técnico anterior e o dry-run continuam disponíveis em uma seção própria, preservando o contrato legado. Missões legadas mantêm o texto original como escopo autorizado.

## Arquitetura e persistência

- `epicbyte/studio.py`: concepção, proposta validada, versionamento, aprovação, transferência e armazenamento privado de referências.
- `epicbyte/api.py`: API autenticada, operações de concepção serializadas, consultas, controles operacionais e SSE.
- `epicbyte/provider.py`: consulta real `model/list`, verificação de modalidades e entrada oficial `localImage` em `turn/start`.
- `epicbyte/engine.py`: Solution Strategist antes de Product Owner e planejamento; vínculo obrigatório de tarefas a IDs aprovados para missões do Studio.
- `frontend/src/api.ts`: erros de rede, sessão/origem, timeout, resposta inválida e indisponibilidade.
- `frontend/src/studio.tsx`: ideia, anexos, proposta, seleção, aprovação e revisão versionada.

Pipeline: Cliente → Solution Strategist / Visual Design Analyst → aprovação do cliente → Product Owner → Software Architect → Planner → Developer → Code Reviewer → QA → Security Reviewer → Supervisor → entrega. O Strategist também participa do motor antes do planejamento; nessa etapa não pode ampliar o escopo já autorizado.

Migração aditiva e idempotente em SQLite: `briefs`, `brief_versions`, `scope_approvals`, `visual_references`, `discovery_runs`. Os requisitos, recomendações, decisões e Design Brief são documentos JSON versionados; não dependem de tabelas separadas por tipo. `briefs.mission` associa uma concepção a uma única missão. Os arquivos ficam privados em `.factory/references/<brief_id>/`, com vínculo único e imutável à missão após encaminhamento. Nenhuma migração remove missões, eventos ou evidências.

Agentes disponíveis: Solution Strategist, Product Owner, Architect, Planner, Developer, Code Reviewer, QA, Security Reviewer e Supervisor. Visual Design Analyst é uma especialidade do Strategist, não um agente independente fictício. Agent Center reúne execuções de concepção e do motor, contagens e histórico, distingue agentes nunca executados e exibe resultados persistidos. Mission Control apresenta etapas, tarefas, dependências, critérios, logs, evidências e o documento de escopo aprovado.

## Imagens e segurança

Suporte atual: **PNG, JPEG e WebP estáticos**, oito arquivos por concepção, 5 MiB por arquivo, até 16 megapixels. Drag and drop, seleção múltipla, miniaturas autenticadas, ampliação e remoção antes da aprovação. O servidor verifica o decodificador real e o conteúdo completo, rejeita imagens animadas, conteúdo corrompido e decompression bombs, regrava como PNG RGB sem metadados ativos e mantém hashes do original e da representação armazenada. Nomes fornecidos pelo cliente nunca viram caminhos. Recuperação verifica integridade e associação ao briefing; não existe diretório público de uploads.

**SVG, PDF e vídeo estão indisponíveis nesta etapa**, explicitamente na interface e em `/api/capabilities`. SVG é recusado em vez de servir XML potencialmente ativo. A prioridade inicial foi a entrega segura de imagens raster; não há suporte fictício aos outros formatos.

A capacidade multimodal é consultada no App Server instalado, sem inferir suporte apenas pelo nome do modelo. O catálogo deste host anunciou `image` no modelo padrão; o schema instalado confirma `localImage`. O adaptador recertifica a modalidade na conexão que vai enviar as imagens. Sem modalidade anunciada, a proposta registra `visual_analysis.status=UNAVAILABLE`; com entrada enviada e resposta concluída, registra `ANALYZED`, modelo e IDs das referências. Falha no provedor fica como execução FAILED, sem fabricar análise.

O smoke real de visão desta sessão terminou em **timeout**. Portanto, o transporte está implementado, mas uma análise visual real concluída ainda precisa ser confirmada no host. A capacidade anunciada não equivale a uma execução bem-sucedida. Evidência em `logs/studio_vision_smoke.json`.

Referências são dados não confiáveis; seus textos e imagens não autorizam ferramentas, mudanças de segurança ou ampliação de escopo. O writer, isolamento, branch develop, validação de caminhos, limites de execução, certificação por escrita e evidências independentes permanecem ativos. Critérios de design incluem interpretação e adaptação; copiar marcas não é autorizado por anexar uma referência.

## Failed to fetch e conexão

Foram corrigidos caminhos concretos de falha encontrados no código:

- A conexão SQLite era aberta fora do tratamento de erro. Uma falha podia encerrar a conexão sem resposta HTTP. Agora retorna 503 estruturado; há teste que injeta essa falha.
- WAL e migrações eram repetidos em cada conexão de estado/SSE. Agora o servidor migra na inicialização e abre conexões leves nas requisições.
- Cada heartbeat disparava leitura completa do estado. Agora apenas eventos ou a renovação da conexão atualizam os dados, com cancelamento ao desmontar a tela, cursor preservado e timeout de 30 segundos sem heartbeat.
- O cliente não tinha timeout, deixava erros de conexão após recuperação e apresentava TypeError sem ação. Agora distingue rede, indisponibilidade, timeout, sessão/origem recusadas, erro operacional e resposta inválida. Erros operacionais não desaparecem durante atualização de conexão.
- A fila de conexões foi ampliada; conexões SSE e consultas simultâneas têm teste HTTP real.

A captura original não estava disponível como log de rede reproduzível; não é possível atribuí-la retrospectivamente a uma única causa comprovada. A correção cobre os defeitos encontrados e as regressões reproduzidas, sem relaxar autenticação, origem ou CSRF. Use Tentar novamente para rede e Reconectar sessão para uma chave antiga; após reiniciar o servidor, reabra o endereço atual.

## Verificação reproduzível

```powershell
python scripts/validate_studio.py
python -m scripts.smoke_vision
```

O primeiro executa suíte Python, React, ESLint, TypeScript/build e smoke HTTP em loopback com o banco existente. Não certifica nem executa missão de escrita. Relatório completo: `logs/studio_validation.json`. Smoke HTTP: `logs/studio_http_smoke.json`. O segundo é opcional e chama o modelo local em read-only com uma imagem sintética; não executa desenvolvimento. O schema real inspecionado ficou em `logs/app-server-schema/`.

A suíte cobre sessão/origem, autorização, indisponibilidade SQLite, concorrência estado/SSE, conteúdo e limites de upload, isolamento, integridade, remoção controlada, persistência, aprovação, versões obsoletas, transferência, vínculo dos IDs aprovados, visão e ausência de visão com provedores de teste, ordem real de chamadas do motor e regressão anterior. Mocks não equivalem a certificação ou execução real do modelo.

Validação final desta evolução: **104 testes Python, 18 testes React, ESLint, TypeScript, build de produção e smoke HTTP aprovados**, conforme `logs/studio_validation.json`. O timeout da visão real está documentado separadamente e não é apresentado como sucesso.

## Inspeção visual pendente e próximos passos

O host de navegador automatizado informou indisponibilidade. O controle nativo foi interrompido por não conseguir confirmar a URL com confiança. **Não houve validação visual real.** Inspeção manual preparada:

1. Abra a URL do inicializador, confira Dashboard e histórico; confirme a missão histórica concluída.
2. No Creator, crie uma ideia, arraste dois PNGs e confira miniaturas, ampliação, preferências e remoção. Tente um SVG e um arquivo renomeado como PNG; devem ser recusados.
3. Execute análise no host autenticado; se houver timeout, confira o erro e o histórico, sem proposta fictícia. Use revisão manual para exercitar aprovação independentemente do provedor.
4. Selecione somente uma funcionalidade; confira a versão e o Design Brief aprovado. Salve nova versão e confirme a exigência de nova aprovação.
5. Sem certificação atual, tente criar a missão: deve bloquear. Não iniciar escrita até executar diagnóstico/certificação válidos no host normal.
6. Confira Agent Center e Mission Control, largura desktop, janela estreita, contraste, navegação por Tab e estados vazios.
7. Pare o backend e confira mensagem de conexão; reinicie e use a nova URL/chave. Confirme reconexão SSE e ausência de erros antigos após recuperação.

Próximas validações: concluir o smoke real multimodal no host, inspecionar o layout visualmente e certificar o sandbox antes de uma missão de escrita. Evoluções de produto posteriores: edição das preferências já anexadas e revisão conversacional de requisitos, tratamento seguro de SVG, extração de PDF e pipeline de vídeo. A revisão estruturada atual é funcional, porém ainda exige JSON para alterações detalhadas de requisitos e design; respostas e decisões já podem ser registradas em linguagem natural.

## Interface (frontend/)

React 19 + TypeScript + Vite, servida pelo backend em produção. Direção visual **Mission Control** (grafite, ciano, dark).

- **Tailwind CSS 4** com tokens de design em `src/styles/index.css` (`@theme`): cores, fontes, raios e sombras num só lugar.
- **Componentes** no padrão shadcn/ui em `src/components/ui/` (Radix para o diálogo acessível, `cva` para variantes).
- **TanStack Query** guarda o estado; o laço de eventos SSE (`src/hooks/useFactory.tsx`) mantém reconexão e timeout de heartbeat.
- **React Router** (HashRouter): uma URL por tela e por missão (`#/missoes/<id>`).
- **React Hook Form + Zod** no formulário técnico, espelhando os limites do backend.
- **Motion** para transições sutis; **ECharts 6** só com dados reais; **Inter** e **JetBrains Mono** empacotadas (sem internet).
- Estrutura: `pages/` (6 telas), `components/layout/AppShell.tsx`, `lib/` (tipos e formatação), `api.ts`.

## Estrutura

- `epicbyte/`: motor, API, provedor Codex, segurança e Studio.
- `agents/`: instruções dos papéis.
- `frontend/`: interface React servida em produção pelo backend.
- `tests/`: suíte Python (`python -m unittest discover -s tests`).
- `missions/`: planos de exemplo.
- `legacy/`: Factory 1.x (`orchestrator/`, `test_codex.py`, `test_mission.py`, `sandbox_mission/`). Não é usada pelo motor atual e fica só como referência.

Gerados em execução e fora do Git: `.factory/` (SQLite e referências), `workspaces/` (repositórios das missões), `logs/`.


---

## Base 2.0 — Mission Control

Plataforma local de orquestração de agentes. React é a camada de operação; o backend Python existente continua responsável pelos estados, dependências, permissões, revisão, QA e escrita isolada. Sem publicação ou portas externas.

### Iniciar

Requer Python 3.11+, Git, Node.js 22+ e npm. Para executar agentes, requer Codex instalado e autenticado no mesmo contexto do processo.

No PowerShell normal do usuário, na raiz do projeto:

```powershell
python scripts/start_local.py
```

O comando instala dependências com `npm ci` quando necessário, compila o frontend e serve backend e interface de produção juntos em **127.0.0.1:8780**. Abra no navegador o endereço completo exibido no terminal, incluindo o fragmento de acesso da sessão. Não compartilhe esse endereço. O fragmento é removido da barra após leitura e a chave fica no sessionStorage desta aba; não é credencial do Codex. Reiniciar o servidor invalida as chaves anteriores.

Ctrl+C encerra o servidor, solicita pausa somente aos seus workers e termina suas árvores de processos se não encerrarem no prazo. Nenhum serviço externo ou servidor Vite adicional é necessário. Após interrupção forçada, locks são preservados: use `recover-lock` na CLI, que só libera PID comprovadamente ausente.

### Interface

- **Dashboard:** estados reais das missões, agentes em execução, tempo acumulado, indicadores de QA, atividade com ECharts e eventos recentes.
- **Mission Control:** objetivo, critérios, pipeline, dependências, tentativas, correções, logs e evidências de cada tarefa. Progresso significa tarefas APPROVED / total.
- **Agent Center:** os oito papéis existentes, suas instruções, execuções e resultados persistidos.
- **Mission Creator:** nome, objetivo, critérios, restrições, workspace gerenciado, duração e limite de execuções. Dry-run vem habilitado e não cria workspace nem chama provedor. Desmarque para criar; o início é uma operação explícita posterior.
- **Execution History:** missões, tarefas, tentativas, relatórios, testes reais do QA e erros.
- **Settings:** diagnóstico atual, disponibilidade de autenticação sem credenciais, sandbox, limites e versões.

Iniciar e retomar passam por autenticação do Codex, validação de estado, branch e isolamento atual. O motor e o writer recertificam antes das escritas. O botão de pausa solicita cancelamento cooperativo ao provedor e o motor respeita a pausa entre chamadas. Uma tarefa em execução pode deixar alterações parciais, registradas nos snapshots; não existe rollback automático. Retomar missões bloqueadas não remove locks, não reinicia contadores e não ignora as regras de recuperação existentes.

### Segurança

A API usa HTTPServer com threads, conexões SQLite independentes por requisição e um subprocesso Python do motor existente por missão. O banco permanece `.factory/factory.sqlite3`, com migração aditiva `mission_limits`; os limites do formulário sobrevivem ao reinício e à retomada pela CLI.

Todas as rotas novas `/api/*` exigem uma chave aleatória de sessão no cabeçalho Authorization. Cada POST também exige origem exata, Host local e JSON, com limite de corpo e autorização de estado/operação. O cliente usa cabeçalho explícito, sem cookies de autenticação; requisições de formulário e origens externas não recebem autorização. CORS não é usado como substituto de autenticação. CSP e Referrer-Policy são enviados para os assets locais. A API só vincula 127.0.0.1.

As rotas legadas somente leitura `/missions`, `/missions/<id>` e `/missions/<id>/events` preservam o contrato anterior: acesso local sem chave, com bloqueio de Origin e Host externos. Não há mutações nessas rotas. O perfil é de operador local único, sem contas remotas ou ACL multiusuário.

O formulário recebe apenas o identificador `managed`. O backend gera um workspace novo sob `workspaces/`, inicializa Git em `develop` e recusa caminhos fornecidos pelo cliente. O projeto principal não tem `.git`; nenhuma branch main foi alterada. Os repositórios existentes nos workspaces foram preservados.

O backend de escrita original permanece: Developer em sessão read-only retorna edições estruturadas, writer fixo executa no sandbox oficial sem rede e sem permissões de escrita nos metadados. Exige raiz Git exata e branch develop; recusa main, HEAD destacado, traversal, aliases Windows, ADS, hardlinks, symlinks e junctions. Não há opção de ignorar certificação. Os probes usam apenas alvos descartáveis.

SQLite preserva estados, execuções, eventos, locks, checkpoints e evidências. Aprovação exige sessões independentes de Developer, Code Reviewer, Security Reviewer e QA da tentativa atual; QA precisa de comandos reais concluídos com código zero. Supervisor decide a conclusão da missão. Nenhum mock foi introduzido no fluxo de produção.

### Atualizações e contratos

- `GET /api/state`: missões com tarefas, eventos recentes, execuções, evidências, agentes, diagnóstico, workspaces e limites.
- `GET /api/events?after=<seq>`: SSE com IDs monotônicos, heartbeat e reconexão por cursor. Conexões são renovadas em até 20 segundos; o cliente mantém Authorization no fetch streaming e atualiza os dados durante heartbeats.
- `POST /api/missions`: valida dry-run ou cria missão após certificação. Limites aceitos: `max_executions` 1–100 e `mission_timeout` 1–3600 segundos. Workspace deve ser `managed`.
- `POST /api/missions/<id>/start`, `/pause`, `/resume`: controles com autorização por estado. Não existe controle de exclusão.
- `POST /api/diagnostic`: executa diagnóstico atual sem chamar modelo; não persiste credenciais nem reutiliza certificação histórica.

Os POSTs aceitam apenas `Content-Type: application/json`. Erros operacionais usam JSON e status 409; autenticação/origem inválidas retornam 403. O diagnóstico é intencionalmente não certificado ao reiniciar o servidor.

### Testes e segunda missão

Comando completo no PowerShell normal:

```powershell
python scripts/validate_integration.py
```

Executa a regressão Python, ESLint, testes React e build de produção; certifica novamente o isolamento e só então prepara e executa uma nova missão com o plano `missions/task_manager_plan.json`. Falha em qualquer etapa interrompe antes da missão. O relatório fica em `logs/integration_validation.json`.

A missão possui três tarefas dependentes: biblioteca Python com persistência JSON; CLI e testes de subprocesso; documentação e integração. Cada tarefa passa pelo fluxo existente de revisão, segurança e QA; o Supervisor avalia a entrega final. Exige cadastro, listagem, conclusão idempotente, exclusão lógica, persistência atômica e tratamento de JSON inválido sem sobrescrever dados. Não testa operações destrutivas.

Verificações individuais:

```powershell
python -m unittest discover -s tests -v
npm --prefix frontend run lint
npm --prefix frontend test
npm --prefix frontend run build
python factory.py doctor --probe
```

Testes de API usam servidor HTTP real em loopback e SQLite temporário. Mocks ficam restritos aos testes de processos, provedor e certificação; testes unitários nunca equivalem a certificação real.

### Evidências e limitações desta execução

A missão histórica `mission_b6aa1e7ff549` e seus arquivos foram preservados. O diagnóstico atual está em `logs/mission_control_doctor.json`: `CreateRestrictedToken failed: 87`, certificação falsa e conta indisponível neste processo. A missão nova não foi iniciada. O relatório completo atualizado é `logs/integration_validation.json`.

O navegador automatizado retornou `The browser access host is unavailable`; a inspeção visual desktop/mobile ficou pendente. Componentes, operações HTTP, TypeScript, ESLint e build são verificados separadamente. A interface foi implementada com layout responsivo e estados vazios, mas isso não substitui inspeção visual humana.

O teste de diagnóstico que lia o banco real foi isolado em diretório temporário, evitando confundir autenticação simulada com a missão histórica real já concluída. Os demais mecanismos de segurança e contratos da CLI foram preservados.

### CLI preservada

```powershell
python factory.py status
python factory.py status <mission_id>
python factory.py logs <mission_id>
python factory.py pause <mission_id>
python factory.py resume <mission_id>
python factory.py recover-lock <mission_id>
python factory.py dry-run missions/task_manager.md --plan missions/task_manager_plan.json
python factory.py serve --port 8780
```

Os scripts legados `legacy/test_codex.py` e `legacy/test_mission.py` chamam modelo e não integram a suíte unitária. `scripts/validate_write_host.py` permanece disponível para a missão anterior da calculadora. Não houve push, deploy, troca de credenciais ou alteração global de permissões.

Validação final desta implementação: **80 testes Python e 7 testes React aprovados**, ESLint e build TypeScript/Vite aprovados. O smoke HTTP com o SQLite real retornou 200 para HTML, estado e SSE; encontrou oito agentes e preservou a missão histórica concluída. O encerramento do inicializador deixou a porta 8780 fechada. Evidências: `logs/integration_validation.json` e `logs/mission_control_http.json`. A saída 2 do validador completo indica a interrupção esperada na certificação, não sucesso da missão de integração.
