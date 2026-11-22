import { resolve } from "node:path";
import type { NextConfig } from "next";

const webNodeModules = resolve(process.cwd(), "node_modules");

const config: NextConfig = {
  poweredByHeader: false,
  experimental: { externalDir: true },
  webpack(webpackConfig) {
    // The web app imports the shared Tauri UI from ../blackmarket-desktop.
    // Since the Vercel install runs inside blackmarket-web, Webpack's
    // issuer-relative lookup misses dependencies installed in this directory.
    webpackConfig.resolve.modules = [
      webNodeModules,
      ...(webpackConfig.resolve.modules ?? []),
    ];
    return webpackConfig;
  },
};

export default config;
