'use client';

import { useEffect, useState } from 'react';
import { useTheme } from 'next-themes';
import { MoonIcon, SunIcon } from '@phosphor-icons/react';
import { cn } from '@/lib/shadcn/utils';

interface ThemeToggleProps {
  className?: string;
}

/** A quiet two-state switch between the day and night ledger. */
export function ThemeToggle({ className }: ThemeToggleProps) {
  const { resolvedTheme, setTheme } = useTheme();
  // The resolved theme is only known on the client, so hold the theme-specific
  // icon/label until after mount to avoid a hydration mismatch.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const isDark = resolvedTheme === 'dark';

  return (
    <button
      type="button"
      onClick={() => setTheme(isDark ? 'light' : 'dark')}
      aria-label={
        !mounted ? 'Toggle theme' : isDark ? 'Switch to light theme' : 'Switch to dark theme'
      }
      className={cn(
        'border-border text-muted-foreground hover:text-foreground flex size-8 items-center justify-center rounded-full border transition-colors',
        className
      )}
    >
      {mounted &&
        (isDark ? (
          <SunIcon size={15} weight="bold" />
        ) : (
          <MoonIcon size={15} weight="bold" />
        ))}
    </button>
  );
}
