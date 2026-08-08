'use client';

import { AnimatePresence, motion } from 'motion/react';
import { useAgent } from '@livekit/components-react';
import { cn } from '@/lib/shadcn/utils';

type StatusTone = 'listening' | 'speaking' | 'thinking' | 'neutral';

interface StatusInfo {
  label: string;
  tone: StatusTone;
}

/** Map the raw agent state to a clear, human-readable status. */
function getStatus(state: string): StatusInfo | null {
  switch (state) {
    case 'initializing':
    case 'connecting':
      return { label: 'Getting ready', tone: 'neutral' };
    case 'pre-connect-buffering':
    case 'idle':
    case 'listening':
      return { label: 'Listening to you', tone: 'listening' };
    case 'thinking':
      return { label: 'Thinking', tone: 'thinking' };
    case 'speaking':
      return { label: 'Dhan Saathi speaking', tone: 'speaking' };
    default:
      return null;
  }
}

/** Small bouncing bars — the agent's "voice" glyph. */
function SpeakingBars() {
  return (
    <span className="flex items-center gap-[3px]" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="bg-ink w-[3px] rounded-full"
          animate={{ height: [5, 13, 5] }}
          transition={{ duration: 0.7, repeat: Infinity, ease: 'easeInOut', delay: i * 0.15 }}
        />
      ))}
    </span>
  );
}

/**
 * Always makes it clear who holds the line right now — the Listening and
 * Speaking states required for Day 3, in the ledger's mono voice.
 */
export function AgentStatusPill({ className }: { className?: string }) {
  const { state } = useAgent();
  const status = getStatus(state);

  return (
    <div className={cn('flex h-6 items-center justify-center', className)}>
      <AnimatePresence mode="wait">
        {status && (
          <motion.div
            key={status.label}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.25 }}
            aria-live="polite"
            className="flex items-center gap-2.5"
          >
            {status.tone === 'speaking' && <SpeakingBars />}
            {status.tone === 'listening' && (
              <motion.span
                aria-hidden="true"
                className="bg-brass size-2 rounded-full"
                animate={{ scale: [1, 1.5, 1], opacity: [0.5, 1, 0.5] }}
                transition={{ duration: 1.4, repeat: Infinity, ease: 'easeInOut' }}
              />
            )}
            {(status.tone === 'thinking' || status.tone === 'neutral') && (
              <span className="flex items-center gap-1" aria-hidden="true">
                {[0, 1, 2].map((i) => (
                  <motion.span
                    key={i}
                    className="bg-ink-soft size-1.5 rounded-full"
                    animate={{ opacity: [0.3, 1, 0.3] }}
                    transition={{ duration: 1, repeat: Infinity, ease: 'easeInOut', delay: i * 0.2 }}
                  />
                ))}
              </span>
            )}
            <span
              className={cn(
                'font-mono text-[11px] font-medium tracking-[0.2em] uppercase',
                status.tone === 'speaking' && 'text-ink',
                status.tone === 'listening' && 'text-brass',
                (status.tone === 'thinking' || status.tone === 'neutral') && 'text-muted-foreground'
              )}
            >
              {status.label}
            </span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
