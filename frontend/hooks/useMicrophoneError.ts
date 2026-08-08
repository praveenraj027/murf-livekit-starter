'use client';

import { useEffect, useState } from 'react';
import { ConnectionState, MediaDeviceFailure, RoomEvent } from 'livekit-client';
import { useSessionContext } from '@livekit/components-react';

export type MicFailure = 'PermissionDenied' | 'NotFound' | 'DeviceInUse' | 'Other';

/**
 * Watches the LiveKit room for microphone device errors (e.g. the user blocked
 * mic access) and reports the failure so the UI can show a clear message.
 *
 * This catches both the connect-time failure (pre-connect buffer / start) and
 * in-call toggle failures, since both surface as `RoomEvent.MediaDevicesError`.
 */
export function useMicrophoneError() {
  const { room, connectionState } = useSessionContext();
  const [failure, setFailure] = useState<MicFailure | null>(null);

  useEffect(() => {
    if (!room) return;

    const handleError = (error: Error, kind?: MediaDeviceKind) => {
      // Ignore camera / other device errors — we only care about the mic here.
      if (kind && kind !== 'audioinput') return;

      const reason = MediaDeviceFailure.getFailure(error);
      setFailure((reason as MicFailure) ?? 'Other');
    };

    room.on(RoomEvent.MediaDevicesError, handleError);
    return () => {
      room.off(RoomEvent.MediaDevicesError, handleError);
    };
  }, [room]);

  // Clear a stale error once the user starts a fresh connection attempt.
  useEffect(() => {
    if (connectionState === ConnectionState.Connecting) {
      setFailure(null);
    }
  }, [connectionState]);

  return { failure, clear: () => setFailure(null) };
}
