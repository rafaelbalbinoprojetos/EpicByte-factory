import * as Dialog from '@radix-ui/react-dialog';
import {X} from 'lucide-react';
import type {ReactNode} from 'react';
import {Button} from './button';

/** Diálogo acessível (Radix): foco preso, Esc fecha, leitor de tela anuncia o título. */
export function Modal({open, title, onClose, children}: {open: boolean; title: string; onClose: () => void; children: ReactNode}) {
  return (
    <Dialog.Root open={open} onOpenChange={value => !value && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[#030910c9] backdrop-blur-[6px]" />
        <Dialog.Content
          aria-describedby={undefined}
          className="fixed left-1/2 top-1/2 z-50 max-h-[88vh] w-[min(900px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-(--radius-card) border border-line-strong bg-surface p-6 shadow-(--shadow-card)"
        >
          <div className="mb-4 flex items-center justify-between gap-3">
            <Dialog.Title className="m-0 text-[15px] font-semibold text-ink-strong">{title}</Dialog.Title>
            <Dialog.Close asChild>
              <Button variant="ghost" size="icon" aria-label="Fechar">
                <X size={18} />
              </Button>
            </Dialog.Close>
          </div>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
