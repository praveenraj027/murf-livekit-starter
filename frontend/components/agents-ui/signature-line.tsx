'use client';

import { useMemo } from 'react';
import { useTheme } from 'next-themes';
import {
  type AgentState,
  useSessionContext,
  useVoiceAssistant,
} from '@livekit/components-react';
import { AgentAudioVisualizerWave } from '@/components/agents-ui/agent-audio-visualizer-wave';
import { cn } from '@/lib/shadcn/utils';

// Day ledger.
const LIGHT = { brass: '#9A7A45', ink: '#16202A', soft: '#59636E' } as const;
// Night ledger — brass brightened, "ink" becomes warm off-white so the
// agent's line stays visible on the dark canvas.
const DARK = { brass: '#C9A86B', ink: '#ECEEE9', soft: '#939BA6' } as const;

/** The line is coloured by who "owns" it right now. */
function colorFor(state: AgentState, isDark: boolean): `#${string}` {
  const p = isDark ? DARK : LIGHT;
  switch (state) {
    case 'speaking':
      return p.ink;
    case 'thinking':
    case 'connecting':
    case 'initializing':
      return p.soft;
    default:
      // listening / idle / disconnected — the calm brass baseline
      return p.brass;
  }
}

interface SignatureLineProps {
  /** Force a state (used by the resting screens that have no live session). */
  stateOverride?: AgentState;
  className?: string;
}

/**
 * The signature of the whole product: a single living ledger line, ruled like
 * a passbook, that reacts to the live audio — brass and driven by your mic
 * while you speak, ink and driven by Dhan Saathi while it replies.
 */
export function SignatureLine({ stateOverride, className }: SignatureLineProps) {
  const va = useVoiceAssistant();
  const session = useSessionContext();
  const { resolvedTheme } = useTheme();

  const state = stateOverride ?? va.state;
  const isDark = resolvedTheme !== 'light';
  const color = useMemo(() => colorFor(state, isDark), [state, isDark]);

  // During the agent's turn, visualise its audio; otherwise visualise the
  // user's live microphone so the line moves with the person speaking.
  const isAgentTurn = state === 'speaking' || state === 'thinking';
  const audioTrack = isAgentTurn ? va.audioTrack : session.local.microphoneTrack;

  return (
    <div className={cn('relative w-full', className)} aria-hidden="true">
      {/* Faint passbook tick marks. */}
      <div className="ledger-baseline absolute inset-x-0 top-1/2 h-3 -translate-y-1/2" />
      {/* The solid centre rule the line is written on. */}
      <div className="ledger-rule absolute inset-x-0 top-1/2 h-px -translate-y-1/2" />
      {/* The living line. */}
      <AgentAudioVisualizerWave
        state={state}
        audioTrack={audioTrack}
        color={color}
        colorShift={0}
        blur={0.6}
        className="relative aspect-auto h-28 w-full md:h-40"
      />
    </div>
  );
}
