import type {ButtonHTMLAttributes} from 'react';
import {cva, type VariantProps} from 'class-variance-authority';
import {cn} from '@/lib/cn';

export const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 rounded-full font-semibold transition-[filter,background-color] duration-200 cursor-pointer disabled:cursor-not-allowed disabled:opacity-50',
  {
    variants: {
      variant: {
        primary: 'bg-accent text-accent-ink hover:brightness-110',
        outline: 'border border-ink/25 text-ink hover:border-accent hover:text-accent',
      },
      size: {md: 'h-11 px-6 text-sm', lg: 'h-13 px-8 text-base'},
    },
    defaultVariants: {variant: 'primary', size: 'md'},
  },
);

type Props = ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants>;

export function Button({className, variant, size, ...props}: Props) {
  return <button className={cn(buttonVariants({variant, size}), className)} {...props} />;
}
