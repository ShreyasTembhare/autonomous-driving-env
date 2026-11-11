"use client";

import { LayerProvider } from "@astryxdesign/core/Layer";
import { Theme } from "@astryxdesign/core/theme";
import { defaultThemeSlug, themes } from "../astryx-themes";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <Theme theme={themes[defaultThemeSlug]} mode="dark">
      <LayerProvider>{children}</LayerProvider>
    </Theme>
  );
}
