'use client';

import { AnimatePresence, motion } from 'motion/react';
import { MicOff, X } from 'lucide-react';
import { type MicFailure, useMicrophoneError } from '@/hooks/useMicrophoneError';

function messageFor(failure: MicFailure): { title: string; description: string } {
  switch (failure) {
    case 'PermissionDenied':
      return {
        title: 'Microphone access is blocked',
        description:
          "Dhan Saathi needs your microphone to hear you. Click the lock (or camera) icon in your browser's address bar, choose Allow for the microphone, then reload the page and start again.",
      };
    case 'NotFound':
      return {
        title: 'No microphone found',
        description:
          'We could not find a microphone. Please connect a microphone or headset, then start again.',
      };
    case 'DeviceInUse':
      return {
        title: 'Microphone is busy',
        description:
          'Your microphone is being used by another app. Please close that app and try again.',
      };
    default:
      return {
        title: 'Could not use your microphone',
        description:
          'Something went wrong while accessing your microphone. Please check your microphone settings and try again.',
      };
  }
}

/**
 * A prominent, dismissible banner shown when microphone access fails —
 * most importantly when the user blocks the microphone permission.
 */
export function MicPermissionAlert() {
  const { failure, clear } = useMicrophoneError();

  return (
    <AnimatePresence>
      {failure && (
        <motion.div
          role="alert"
          initial={{ opacity: 0, y: -16 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -16 }}
          transition={{ duration: 0.25 }}
          className="fixed inset-x-0 top-0 z-[100] flex justify-center px-4 pt-4"
        >
          <div className="border-destructive/30 bg-destructive/10 text-foreground flex w-full max-w-md items-start gap-3 rounded-xl border p-4 shadow-lg backdrop-blur-sm">
            <span className="text-destructive mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-destructive/15">
              <MicOff className="size-4" />
            </span>
            <div className="flex-1 text-sm">
              <p className="font-semibold">{messageFor(failure).title}</p>
              <p className="text-muted-foreground mt-1 leading-relaxed">
                {messageFor(failure).description}
              </p>
            </div>
            <button
              type="button"
              onClick={clear}
              aria-label="Dismiss"
              className="text-muted-foreground hover:text-foreground -mt-1 -mr-1 rounded-md p-1 transition-colors"
            >
              <X className="size-4" />
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
