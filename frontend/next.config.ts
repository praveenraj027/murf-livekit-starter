import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  eslint: {
    // These warnings come from upstream LiveKit/AI UI components, not our code.
    ignoreDuringBuilds: true,
  },
  // node-sqlite3-wasm ships a .wasm binary that must be loaded from node_modules
  // at runtime, not bundled. The Day 7 help desk reads the backend's SQLite file
  // through it in a Node runtime route.
  serverExternalPackages: ['node-sqlite3-wasm'],
};

export default nextConfig;
