"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

const Application = dynamic(() => import("../../../blackmarket-desktop/src/App"), {
  ssr: false,
  loading: () => <main className="startup-screen"><section className="startup-card"><strong>BlackMarket AI</strong><p>Loading institutional terminal…</p></section></main>,
});

export default function SharedApplication() {
  const [identityReady, setIdentityReady] = useState(false);
  const [identityError, setIdentityError] = useState("");

  useEffect(() => {
    let active = true;
    fetch("/api/identity", { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) {
          const result = await response.json().catch(() => ({}));
          throw new Error(typeof result.error === "string" ? result.error : "Could not initialize browser identity.");
        }
        if (active) setIdentityReady(true);
      })
      .catch((error: unknown) => {
        if (active) setIdentityError(error instanceof Error ? error.message : "Could not initialize browser identity.");
      });

    return () => { active = false; };
  }, []);

  if (identityError) {
    return <main className="startup-screen"><section className="startup-card"><strong>BlackMarket AI</strong><p>{identityError}</p><p>Check the website configuration and reload.</p></section></main>;
  }
  if (!identityReady) {
    return <main className="startup-screen"><section className="startup-card"><strong>BlackMarket AI</strong><p>Opening dashboard…</p></section></main>;
  }
  return <Application />;
}
