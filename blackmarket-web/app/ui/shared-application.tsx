"use client";

import dynamic from "next/dynamic";

const Application = dynamic(() => import("../../../../blackmarket-desktop/src/App"), {
  ssr: false,
  loading: () => <main className="startup-screen"><section className="startup-card"><strong>BlackMarket AI</strong><p>Loading institutional terminal…</p></section></main>,
});

export default function SharedApplication() {
  return <Application />;
}
