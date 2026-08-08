'use client';

import { motion } from 'motion/react';
import { SignatureLine } from '@/components/agents-ui/signature-line';

/**
 * Connecting state — the ledger line draws itself across the page like a pen
 * while the room joins. Tells the user plainly to wait.
 */
export const ConnectingView = ({ ref }: React.ComponentProps<'div'>) => {
  return (
    <div ref={ref}>
      <section className="mx-auto flex w-full max-w-xl flex-col items-center px-6 text-center">
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: [0.4, 1, 0.4] }}
          transition={{ duration: 1.6, repeat: Infinity, ease: 'easeInOut' }}
          className="text-muted-foreground font-mono text-[11px] font-medium tracking-[0.22em] uppercase"
        >
          Connecting
        </motion.p>

        <motion.h1
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="text-foreground mt-5 font-serif text-3xl font-medium tracking-tight md:text-4xl"
        >
          Joining the call
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1, duration: 0.5 }}
          className="text-muted-foreground mt-4 max-w-sm text-[15px] leading-relaxed text-pretty"
        >
          One moment, please. Dhan Saathi is getting ready to talk with you.
        </motion.p>

        <div className="animate-draw-across mt-10 w-full">
          <SignatureLine stateOverride="connecting" />
        </div>
      </section>
    </div>
  );
};
