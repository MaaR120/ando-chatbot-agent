"use client";
import * as React from "react";
import { HugeiconsIcon } from "@hugeicons/react";
import { ArrowUp02Icon } from "@hugeicons/core-free-icons";

import { Bubble, BubbleContent } from "@/components/ui/bubble";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupTextarea,
} from "@/components/ui/input-group";

import { Message, MessageContent } from "@/components/ui/message";
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from "@/components/ui/message-scroller";

type ChatMessage = { id: string; role: "user" | "assistant"; text: string };

// Único punto a reemplazar cuando se conecte el POST /agent/chat.
async function reply(text: string): Promise<string> {
  return `Recibí: "${text}". Todavía no estoy conectado al agente.`;
}

export function ChatComponent() {
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [draft, setDraft] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const formRef = React.useRef<HTMLFormElement>(null);
  const nextId = React.useRef(0);
  const newId = () => String(nextId.current++);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || busy) return;

    setDraft("");
    setBusy(true);
    setMessages((prev) => [...prev, { id: newId(), role: "user", text }]);
    try {
      const answer = await reply(text);
      setMessages((prev) => [
        ...prev,
        { id: newId(), role: "assistant", text: answer },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: newId(),
          role: "assistant",
          text: "No pude responder. Probá de nuevo.",
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <MessageScrollerProvider>
      <div className="flex h-full w-full max-w-3xl flex-col gap-4">
        <div className="min-h-0 flex-1">
          <MessageScroller>
            <MessageScrollerViewport>
              <MessageScrollerContent aria-busy={busy} className="gap-4 px-4">
                {messages.map((m) => (
                  <MessageScrollerItem
                    key={m.id}
                    messageId={m.id}
                    scrollAnchor={m.role === "user"}
                  >
                    <Message align={m.role === "user" ? "end" : "start"}>
                      <MessageContent>
                        <Bubble
                          align={m.role === "user" ? "end" : "start"}
                          variant={m.role === "user" ? "muted" : "ghost"}
                        >
                          <BubbleContent>{m.text}</BubbleContent>
                        </Bubble>
                      </MessageContent>
                    </Message>
                  </MessageScrollerItem>
                ))}
              </MessageScrollerContent>
            </MessageScrollerViewport>
            <MessageScrollerButton />
          </MessageScroller>
        </div>

        <form ref={formRef} onSubmit={onSubmit} className="px-4 pb-6">
          <InputGroup className="bg-background/60 backdrop-blur">
            <InputGroupTextarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="¿Hacia dónde vamos?"
              aria-label="Mensaje"
              className="min-h-14"
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  formRef.current?.requestSubmit();
                }
              }}
            />
            <InputGroupAddon align="block-end">
              <InputGroupButton
                type="submit"
                variant="default"
                size="icon-sm"
                disabled={!draft.trim() || busy}
                className="ml-auto"
              >
                <HugeiconsIcon icon={ArrowUp02Icon} />
                <span className="sr-only">Enviar</span>
              </InputGroupButton>
            </InputGroupAddon>
          </InputGroup>
        </form>
      </div>
    </MessageScrollerProvider>
  );
}
