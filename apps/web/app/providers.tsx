"use client";

import { ThemeProvider } from "next-themes";
import { useEffect } from "react";
import { Toaster } from "sonner";
import { connectWs, disconnectWs } from "@/lib/ws";
import { TooltipProvider } from "@/components/tip";

export function Providers({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    connectWs();
    return () => disconnectWs();
  }, []);

  return (
    <ThemeProvider attribute="class" defaultTheme="dark" enableSystem>
      <TooltipProvider>
        {children}
      </TooltipProvider>
      <Toaster position="bottom-right" richColors />
    </ThemeProvider>
  );
}
