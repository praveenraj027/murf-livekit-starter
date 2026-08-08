'use client';

import { useEffect, useState } from 'react';
import { ConnectionState } from 'livekit-client';
import { AnimatePresence, motion } from 'motion/react';
import { useSessionContext } from '@livekit/components-react';
import type { AppConfig } from '@/app-config';
import { AgentSessionView_01 } from '@/components/agents-ui/blocks/agent-session-view-01';
import { CallEndedView } from '@/components/app/call-ended-view';
import { ConnectingView } from '@/components/app/connecting-view';
import { MicPermissionAlert } from '@/components/app/mic-permission-alert';
import { WelcomeView } from '@/components/app/welcome-view';

const MotionWelcomeView = motion.create(WelcomeView);
const MotionConnectingView = motion.create(ConnectingView);
const MotionCallEndedView = motion.create(CallEndedView);
const MotionSessionView = motion.create(AgentSessionView_01);

const VIEW_MOTION_PROPS = {
  variants: {
    visible: {
      opacity: 1,
    },
    hidden: {
      opacity: 0,
    },
  },
  initial: 'hidden',
  animate: 'visible',
  exit: 'hidden',
  transition: {
    duration: 0.5,
    ease: 'linear',
  },
};

type Phase = 'ready' | 'connecting' | 'session' | 'ended';

interface ViewControllerProps {
  appConfig: AppConfig;
}

export function ViewController({ appConfig }: ViewControllerProps) {
  const { isConnected, connectionState, start } = useSessionContext();

  // Derive one of the five Day-3 states. "Ready" and "Ended" are both the
  // disconnected state — we tell them apart by whether a call has happened yet.
  const [phase, setPhase] = useState<Phase>('ready');

  useEffect(() => {
    if (connectionState === ConnectionState.Connecting) {
      setPhase('connecting');
    } else if (isConnected) {
      setPhase('session');
    } else if (connectionState === ConnectionState.Disconnected) {
      // Only show "Call ended" if we had actually been in a call.
      setPhase((prev) => (prev === 'ready' ? 'ready' : 'ended'));
    }
  }, [connectionState, isConnected]);

  return (
    <>
      {/* Mic permission errors are surfaced across every phase. */}
      <MicPermissionAlert />

      <AnimatePresence mode="wait">
        {/* Ready */}
        {phase === 'ready' && (
          <MotionWelcomeView
            key="welcome"
            {...VIEW_MOTION_PROPS}
            startButtonText={appConfig.startButtonText}
            onStartCall={start}
          />
        )}

        {/* Connecting */}
        {phase === 'connecting' && <MotionConnectingView key="connecting" {...VIEW_MOTION_PROPS} />}

        {/* Call ended */}
        {phase === 'ended' && (
          <MotionCallEndedView key="ended" {...VIEW_MOTION_PROPS} onStartCall={start} />
        )}

        {/* Listening / Speaking (live session) */}
        {phase === 'session' && (
          <MotionSessionView
            key="session-view"
            {...VIEW_MOTION_PROPS}
            supportsChatInput={appConfig.supportsChatInput}
            className="fixed inset-0"
          />
        )}
      </AnimatePresence>
    </>
  );
}
