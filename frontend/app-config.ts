export interface AppConfig {
  pageTitle: string;
  pageDescription: string;
  companyName: string;

  supportsChatInput: boolean;
  supportsVideoInput: boolean;
  supportsScreenShare: boolean;
  isPreConnectBufferEnabled: boolean;

  logo: string;
  startButtonText: string;
  accent?: string;
  logoDark?: string;
  accentDark?: string;

  audioVisualizerType?: 'bar' | 'wave' | 'grid' | 'radial' | 'aura';
  audioVisualizerColor?: `#${string}`;
  audioVisualizerColorDark?: `#${string}`;
  audioVisualizerColorShift?: number;
  audioVisualizerBarCount?: number;
  audioVisualizerGridRowCount?: number;
  audioVisualizerGridColumnCount?: number;
  audioVisualizerRadialBarCount?: number;
  audioVisualizerRadialRadius?: number;
  audioVisualizerWaveLineWidth?: number;

  // agent dispatch configuration
  agentName?: string;

  // LiveKit Cloud Sandbox configuration
  sandboxId?: string;
}

export const APP_CONFIG_DEFAULTS: AppConfig = {
  // Financial Services track — "Dhan Saathi", a warm money guide for everyday
  // people in India. Identity: "Ledger Line" (see styles/globals.css). Colour
  // and type live in CSS tokens, so no accent is injected here.
  companyName: 'Dhan Saathi',
  pageTitle: 'Dhan Saathi — Money, explained in plain words',
  pageDescription:
    'Talk to Dhan Saathi, a friendly voice guide for banking, savings, and government schemes. Powered by Murf Falcon — the fastest TTS API.',

  supportsChatInput: true,
  // A simple, focused money helpline — no camera or screen share clutter.
  supportsVideoInput: false,
  supportsScreenShare: false,
  isPreConnectBufferEnabled: true,

  logo: '/murf-logo.svg',
  logoDark: '/murf-logo-dark.svg',
  startButtonText: 'Start talking',

  // agent dispatch configuration
  agentName: process.env.AGENT_NAME ?? undefined,

  // LiveKit Cloud Sandbox configuration
  sandboxId: undefined,
};
