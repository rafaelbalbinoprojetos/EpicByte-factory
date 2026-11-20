# EpicByte Factory 2.1

A evolução atual está documentada em [README-2.1.md](README-2.1.md), incluindo instalação, fluxo de aprovação, suporte real a imagens, correções de API e limitações verificadas. Os resultados reproduzíveis ficam em `logs/studio_validation.json`.

A documentação abaixo descreve a base 2.0 preservada e suas validações históricas.

# EpicByte Factory 2.0 — Mission Control

Plataforma local de orquestração de agentes. React é a camada de operação; o backend Python existente continua responsável pelos estados, dependências, permissões, revisão, QA e escrita isolada. Sem publicação ou portas externas.

## Iniciar

Requer Python 3.11+, Git, Node.js 22+ e npm. Para executar agentes, requer Codex instalado e autenticado no mesmo contexto do processo.

No PowerShell normal do usuário, na raiz do projeto:

```powershell
python scripts/start_local.py
```

O comando instala dependências com `npm ci` quando necessário, compila o frontend e serve backend e interface de produção juntos em **127.0.0.1:8765**. Abra no navegador o endereço completo exibido no terminal, incluindo o fragmento de acesso da sessão. Não compartilhe esse endereço. O fragmento é removido da barra após leitura e a chave fica no sessionStorage desta aba; não é credencial do Codex. Reiniciar o servidor invalida as chaves anteriores.

Ctrl+C encerra o servidor, solicita pausa somente aos seus workers e termina suas árvores de processos se não encerrarem no prazo. Nenhum serviço externo ou servidor Vite adicional é necessário. Após interrupção forçada, locks são preservados: use `recover-lock` na CLI, que só libera PID comprovadamente ausente.

## Interface

- **Dashboard:** estados reais das missões, agentes em execução, tempo acumulado, indicadores de QA, atividade com ECharts e eventos recentes.
- **Mission Control:** objetivo, critérios, pipeline, dependências, tentativas, correções, logs e evidências de cada tarefa. Progresso significa tarefas APPROVED / total.
- **Agent Center:** os oito papéis existentes, suas instruções, execuções e resultados persistidos.
- **Mission Creator:** nome, objetivo, critérios, restrições, workspace gerenciado, duração e limite de execuções. Dry-run vem habilitado e não cria workspace nem chama provedor. Desmarque para criar; o início é uma operação explícita posterior.
- **Execution History:** missões, tarefas, tentativas, relatórios, testes reais do QA e erros.
- **Settings:** diagnóstico atual, disponibilidade de autenticação sem credenciais, sandbox, limites e versões.

Iniciar e retomar passam por autenticação do Codex, validação de estado, branch e isolamento atual. O motor e o writer recertificam antes das escritas. O botão de pausa solicita cancelamento cooperativo ao provedor e o motor respeita a pausa entre chamadas. Uma tarefa em execução pode deixar alterações parciais, registradas nos snapshots; não existe rollback automático. Retomar missões bloqueadas não remove locks, não reinicia contadores e não ignora as regras de recuperação existentes.

## Segurança

A API usa HTTPServer com threads, conexões SQLite independentes por requisição e um subprocesso Python do motor existente por missão. O banco permanece `.factory/factory.sqlite3`, com migração aditiva `mission_limits`; os limites do formulário sobrevivem ao reinício e à retomada pela CLI.

Todas as rotas novas `/api/*` exigem uma chave aleatória de sessão no cabeçalho Authorization. Cada POST também exige origem exata, Host local e JSON, com limite de corpo e autorização de estado/operação. O cliente usa cabeçalho explícito, sem cookies de autenticação; requisições de formulário e origens externas não recebem autorização. CORS não é usado como substituto de autenticação. CSP e Referrer-Policy são enviados para os assets locais. A API só vincula 127.0.0.1.

As rotas legadas somente leitura `/missions`, `/missions/<id>` e `/missions/<id>/events` preservam o contrato anterior: acesso local sem chave, com bloqueio de Origin e Host externos. Não há mutações nessas rotas. O perfil é de operador local único, sem contas remotas ou ACL multiusuário.

