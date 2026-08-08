'use client';

import React, { useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Mic, MicOff, MessageSquareText, PhoneOff } from 'lucide-react';
import { useAgent, useSessionContext, useSessionMessages } from '@livekit/components-react';
import { AgentChatTranscript } from '@/components/agents-ui/agent-chat-transcript';
import { AgentStatusPill } from '@/components/agents-ui/agent-status-pill';
import { SignatureLine } from '@/components/agents-ui/signature-line';
import { useInputControls } from '@/hooks/agents-ui/use-agent-control-bar';
import { cn } from '@/lib/shadcn/utils';

export interface AgentSessionView_01Props {
  /** Show the live transcript toggle. @default true */
  supportsChatInput?: boolean;
  /** Optional class name merged onto the outer container. */
  className?: string;
}

/**
 * The live call, in the ledger language: a status in mono, the reactive
 * signature line as the stage, and a small, quiet control bar.
 */
export function AgentSessionView_01({
  supportsChatInput = true,
  ref,
  className,
  ...props
}: React.ComponentProps<'section'> & AgentSessionView_01Props) {
  const session = useSessionContext();
  const { messages } = useSessionMessages(session);
  const { state: agentState } = useAgent();
  const { microphoneToggle } = useInputControls();
  const [transcriptOpen, setTranscriptOpen] = useState(false);

  return (
    <section ref={ref} className={cn('relative h-full w-full overflow-hidden', className)} {...props}>
      {/* Voice stage */}
      <motion.div
        className="absolute inset-0 grid place-content-center px-6"
        animate={{ opacity: transcriptOpen ? 0.15 : 1 }}
        transition={{ duration: 0.3 }}
      >
        <div className="mx-auto flex w-full max-w-xl flex-col items-center">
          <AgentStatusPill />
          <SignatureLine className="mt-10" />
          <p className="text-muted-foreground mt-7 max-w-xs text-center font-mono text-[10px] leading-relaxed tracking-[0.18em] uppercase">
            Speak naturally · you can interrupt any time
          </p>
        </div>
      </motion.div>

      {/* Live transcript */}
      <AnimatePresence>
        {transcriptOpen && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 16 }}
            transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
            className="absolute inset-x-0 top-20 bottom-28 z-20 mx-auto flex max-w-xl flex-col px-6 md:bottom-32"
          >
            <div className="border-border bg-card/95 flex h-full w-full flex-col overflow-hidden rounded-2xl border shadow-lg backdrop-blur">
              <div className="border-border/70 flex items-center justify-between border-b px-4 py-2.5">
                <span className="text-muted-foreground font-mono text-[10px] tracking-[0.2em] uppercase">
                  Transcript
                </span>
                <AgentStatusPill />
              </div>
              <AgentChatTranscript
                agentState={agentState}
                messages={messages}
                className="min-h-0 flex-1 overflow-y-auto px-3 py-3 [&>div>div]:px-1"
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Controls */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3, duration: 0.4 }}
        className="absolute inset-x-0 bottom-8 z-30 flex justify-center px-6 md:bottom-12"
      >
        <div className="border-border bg-card/90 flex items-center gap-2 rounded-full border p-2 shadow-sm backdrop-blur">
          {/* Microphone */}
          <button
            type="button"
            onClick={() => microphoneToggle.toggle()}
            disabled={microphoneToggle.pending}
            aria-pressed={microphoneToggle.enabled}
            aria-label={microphoneToggle.enabled ? 'Mute microphone' : 'Unmute microphone'}
            className={cn(
              'flex size-11 items-center justify-center rounded-full transition-colors disabled:opacity-50',
              microphoneToggle.enabled
                ? 'bg-secondary text-ink hover:bg-accent'
                : 'bg-destructive/10 text-destructive hover:bg-destructive/15'
            )}
          >
            {microphoneToggle.enabled ? <Mic className="size-5" /> : <MicOff className="size-5" />}
          </button>

          {/* Transcript */}
          {supportsChatInput && (
            <button
              type="button"
              onClick={() => setTranscriptOpen((open) => !open)}
              aria-pressed={transcriptOpen}
              aria-label="Toggle transcript"
              className={cn(
                'flex size-11 items-center justify-center rounded-full transition-colors',
                transcriptOpen
                  ? 'bg-ink text-paper'
                  : 'bg-secondary text-ink hover:bg-accent'
              )}
            >
              <MessageSquareText className="size-5" />
            </button>
          )}

          <div className="bg-border mx-1 h-6 w-px" />

          {/* End call */}
          <button
            type="button"
            onClick={session.end}
            className="text-destructive bg-destructive/10 hover:bg-destructive/15 flex h-11 items-center gap-2 rounded-full px-5 font-mono text-[11px] font-bold tracking-[0.15em] uppercase transition-colors"
          >
            <PhoneOff className="size-4" />
            <span>End call</span>
          </button>
        </div>
      </motion.div>
    </section>
  );
}
