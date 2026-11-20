import {forwardRef, type ButtonHTMLAttributes} from 'react';
import {Slot} from '@radix-ui/react-slot';
import {cva, type VariantProps} from 'class-variance-authority';
import {cn} from '@/lib/cn';

export const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-(--radius-control) text-[13px] font-semibold transition-[filter,background-color,border-color] duration-150 cursor-pointer disabled:cursor-not-allowed disabled:opacity-40 [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        primary: 'border border-accent bg-accent text-accent-ink hover:enabled:brightness-110',
        secondary: 'border border-[#304457] bg-surface-2 text-[#afc5da] hover:enabled:border-accent-line hover:enabled:text-ink-strong',
        ghost: 'border border-transparent bg-transparent text-ink-soft hover:enabled:text-ink-strong',
        link: 'border-0 bg-transparent p-0 text-[12px] font-medium text-[#65b8d0] hover:enabled:text-accent-strong',
      },
      size: {
        md: 'h-10 px-4',
        sm: 'h-8 px-3 text-[12px]',
        icon: 'h-8 w-8 p-0',
        none: '',
      },
    },
    defaultVariants: {variant: 'primary', size: 'md'},
  },
);

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants> & {asChild?: boolean};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(({className, variant, size, asChild, ...props}, ref) => {
  const Component = asChild ? Slot : 'button';
  const resolvedSize = size ?? (variant === 'link' ? 'none' : undefined);
  return <Component ref={ref} className={cn(buttonVariants({variant, size: resolvedSize}), className)} {...props} />;
});
Button.displayName = 'Button';