O formulário recebe apenas o identificador `managed`. O backend gera um workspace novo sob `workspaces/`, inicializa Git em `develop` e recusa caminhos fornecidos pelo cliente. O projeto principal não tem `.git`; nenhuma branch main foi alterada. Os repositórios existentes nos workspaces foram preservados.

O backend de escrita original permanece: Developer em sessão read-only retorna edições estruturadas, writer fixo executa no sandbox oficial sem rede e sem permissões de escrita nos metadados. Exige raiz Git exata e branch develop; recusa main, HEAD destacado, traversal, aliases Windows, ADS, hardlinks, symlinks e junctions. Não há opção de ignorar certificação. Os probes usam apenas alvos descartáveis.

SQLite preserva estados, execuções, eventos, locks, checkpoints e evidências. Aprovação exige sessões independentes de Developer, Code Reviewer, Security Reviewer e QA da tentativa atual; QA precisa de comandos reais concluídos com código zero. Supervisor decide a conclusão da missão. Nenhum mock foi introduzido no fluxo de produção.

## Atualizações e contratos

- `GET /api/state`: missões com tarefas, eventos recentes, execuções, evidências, agentes, diagnóstico, workspaces e limites.
- `GET /api/events?after=<seq>`: SSE com IDs monotônicos, heartbeat e reconexão por cursor. Conexões são renovadas em até 20 segundos; o cliente mantém Authorization no fetch streaming e atualiza os dados durante heartbeats.
- `POST /api/missions`: valida dry-run ou cria missão após certificação. Limites aceitos: `max_executions` 1–100 e `mission_timeout` 1–3600 segundos. Workspace deve ser `managed`.
- `POST /api/missions/<id>/start`, `/pause`, `/resume`: controles com autorização por estado. Não existe controle de exclusão.
- `POST /api/diagnostic`: executa diagnóstico atual sem chamar modelo; não persiste credenciais nem reutiliza certificação histórica.

Os POSTs aceitam apenas `Content-Type: application/json`. Erros operacionais usam JSON e status 409; autenticação/origem inválidas retornam 403. O diagnóstico é intencionalmente não certificado ao reiniciar o servidor.

## Testes e segunda missão

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

## Evidências e limitações desta execução

A missão histórica `mission_b6aa1e7ff549` e seus arquivos foram preservados. O diagnóstico atual está em `logs/mission_control_doctor.json`: `CreateRestrictedToken failed: 87`, certificação falsa e conta indisponível neste processo. A missão nova não foi iniciada. O relatório completo atualizado é `logs/integration_validation.json`.

O navegador automatizado retornou `The browser access host is unavailable`; a inspeção visual desktop/mobile ficou pendente. Componentes, operações HTTP, TypeScript, ESLint e build são verificados separadamente. A interface foi implementada com layout responsivo e estados vazios, mas isso não substitui inspeção visual humana.

O teste de diagnóstico que lia o banco real foi isolado em diretório temporário, evitando confundir autenticação simulada com a missão histórica real já concluída. Os demais mecanismos de segurança e contratos da CLI foram preservados.

## CLI preservada

```powershell
python factory.py status
python factory.py status <mission_id>
python factory.py logs <mission_id>
python factory.py pause <mission_id>
python factory.py resume <mission_id>
python factory.py recover-lock <mission_id>
python factory.py dry-run missions/task_manager.md --plan missions/task_manager_plan.json
python factory.py serve --port 8765
```

Os scripts legados `test_codex.py` e `test_mission.py` chamam modelo e não integram a suíte unitária. `scripts/validate_write_host.py` permanece disponível para a missão anterior da calculadora. Não houve push, deploy, troca de credenciais ou alteração global de permissões.

Validação final desta implementação: **80 testes Python e 7 testes React aprovados**, ESLint e build TypeScript/Vite aprovados. O smoke HTTP com o SQLite real retornou 200 para HTML, estado e SSE; encontrou oito agentes e preservou a missão histórica concluída. O encerramento do inicializador deixou a porta 8765 fechada. Evidências: `logs/integration_validation.json` e `logs/mission_control_http.json`. A saída 2 do validador completo indica a interrupção esperada na certificação, não sucesso da missão de integração.
