"use client";
import * as React from "react";
import Link from "next/link";
import { HugeiconsIcon } from "@hugeicons/react";
import {
  ArrowUp02Icon,
  Menu01Icon,
  Delete02Icon,
  Comment01Icon,
  CirclePlusIcon,
  AiSparklesIcon,
  Wrench01Icon,
  Copy01Icon,
  Tick02Icon,
} from "@hugeicons/core-free-icons";

import { Markdown } from "@/components/chat/markdown";
import { Bubble, BubbleContent } from "@/components/ui/bubble";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupTextarea,
} from "@/components/ui/input-group";

import {
  Message,
  MessageContent,
  MessageFooter,
} from "@/components/ui/message";
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from "@/components/ui/message-scroller";

export type ToolCallStep = {
  tool: string;
  input: unknown;
  thought?: string | null;
  output?: unknown;
};

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  thought?: string | null;
  steps?: ToolCallStep[];
};

type Conversation = {
  id: string;
  usuario_id: string;
  fecha_inicio: string;
  titulo: string;
  cantidad_mensajes: number;
  activa: boolean;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const DEMO_USER_ID = "8addc001-3489-4811-b84f-4c7be7bfce02";

async function fetchConversations(): Promise<Conversation[]> {
  const res = await fetch(
    `${API_BASE_URL}/agent/conversations?user_id=${DEMO_USER_ID}`,
    {
      cache: "no-store",
    },
  );
  if (!res.ok) return [];
  return res.json();
}

async function fetchConversationMessages(
  conversationId: string,
): Promise<ChatMessage[]> {
  const res = await fetch(
    `${API_BASE_URL}/agent/conversations/${conversationId}/messages?user_id=${DEMO_USER_ID}`,
    { cache: "no-store" },
  );
  if (!res.ok) return [];
  const data: Array<{ id: string; rol: string; contenido: string }> =
    await res.json();
  return data.map((m) => ({
    id: m.id,
    role: m.rol === "usuario" || m.rol === "user" ? "user" : "assistant",
    text: m.contenido,
  }));
}

async function removeConversation(conversationId: string): Promise<boolean> {
  const res = await fetch(
    `${API_BASE_URL}/agent/conversations/${conversationId}?user_id=${DEMO_USER_ID}`,
    { method: "DELETE" },
  );
  return res.ok;
}

async function replyToAgent(
  text: string,
  history: ChatMessage[],
  conversationId: string | null,
): Promise<{
  answer: string;
  newConversationId?: string;
  thought?: string | null;
  steps?: ToolCallStep[];
}> {
  const formattedHistory = history.map((m) => ({
    rol: m.role === "user" ? "usuario" : "asistente",
    contenido: m.text,
  }));

  const res = await fetch(`${API_BASE_URL}/agent/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      message: text,
      user_id: DEMO_USER_ID,
      conversation_id: conversationId,
      history: formattedHistory,
    }),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Error en el servidor (${res.status})`);
  }

  const data = await res.json();
  return {
    answer: data.response,
    newConversationId: data.conversation_id,
    thought: data.thought,
    steps: data.steps,
  };
}

