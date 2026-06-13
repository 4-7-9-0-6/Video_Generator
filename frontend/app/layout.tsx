import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ToonForge Studio",
  description: "Local-first AI creation suite — characters, voice, video.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <header className="topbar">
          <a href="/" className="brand">🎬 ToonForge Studio</a>
          <nav className="row" style={{ gap: 14 }}>
            <a href="/">Projects</a>
            <a href="/voice">VoiceLab</a>
          </nav>
          <span className="tagline" style={{ marginLeft: "auto" }}>local-first · free · EN/FR</span>
        </header>
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
