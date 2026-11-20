# EpicByte Factory 2.1 — Intelligent Product Studio

Implementação incremental sobre a Factory 2.0. O backend continua sendo a autoridade de execução. Não houve reconstrução, deploy, push, alteração de credenciais ou execução de missões de escrita nesta evolução. O projeto principal não possui `.git`; repositórios e branches dos workspaces existentes foram preservados.

## Iniciar

```powershell
cd C:\Projetos\EpicByte-Factory
python -m pip install -r requirements.txt
python scripts/start_local.py
```

Abra **o endereço completo exibido pelo servidor**, em `http://127.0.0.1:8765`, com o fragmento temporário da sessão. Não use `localhost`, a porta de desenvolvimento Vite ou uma chave de servidor anterior. A proteção de Host e Origin permanece exata; não foi habilitado CORS externo. A interface e a API são servidas juntas. O primeiro comando só é necessário para preparar a dependência Pillow de validação de imagens.

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