function ToolCallsDisclosure({
  thought,
  steps,
}: {
  thought?: string | null;
  steps?: ToolCallStep[];
}) {
  const [open, setOpen] = React.useState(false);
  const totalSteps = steps?.length || 0;

  if (!thought && (!steps || steps.length === 0)) return null;

  return (
    <div className="mb-2 w-full max-w-2xl overflow-hidden rounded-xl border border-zinc-800/80 bg-zinc-950/70 text-xs shadow-sm backdrop-blur">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="flex w-full items-center justify-between px-3 py-2 text-left font-mono text-[11px] text-zinc-400 transition-colors hover:bg-zinc-900/60 hover:text-zinc-200"
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className="flex h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.7)]" />
          <span className="font-semibold text-zinc-300">
            {totalSteps > 0
              ? `Razonamiento & ${totalSteps} ${totalSteps === 1 ? "herramienta" : "herramientas"}`
              : "Proceso de pensamiento"}
          </span>
          {steps && steps.length > 0 && (
            <span className="rounded bg-zinc-800/80 px-1.5 py-0.5 text-[10px] text-zinc-300">
              {steps.map((s) => s.tool).join(", ")}
            </span>
          )}
        </div>
        <span className="text-[10px] text-zinc-500 font-sans ml-2">
          {open ? "Ocultar ▲" : "Ver proceso ▼"}
        </span>
      </button>

      {open && (
        <div className="space-y-3 border-t border-zinc-800/60 p-3 font-mono text-[11px]">
          {thought && (
            <div>
              <div className="mb-1 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-amber-400">
                <HugeiconsIcon icon={AiSparklesIcon} size={12} />
                <span>Pensamiento de la IA</span>
              </div>
              <div className="rounded-lg bg-zinc-900/80 p-2.5 text-zinc-300 whitespace-pre-wrap leading-relaxed">
                {thought}
              </div>
            </div>
          )}

          {steps && steps.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-emerald-400">
                <HugeiconsIcon icon={Wrench01Icon} size={12} />
                <span>Herramientas invocadas</span>
              </div>

              {steps.map((s, idx) => (
                <div
                  key={idx}
                  className="rounded-lg border border-zinc-800/60 bg-zinc-900/50 p-2.5 space-y-1.5"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-emerald-300">
                      🔧 {s.tool}
                    </span>
                  </div>

                  {s.thought && (
                    <div className="text-zinc-400 text-[10px]">
                      <span className="text-zinc-500 font-semibold">
                        Motivo:{" "}
                      </span>
                      {s.thought}
                    </div>
                  )}

                  {s.input !== undefined && s.input !== null && (
                    <div className="text-[10px]">
                      <span className="text-zinc-500 font-semibold">
                        Parámetros:{" "}
                      </span>
                      <code className="text-zinc-300 bg-zinc-950/80 px-1 py-0.5 rounded break-all">
                        {typeof s.input === "string"
                          ? s.input
                          : JSON.stringify(s.input)}
                      </code>
                    </div>
                  )}

                  {s.output !== undefined && s.output !== null && (
                    <details className="mt-1 text-[10px]">
                      <summary className="cursor-pointer text-zinc-500 hover:text-zinc-300 select-none">
                        Ver datos devueltos por la BD...
                      </summary>
                      <pre className="mt-1 max-h-36 overflow-y-auto rounded bg-zinc-950/90 p-2 text-[10px] text-zinc-300 whitespace-pre-wrap">
                        {typeof s.output === "string"
                          ? s.output
                          : JSON.stringify(s.output, null, 2)}
                      </pre>
                    </details>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function CopyAction({ text }: { text: string }) {
  const [copied, setCopied] = React.useState(false);

  React.useEffect(() => {
    if (!copied) return;
    const timeout = setTimeout(() => setCopied(false), 2000);
    return () => clearTimeout(timeout);
  }, [copied]);

  const label = copied ? "Copiado" : "Copiar";

  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={label}
            onClick={() =>
              navigator.clipboard.writeText(text).then(() => setCopied(true))
            }
          />
        }
      >
        <HugeiconsIcon icon={copied ? Tick02Icon : Copy01Icon} />
      </TooltipTrigger>
      <TooltipContent>
        <p>{label}</p>
      </TooltipContent>
    </Tooltip>
  );
}

export function ChatComponent() {
  const [conversations, setConversations] = React.useState<Conversation[]>([]);
  const [currentConversationId, setCurrentConversationId] = React.useState<
    string | null
  >(null);
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [draft, setDraft] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [sidebarOpen, setSidebarOpen] = React.useState(true);

  const formRef = React.useRef<HTMLFormElement>(null);
  const nextId = React.useRef(0);
  const newId = () => String(nextId.current++);

  const refreshConversations = async () => {
    try {
      const list = await fetchConversations();
      setConversations(list);
    } catch {
      // Ignorar si la API no está disponible
    }
  };

  React.useEffect(() => {
    let ignore = false;
    async function load() {
      try {
        const list = await fetchConversations();
        if (!ignore) {
          setConversations(list);
        }
      } catch {
        // Ignorar si la API no está disponible
      }
    }
    load();
    return () => {
      ignore = true;
    };
  }, []);

  // Seleccionar conversación previa
  async function handleSelectConversation(id: string) {
    if (id === currentConversationId || busy) return;
    setBusy(true);
    setCurrentConversationId(id);
    try {
      const historyMsgs = await fetchConversationMessages(id);
      setMessages(historyMsgs);
    } catch {
      setMessages([]);
    } finally {
      setBusy(false);
    }
  }

  // Iniciar nuevo chat
  function handleNewChat() {
    if (busy) return;
    setCurrentConversationId(null);
    setMessages([]);
    setDraft("");
  }

  // Eliminar conversación
  async function handleDeleteConversation(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    try {
      await removeConversation(id);
      setConversations((prev) => prev.filter((c) => c.id !== id));
      if (currentConversationId === id) {
        handleNewChat();
      }
    } catch {
      // Ignorar error al borrar
    }
  }

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || busy) return;

    setDraft("");
    setBusy(true);

    const userMsgId = newId();
    setMessages((prev) => [...prev, { id: userMsgId, role: "user", text }]);

    try {
      const result = await replyToAgent(text, messages, currentConversationId);
      if (
        result.newConversationId &&
        result.newConversationId !== currentConversationId
      ) {
        setCurrentConversationId(result.newConversationId);
        refreshConversations();
      }

      setMessages((prev) => [
        ...prev,
        {
          id: newId(),
          role: "assistant",
          text: result.answer,
          thought: result.thought,
          steps: result.steps,
        },
      ]);
    } catch (err: unknown) {
      const errorMessage =
        err instanceof Error
          ? err.message
          : "No pude responder. Probá de nuevo.";
      setMessages((prev) => [
        ...prev,
        {
          id: newId(),
          role: "assistant",
          text: `⚠️ ${errorMessage}`,
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  const currentTitle =
    conversations.find((c) => c.id === currentConversationId)?.titulo ||
    "Nueva conversación";

  return (
    <div className="flex h-full w-full overflow-hidden">
      {/* Sidebar de Historial */}
      <aside
        className={`flex flex-col border-r border-zinc-800/80 bg-zinc-950/80 backdrop-blur-xl transition-all duration-300 ${
          sidebarOpen ? "w-72" : "w-0 -translate-x-full overflow-hidden"
        }`}
      >
        <div className="flex items-center justify-between border-b border-zinc-800/60 p-4">
          <Link
            href="/"
            className="text-xs font-semibold tracking-wider text-zinc-300 transition-colors hover:text-white"
          >
            ← ANDO BOT
          </Link>
          <button
            onClick={handleNewChat}
            className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-800/80 px-2.5 py-1 text-xs font-medium text-zinc-200 shadow-sm transition-all hover:bg-zinc-700 hover:text-white active:scale-95"
            title="Iniciar nueva conversación"
          >
            <HugeiconsIcon icon={CirclePlusIcon} size={14} />
            <span>Nuevo</span>
          </button>
        </div>

        {/* Lista de Chats Previos */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          <div className="px-2 py-1 text-[11px] font-medium uppercase tracking-wider text-zinc-500">
            Historial de chats
          </div>
          {conversations.length === 0 ? (
            <div className="px-3 py-6 text-center text-xs text-zinc-500">
              No hay conversaciones guardadas.
            </div>
          ) : (
            conversations.map((c) => {
              const active = c.id === currentConversationId;
              return (
                <div
                  key={c.id}
                  onClick={() => handleSelectConversation(c.id)}
                  className={`group flex items-center justify-between rounded-lg px-3 py-2 text-xs cursor-pointer transition-all ${
                    active
                      ? "bg-zinc-800 text-zinc-100 font-medium shadow-sm"
                      : "text-zinc-400 hover:bg-zinc-900/80 hover:text-zinc-200"
                  }`}
                >
                  <div className="flex items-center gap-2 truncate pr-2">
                    <HugeiconsIcon
                      icon={Comment01Icon}
                      size={14}
                      className={active ? "text-primary" : "text-zinc-500"}
                    />
                    <span className="truncate">{c.titulo}</span>
                  </div>
                  <button
                    onClick={(e) => handleDeleteConversation(e, c.id)}
                    className="opacity-0 group-hover:opacity-100 text-zinc-500 hover:text-red-400 transition-opacity p-1 rounded"
                    title="Eliminar chat"
                  >
                    <HugeiconsIcon icon={Delete02Icon} size={13} />
                  </button>
                </div>
              );
            })
          )}
        </div>

        {/* Footer usuario demo */}
        <div className="border-t border-zinc-800/60 p-3 text-xs text-zinc-400">
          <div className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded-full bg-zinc-800 text-[10px] font-bold text-zinc-300">
              M
            </div>
            <div className="truncate">
              <p className="text-[11px] font-medium text-zinc-200 leading-tight">
                Martina Luconi
              </p>
              <p className="text-[10px] text-zinc-500">Mendoza, AR</p>
            </div>
          </div>
        </div>
      </aside>

      {/* Área Principal de Chat */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Barra superior */}
        <header className="flex h-12 items-center justify-between border-b border-zinc-800/40 bg-zinc-950/40 px-4 backdrop-blur">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen((prev) => !prev)}
              className="rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 transition-colors"
              title={sidebarOpen ? "Ocultar historial" : "Mostrar historial"}
            >
              <HugeiconsIcon icon={Menu01Icon} size={18} />
            </button>
            <span className="text-xs font-semibold text-zinc-200 truncate max-w-sm">
              {currentTitle}
            </span>
          </div>

          <button
            onClick={handleNewChat}
            className="text-xs text-zinc-400 hover:text-zinc-200 transition-colors sm:hidden"
          >
            + Nuevo
          </button>
        </header>

        {/* Mensajes del chat */}
        <div className="flex flex-1 justify-center overflow-hidden">
          <MessageScrollerProvider>
            <div className="flex h-full w-full max-w-3xl flex-col gap-4">
              <div className="min-h-0 flex-1">
                <MessageScroller>
                  <MessageScrollerViewport>
                    <MessageScrollerContent
                      aria-busy={busy}
                      className="gap-4 px-4 pt-4"
                    >
                      {messages.length === 0 && (
                        <div className="flex flex-col items-center justify-center py-20 text-center text-zinc-500">
                          <p className="text-sm font-medium text-zinc-300">
                            ¡Hola, Martina!
                          </p>
                          <p className="text-xs text-zinc-500 mt-1 max-w-sm">
                            ¿En qué puedo ayudarte hoy? Pregúntame sobre bodegas
                            en Mendoza, restaurantes, itinerarios o actividades
                            de aventura.
                          </p>
                        </div>
                      )}

                      {messages.map((m) => (
                        <MessageScrollerItem
                          key={m.id}
                          messageId={m.id}
                          scrollAnchor={m.role === "user"}
                        >
                          {m.role === "user" ? (
                            <Message align="end">
                              <MessageContent>
                                <Bubble align="end" variant="muted">
                                  <BubbleContent className="whitespace-pre-wrap leading-relaxed">
                                    {m.text}
                                  </BubbleContent>
                                </Bubble>
                              </MessageContent>
                            </Message>
                          ) : (
                            <Message>
                              <MessageContent className="gap-2 text-sm">
                                <ToolCallsDisclosure
                                  thought={m.thought}
                                  steps={m.steps}
                                />
                                <Markdown>{m.text}</Markdown>
                                <MessageFooter className="px-0">
                                  <CopyAction text={m.text} />
                                </MessageFooter>
                              </MessageContent>
                            </Message>
                          )}
                        </MessageScrollerItem>
                      ))}

                      {busy && (
                        <Message align="start">
                          <MessageContent>
                            <div className="flex items-center gap-2.5 rounded-xl border border-zinc-800/80 bg-zinc-900/40 px-3.5 py-2 text-xs text-zinc-400 backdrop-blur animate-pulse font-mono text-[11px]">
                              <span className="flex h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.7)]" />
                              <span>
                                Pensando y consultando herramientas de
                                Mendoza...
                              </span>
                            </div>
                          </MessageContent>
                        </Message>
                      )}
                    </MessageScrollerContent>
                  </MessageScrollerViewport>
                  <MessageScrollerButton />
                </MessageScroller>
              </div>

              {/* Formulario de Entrada */}
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
        </div>
      </div>
    </div>
  );
}
