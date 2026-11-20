import type { Metadata } from "next";
import "./globals.css";
import "../../blackmarket-desktop/src/index.css";
import "../../blackmarket-desktop/src/design-tokens.css";
import "../../blackmarket-desktop/src/App.css";

export const metadata: Metadata = {
  title: "BlackMarket AI",
  description: "Institutional cryptocurrency intelligence terminal",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
