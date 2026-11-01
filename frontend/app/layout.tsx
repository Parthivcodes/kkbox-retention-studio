import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "Retention Studio — KKBox", description: "Streaming customer retention intelligence" };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
