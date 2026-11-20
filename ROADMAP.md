# Roadmap — EpicByte Factory

**Objetivo final:** descrever um software, sistema ou landing page na interface; a fábrica pergunta o que falta, o cliente aprova, os agentes constroem, testam e revisam, e o resultado abre funcionando.

Cada marco entrega algo que funciona de ponta a ponta antes do próximo.

## Marco 1 — Provar o ciclo completo
- [x] Missão pequena (Python, sem npm) executada até COMPLETED — `mission_a17ffc008803`, 4 tarefas aprovadas de primeira
- [x] Corrigir o que quebrar no caminho: porta 8765 em conflito (agora 8780); agentes sem Python/Git/Node no PATH; QA reprovava tarefa correta por comando fora do escopo
- [ ] Commitar o trabalho aprovado no workspace (hoje os arquivos ficam não rastreados na `develop`)
- [ ] Product Owner deve ampliar critérios literais (a CLI pedida só com `100 C F` saiu só C→F)
- [ ] Dashboard: não mostrar "Certificação necessária" como bloqueio logo após reiniciar; rodar o diagnóstico ao subir
- [ ] Arquivar as missões pausadas antigas

**Pronto quando:** uma missão criada na tela termina COMPLETED com código no workspace e testes verdes.

## Marco 2 — Projetos web
- [ ] Templates prontos (Vite + React + TypeScript com testes)
- [ ] Instalação controlada: o motor (não o agente) roda `npm ci` a partir do lockfile, com lock por projeto
- [ ] Verificações: typecheck, lint, testes, build, `npm audit`, e2e simples, gravadas como evidência do QA
- [ ] Pré-visualização: porta própria por projeto e botão "Abrir site"

**Pronto quando:** uma landing page simples termina com o site abrindo pelo botão e verificações verdes.

## Marco 3 — Agentes especialistas
- [ ] Frontend Developer (UI, responsividade, acessibilidade, animação)
- [ ] Design Reviewer (screenshots celular/desktop comparados ao Design Brief)
- [ ] Instruções por tipo de projeto (landing, sistema, API)
- [ ] Limites de tempo/execuções maiores para projetos grandes

## Marco 4 — Interface como central de produção
- [ ] Tela de Projetos: screenshots, verificações, README, Abrir site, Rodar verificações
- [ ] Painel ao vivo dos agentes
- [ ] Perguntas e aprovações na própria tela

## Marco 5 — Crescer
- [ ] Radar de oportunidades (Market Scout) com botão "virar missão"
- [ ] Escolher a IA por missão (Codex ou Claude)
- [ ] Métricas de custo, tempo e aprovação por agente

## Princípios
- Codex nos marcos 1–3 (sandbox certificado, assinatura existente); Claude como opção no marco 5.
- Uma interface só: evoluir o Mission Control.
- Agentes nunca têm internet nem escrevem fora do workspace; só o motor instala pacotes, de forma controlada.
