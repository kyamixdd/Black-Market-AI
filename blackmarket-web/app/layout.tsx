import type { Metadata } from "next";
import "./globals.css";
import "../desktop/src/index.css";
import "../desktop/src/App.css";
export const metadata: Metadata = {
  title: "BlackMarket AI",
  description: "Private market intelligence and paper trading dashboard"
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}