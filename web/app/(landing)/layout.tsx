import type { Metadata } from "next";
import "./style.css";

export const metadata: Metadata = {
  title: "Mini-Nota | From CT scans to risk rankings",
  description: "Follow the Mini-Nota imaging workflow from public Lung1 CT scans to a recorded survival-risk analysis.",
};

export default function LandingLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@500;600&family=Newsreader:opsz,wght@6..72,400;6..72,500&family=IBM+Plex+Mono:wght@400;500&display=swap"
          precedence="landing-fonts"
        />
        {children}
      </body>
    </html>
  );
}
