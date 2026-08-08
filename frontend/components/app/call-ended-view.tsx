'use client';

import { motion } from 'motion/react';
import { SignatureLine } from '@/components/agents-ui/signature-line';
import { Button } from '@/components/ui/button';

interface CallEndedViewProps {
  onStartCall: () => void;
}

const container = {
  hidden: {},
  show: {
    transition: { staggerChildren: 0.12, delayChildren: 0.08 },
  },
};

const item = {
  hidden: { opacity: 0, y: 14 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.7, ease: [0.22, 1, 0.36, 1] as const },
  },
};

/**
 * Call ended — the line settles flat. A warm sign-off and one clear way back.
 */
export const CallEndedView = ({
  onStartCall,
  ref,
}: React.ComponentProps<'div'> & CallEndedViewProps) => {
  return (
    <div ref={ref}>
      <motion.section
        variants={container}
        initial="hidden"
        animate="show"
        className="mx-auto flex w-full max-w-xl flex-col items-center px-6 text-center"
      >
        <motion.p
          variants={item}
          className="text-muted-foreground font-mono text-[11px] font-medium tracking-[0.22em] uppercase"
        >
          Call ended
        </motion.p>

        <motion.h1
          variants={item}
          className="text-foreground mt-5 font-serif text-[36px] leading-[1.1] font-medium tracking-tight md:text-[44px]"
        >
          Take care of your money.
        </motion.h1>

        <motion.p
          variants={item}
          className="text-muted-foreground mt-5 max-w-md text-[15px] leading-relaxed text-pretty md:text-base"
        >
          Thank you for talking with Dhan Saathi. Come back any time you have a question — the
          helpline is always here.
        </motion.p>

        <motion.div variants={item} className="mt-10 w-full">
          <SignatureLine stateOverride="disconnected" />
        </motion.div>

        <motion.div variants={item} className="mt-8">
          <Button
            size="lg"
            onClick={onStartCall}
            className="h-12 w-64 rounded-full px-8 font-mono text-[11px] font-bold tracking-[0.18em] uppercase transition-transform duration-200 hover:-translate-y-0.5"
          >
            Start again
          </Button>
        </motion.div>
      </motion.section>
    </div>
  );
};
