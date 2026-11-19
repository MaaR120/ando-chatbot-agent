"use client";

import { Streamdown } from "streamdown";
export function Markdown({ children }: { children: string }) {
  return <Streamdown mode="static">{children}</Streamdown>;
}
