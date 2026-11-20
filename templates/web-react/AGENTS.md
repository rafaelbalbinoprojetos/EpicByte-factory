# Padrão EpicByte para sites e landing pages

Você trabalha num projeto **React 19 + TypeScript + Vite + Tailwind CSS 4**. O resultado precisa parecer feito por um estúdio profissional, não por um gerador.

## Stack disponível (não há outras dependências)
- `react`, `react-dom`
- `tailwindcss` 4 (tokens em `src/styles.css`, bloco `@theme`)
- `motion` (`import {motion} from 'motion/react'`): entradas, hover e transições
- `gsap` (com `gsap/ScrollTrigger`): animações ligadas à rolagem e sequências
- `lucide-react`: ícones
- `clsx`, `tailwind-merge` (`cn` em `src/lib/cn.ts`) e `class-variance-authority` (variantes, ver `src/components/ui/button.tsx`)
- `@fontsource-variable/inter` (outras fontes não estão instaladas; não importe do Google Fonts)
- Testes: `vitest` + `@testing-library/react` + `@testing-library/jest-dom`

**Proibido:** alterar `package.json`, `package-lock.json` ou `.npmrc`, ou importar pacotes que não estão acima. O motor recusa e a tarefa falha.

## Estrutura
- `src/App.tsx`: composição da página (só monta as seções)
- `src/sections/<Nome>.tsx`: uma seção por arquivo (Hero, Sobre, Serviços, Depoimentos, FAQ, Contato, Rodapé…)
- `src/components/ui/`: componentes reutilizáveis (botão, card, campo)
- `src/content/site.ts`: **todo o texto e os dados** (nome, telefone, WhatsApp, itens de listas), sem texto espalhado nas seções
- `src/styles.css`: tokens de design; ajuste o `@theme` para a identidade do projeto
- `public/assets/`: imagens fornecidas (use `./assets/arquivo.png` no `src` das imagens)
- Testes ao lado do código: `Nome.test.tsx`

## Padrão de qualidade (obrigatório)
1. **Responsivo de 360px a 1920px**, mobile-first, sem rolagem horizontal. Teste mentalmente 360, 768, 1280 e 1920.
2. **Acessibilidade:** HTML semântico (`header`, `main`, `section` com `aria-labelledby`, `footer`), um único `h1`, hierarquia de títulos, `alt` descritivo, contraste AA, foco visível, botões de verdade para ações e links para navegação.
3. **Movimento com respeito:** animações sutis e com propósito; respeite `prefers-reduced-motion` (Motion: `useReducedMotion`; GSAP: não registrar animações quando o usuário pedir menos movimento). Nada pisca mais de 3 vezes por segundo.
4. **Performance:** imagens com `width`/`height` e `loading="lazy"` fora da primeira dobra; o hero com `fetchPriority="high"`; nada de bibliotecas pesadas além das listadas.
5. **SEO básico:** `<title>` e `<meta name="description">` reais em `index.html`; `lang="pt-BR"`.
6. **Conteúdo honesto:** dados fictícios ficam marcados como exemplo em `site.ts`; nunca invente números, prêmios ou depoimentos como se fossem reais.
7. **Visual:** hierarquia tipográfica clara, espaçamento generoso e consistente (escala do Tailwind), no máximo 2 famílias e 1 cor de destaque principal. Evite gradientes e brilhos em excesso.

## Código
- TypeScript estrito; sem `any`; componentes funcionais; exports nomeados.
- Estilo só com classes do Tailwind e tokens do `@theme` (sem CSS inline, exceto valores dinâmicos).
- GSAP dentro de `useEffect`/`useLayoutEffect` com limpeza (`ctx.revert()`).

## Verificações (rodadas pelo motor depois de cada entrega)
`npm run typecheck`, `npm run lint`, `npm run test`, `npm run build` e `npm audit`. **Todas precisam passar.** Cada seção nova precisa de ao menos um teste que verifique o conteúdo principal e a acessibilidade básica (papel e nome do título).
