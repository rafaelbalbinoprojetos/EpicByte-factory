import {motion} from 'motion/react';
import {Button} from '@/components/ui/button';

/** Página inicial de exemplo. Substitua pelo conteúdo do projeto. */
export function App() {
  return (
    <main className="grid min-h-screen place-items-center px-6">
      <motion.section initial={{opacity: 0, y: 12}} animate={{opacity: 1, y: 0}} transition={{duration: 0.5}} className="max-w-xl text-center">
        <h1 className="text-4xl font-semibold tracking-tight md:text-5xl">Projeto EpicByte</h1>
        <p className="mt-4 text-ink-muted">Base pronta: React, TypeScript, Tailwind 4, Motion e GSAP.</p>
        <Button className="mt-8">Começar</Button>
      </motion.section>
    </main>
  );
}
