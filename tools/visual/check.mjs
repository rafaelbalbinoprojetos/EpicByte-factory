// Verificação visual de um site gerado pela fábrica.
// Uso: node check.mjs <url> <pasta-de-saida>
// Imprime um JSON com o resultado. Só acessa 127.0.0.1: qualquer outra requisição é bloqueada.
import {chromium} from 'playwright';
import AxeBuilder from '@axe-core/playwright';
import {mkdirSync, writeFileSync} from 'node:fs';
import {join} from 'node:path';

const [url, outDir] = process.argv.slice(2);
mkdirSync(outDir, {recursive: true});
const WIDTHS = [360, 768, 1280, 1920];
const result = {url, widths: [], console_errors: [], failed_requests: [], blocked_external: [], accessibility: {}, keyboard: {}, reduced_motion: {}};

const browser = await chromium.launch();
try {
  const context = await browser.newContext({deviceScaleFactor: 1});
  await context.route('**/*', route => {
    const target = new URL(route.request().url());
    if (['127.0.0.1', 'localhost'].includes(target.hostname) || target.protocol === 'data:') return route.continue();
    result.blocked_external.push(target.origin);
    return route.abort();
  });
  const page = await context.newPage();
  page.on('console', msg => { if (msg.type() === 'error') result.console_errors.push(msg.text().slice(0, 300)); });
  page.on('pageerror', err => result.console_errors.push(String(err).slice(0, 300)));
  page.on('response', res => { if (res.status() >= 400) result.failed_requests.push(`${res.status()} ${new URL(res.url()).pathname}`); });

  for (const width of WIDTHS) {
    await page.setViewportSize({width, height: width < 768 ? 800 : 900});
    await page.goto(url, {waitUntil: 'networkidle'});
    await page.waitForTimeout(600);
    const metrics = await page.evaluate(() => {
      const w = document.documentElement.clientWidth;
      const wide = [...document.querySelectorAll('body *')]
        .filter(e => e.getBoundingClientRect().right > w + 1 && getComputedStyle(e).position !== 'fixed')
        .slice(0, 5).map(e => `${e.tagName.toLowerCase()}${e.id ? '#' + e.id : ''}.${String(e.className).split(' ').slice(0, 3).join('.')}`);
      const images = [...document.images].map(i => ({src: i.getAttribute('src'), ok: i.complete && i.naturalWidth > 0, alt: i.getAttribute('alt')}));
      return {scroll_width: document.documentElement.scrollWidth, viewport: w, overflow: document.documentElement.scrollWidth > w + 1, wide_elements: wide,
              h1: document.querySelectorAll('h1').length, broken_images: images.filter(i => !i.ok).map(i => i.src), images_without_alt: images.filter(i => i.alt === null).map(i => i.src),
              page_height: document.documentElement.scrollHeight};
    });
    const shot = join(outDir, `largura-${width}.png`);
    await page.screenshot({path: shot, fullPage: false});
    result.widths.push({width, screenshot: shot, ...metrics});
  }

  await page.setViewportSize({width: 1280, height: 900});
  await page.goto(url, {waitUntil: 'networkidle'});
  const axe = await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  const serious = axe.violations.filter(v => ['serious', 'critical'].includes(v.impact));
  result.accessibility = {
    serious_or_critical: serious.length,
    violations: axe.violations.map(v => ({id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length, example: v.nodes[0]?.target?.join(' ')})).slice(0, 15),
  };

  const focus = [];
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press('Tab');
    focus.push(await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body) return null;
      const style = getComputedStyle(el);
      const visible = style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) > 0 || style.boxShadow !== 'none';
      return {element: `${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}`, name: (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 40), focus_visible: visible};
    }));
  }
  const reached = focus.filter(Boolean);
  result.keyboard = {focusable_reached: reached.length, without_visible_focus: reached.filter(f => !f.focus_visible).map(f => f.element + ' ' + f.name), order: reached.map(f => f.name)};

  const reduced = await browser.newContext({reducedMotion: 'reduce', viewport: {width: 1280, height: 900}});
  await reduced.route('**/*', route => (['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort()));
  const rpage = await reduced.newPage();
  await rpage.goto(url, {waitUntil: 'networkidle'});
  await rpage.waitForTimeout(400);
  result.reduced_motion = await rpage.evaluate(() => {
    const running = document.getAnimations().filter(a => a.playState === 'running' && (a.effect?.getTiming().duration ?? 0) > 50);
    return {running_animations: running.length};
  });
  await rpage.screenshot({path: join(outDir, 'movimento-reduzido.png')});
} finally {
  await browser.close();
}

const problems = [];
for (const w of result.widths) {
  if (w.overflow) problems.push(`Rolagem horizontal em ${w.width}px (${w.scroll_width}px de conteúdo): ${w.wide_elements.join(', ')}`);
  if (w.broken_images.length) problems.push(`Imagens quebradas em ${w.width}px: ${w.broken_images.join(', ')}`);
}
if (result.widths[0] && result.widths[0].h1 !== 1) problems.push(`A página tem ${result.widths[0].h1} h1 (precisa de exatamente 1)`);
if (result.console_errors.length) problems.push(`Erros no console: ${[...new Set(result.console_errors)].slice(0, 5).join(' | ')}`);
if (result.failed_requests.length) problems.push(`Recursos não encontrados: ${[...new Set(result.failed_requests)].slice(0, 5).join(', ')}`);
if (result.accessibility.serious_or_critical) problems.push(`Acessibilidade (axe): ${result.accessibility.violations.filter(v => ['serious', 'critical'].includes(v.impact)).map(v => `${v.id} (${v.help}; ex.: ${v.example})`).join(' | ')}`);
if (result.keyboard.without_visible_focus.length) problems.push(`Foco invisível no teclado: ${result.keyboard.without_visible_focus.slice(0, 5).join(', ')}`);
if (result.reduced_motion.running_animations) problems.push(`${result.reduced_motion.running_animations} animações rodando com prefers-reduced-motion ativado`);
result.passed = problems.length === 0;
result.problems = problems;
writeFileSync(join(outDir, 'resultado.json'), JSON.stringify(result, null, 2));
console.log(JSON.stringify(result));
