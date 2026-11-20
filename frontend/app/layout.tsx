import type { Metadata } from "next";
import { Fraunces, IBM_Plex_Mono, Source_Sans_3 } from "next/font/google";
import "./globals.css";
import { cn } from "@/lib/utils";

const sans = Source_Sans_3({ subsets: ["latin"], variable: "--font-sans" });

const heading = Fraunces({ subsets: ["latin"], variable: "--font-fraunces" });

const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-plex-mono" });

export const metadata: Metadata = {
  title: "Ando · Asistente turístico de Mendoza",
  description: "Planificá tu salida por Mendoza con el asistente de Ando.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="es"
      className={cn(
        "h-full",
        "antialiased",
        sans.variable,
        heading.variable,
        mono.variable,
        "font-sans",
      )}
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
