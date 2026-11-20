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
import { RouteTimelines, tieneRuta } from "@/components/chat/route-timeline";
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
  id?: string;
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
  // true mientras el agente sigue trabajando en este mensaje (streaming)
  live?: boolean;
};

// Eventos que emite POST /agent/chat/stream (Server-Sent Events).
type AgentEvent =
  | { type: "start"; conversation_id: string }
  | { type: "reasoning"; delta: string }
  | { type: "token"; delta: string }
  | {
      type: "tool_call";
      id: string;
      tool: string;
      input: unknown;
      thought: string | null;
    }
  | { type: "tool_result"; id: string; tool: string; output: unknown }
  | {
      type: "done";
      output: string;
      thought: string | null;
      steps: ToolCallStep[];
      conversation_id: string;
    }
  | { type: "error"; detail: string };

type Conversation = {
  id: string;
  usuario_id: string;
  fecha_inicio: string;
  titulo: string;
  cantidad_mensajes: number;
  activa: boolean;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
// Cuenta inicial de la demo (no hay login real: se elige una cuenta en el pie de la barra lateral).
const DEFAULT_USER_ID = "8addc001-3489-4811-b84f-4c7be7bfce02";
const USER_STORAGE_KEY = "ando-chat-user";
const ANONYMOUS = "anonimo";

type DemoUser = {
  id: string;
  nombre: string;
  apellido: string;
  ciudad_origen: string | null;
  valoraciones: number;
  itinerarios: number;
};

async function fetchUsers(): Promise<DemoUser[]> {
  const res = await fetch(`${API_BASE_URL}/agent/users`, { cache: "no-store" });
  if (!res.ok) return [];
  return res.json();
}

async function fetchConversations(userId: string): Promise<Conversation[]> {
  const res = await fetch(
    `${API_BASE_URL}/agent/conversations?user_id=${userId}`,
    {
      cache: "no-store",
    },
  );
  if (!res.ok) return [];
  return res.json();
}

async function fetchConversationMessages(
  conversationId: string,
  userId: string,
): Promise<ChatMessage[]> {
  const res = await fetch(
    `${API_BASE_URL}/agent/conversations/${conversationId}/messages?user_id=${userId}`,
    { cache: "no-store" },
  );
  if (!res.ok) return [];
  const data: Array<{
    id: string;
    rol: string;
    contenido: string;
    thought: string | null;
    steps: ToolCallStep[];
  }> = await res.json();
  return data.map((m) => ({
    id: m.id,
    role: m.rol === "usuario" || m.rol === "user" ? "user" : "assistant",
    text: m.contenido,
    thought: m.thought,
    steps: m.steps,
  }));
}

async function removeConversation(
  conversationId: string,
  userId: string,
): Promise<boolean> {
  const res = await fetch(
    `${API_BASE_URL}/agent/conversations/${conversationId}?user_id=${userId}`,
    { method: "DELETE" },
  );
  return res.ok;
}

/**
 * Envía el mensaje y llama a `onEvent` con cada evento a medida que el agente trabaja.
 * El backend responde text/event-stream: bloques "data: <json>" separados por una línea en blanco.
 */
async function streamAgentReply(
  text: string,
  history: ChatMessage[],
  conversationId: string | null,
  userId: string | null,
  onEvent: (event: AgentEvent) => void,
): Promise<void> {
  const formattedHistory = history.map((m) => ({
    rol: m.role === "user" ? "usuario" : "asistente",
    contenido: m.text,
  }));

  const res = await fetch(`${API_BASE_URL}/agent/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: text,
      // null = sin sesión: el agente no tiene las tools personales y la conversación no se guarda.
      user_id: userId,
      conversation_id: conversationId,
      history: formattedHistory,
    }),
  });

  if (!res.ok || !res.body) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Error en el servidor (${res.status})`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // Un evento puede llegar partido en varios fragmentos: se procesan sólo los completos.
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      const data = block
        .split("\n")
        .filter((line) => line.startsWith("data: "))
        .map((line) => line.slice(6))
        .join("\n");
      if (data) onEvent(JSON.parse(data) as AgentEvent);
    }
  }
}

/** Aplica un evento del stream al mensaje del asistente que se está construyendo. */
function applyAgentEvent(message: ChatMessage, event: AgentEvent): ChatMessage {
  switch (event.type) {
    case "reasoning":
      return { ...message, thought: (message.thought ?? "") + event.delta };
    case "token":
      return { ...message, text: message.text + event.delta };
    case "tool_call":
      // El texto previo a la tool call ya viaja en `thought` del paso: se limpia la respuesta.
      return {
        ...message,
        text: "",
        steps: [
          ...(message.steps ?? []),
          {
            id: event.id,
            tool: event.tool,
            input: event.input,
            thought: event.thought,
          },
        ],
      };
    case "tool_result":
      return {
        ...message,
        steps: (message.steps ?? []).map((s) =>
          s.id === event.id ? { ...s, output: event.output } : s,
        ),
      };
    case "done":
      return {
        ...message,
        text: event.output,
        thought: event.thought,
        steps: event.steps,
        live: false,
      };
    case "error":
      return { ...message, text: `⚠️ ${event.detail}`, live: false };
    default:
      return message;
  }
}

function formatPayload(value: unknown, indent?: number): string {
  return typeof value === "string" ? value : JSON.stringify(value, null, indent);
}

function ToolStepCard({ step, live }: { step: ToolCallStep; live?: boolean }) {
  return (
    <div className="rounded-lg border border-stone-200 bg-stone-50 p-2.5 space-y-1.5">
      <div className="flex items-center gap-2">
        <span className="font-bold text-[#7a1f34]">🔧 {step.tool}</span>
        {live && step.output == null && (
          <span className="animate-pulse text-[10px] text-stone-500">
            ejecutando…
          </span>
        )}
      </div>

      {step.thought && (
        <div className="text-[10px] text-stone-500">
          <span className="text-stone-500 font-semibold">Motivo: </span>
          {step.thought}
        </div>
      )}

      {step.input != null && (
        <div className="text-[10px]">
          <span className="text-stone-500 font-semibold">Parámetros: </span>
          <code className="text-stone-700 bg-white px-1 py-0.5 rounded break-all">
            {formatPayload(step.input)}
          </code>
        </div>
      )}

      {step.output != null && (
        <details className="mt-1 text-[10px]">
          <summary className="cursor-pointer text-stone-500 hover:text-stone-700 select-none">
            Ver datos devueltos por la BD...
          </summary>
          <pre className="mt-1 max-h-36 overflow-y-auto rounded bg-white p-2 text-[10px] text-stone-700 whitespace-pre-wrap">
            {formatPayload(step.output, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}

function ToolSteps({ steps, live }: { steps: ToolCallStep[]; live?: boolean }) {
  const label = `${steps.length} ${steps.length === 1 ? "herramienta invocada" : "herramientas invocadas"}`;

  return (
    // Abierto mientras el agente trabaja, para ver cada tool apenas se invoca.
    <details className="group border-t border-stone-200" open={live || undefined}>
      <summary className="flex cursor-pointer select-none items-center gap-1.5 px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-[#7a1f34] hover:bg-stone-50">
        <HugeiconsIcon icon={Wrench01Icon} size={12} />
        <span>{label}</span>
        <span className="ml-auto font-sans font-normal normal-case text-stone-500 group-open:rotate-180">
          ▼
        </span>
      </summary>
      <div className="space-y-2 p-3 pt-0">
        {steps.map((s, idx) => (
          <ToolStepCard key={s.id ?? idx} step={s} live={live} />
        ))}
      </div>
    </details>
  );
}

function ToolCallsDisclosure({
  thought,
  steps: rawSteps,
  live,
}: {
  thought?: string | null;
  steps?: ToolCallStep[] | null;
  live?: boolean;
}) {
  const steps = rawSteps ?? [];
  if (!thought && steps.length === 0) return null;

  return (
    <div className="mb-2 w-full max-w-2xl overflow-hidden rounded-xl border border-stone-200 bg-white font-mono text-[11px] shadow-sm backdrop-blur">
      {thought && (
        <details className="group" open={live || undefined}>
          <summary className="flex cursor-pointer select-none items-center gap-1.5 px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-amber-700 hover:bg-stone-50">
            <HugeiconsIcon icon={AiSparklesIcon} size={12} />
            <span>{live ? "Pensando…" : "Pensamiento de la IA"}</span>
            <span className="ml-auto font-sans font-normal normal-case text-stone-500 group-open:rotate-180">
              ▼
            </span>
          </summary>
          <div className="whitespace-pre-wrap px-3 pb-3 leading-relaxed text-stone-700">
            {thought}
          </div>
        </details>
      )}
      {steps.length > 0 && <ToolSteps steps={steps} live={live} />}
    </div>
  );
}

type PdfOutput = { file_id: string; filename: string };

function PdfDownloads({ steps }: { steps?: ToolCallStep[] | null }) {
  const pdfs = (steps ?? [])
    .filter((s) => s.tool === "generar_pdf")
    .map((s) => s.output as PdfOutput | null)
    .filter((p): p is PdfOutput => !!p?.file_id);
  return pdfs.map((p) => (
    <a
      key={p.file_id}
      href={`${API_BASE_URL}/agent/pdfs/${p.file_id}?filename=${encodeURIComponent(p.filename)}`}
      className="w-fit rounded-lg bg-[#7a1f34] px-3 py-1.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-[#5e1828]"
    >
      Descargar {p.filename}
    </a>
  ));
}

function ThinkingIndicator() {
  return (
    <div className="flex w-fit items-center gap-2.5 rounded-xl border border-stone-200 bg-stone-50 px-3.5 py-2 font-mono text-[11px] text-stone-500 backdrop-blur animate-pulse">
      <span className="flex h-2 w-2 rounded-full bg-[#7a1f34]" />
      <span>Pensando y consultando herramientas de Mendoza...</span>
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
  // Cuenta con la que se conversa; null = sin sesión.
  const [userId, setUserId] = React.useState<string | null>(DEFAULT_USER_ID);
  const [users, setUsers] = React.useState<DemoUser[]>([]);

  const formRef = React.useRef<HTMLFormElement>(null);
  const nextId = React.useRef(0);
  const newId = () => String(nextId.current++);

  const currentUser = users.find((u) => u.id === userId) ?? null;

  const refreshConversations = async () => {
    if (!userId) return;
    try {
      const list = await fetchConversations(userId);
      setConversations(list);
    } catch {
      // Ignorar si la API no está disponible
    }
  };

  // Cuentas disponibles y, si sigue existiendo, la última elegida en este navegador.
  React.useEffect(() => {
    fetchUsers()
      .then((list) => {
        setUsers(list);
        let stored: string | null = null;
        try {
          stored = localStorage.getItem(USER_STORAGE_KEY);
        } catch {
          // Sin acceso a localStorage: se queda la cuenta por defecto.
        }
        if (stored === ANONYMOUS) setUserId(null);
        else if (stored && list.some((u) => u.id === stored)) setUserId(stored);
      })
      .catch(() => {});
  }, []);

  // Al cambiar de cuenta se cargan sus conversaciones (sin sesión no hay historial guardado).
  React.useEffect(() => {
    let ignore = false;
    async function load() {
      if (!userId) {
        setConversations([]);
        return;
      }
      try {
        const list = await fetchConversations(userId);
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
  }, [userId]);

  // Seleccionar conversación previa
  async function handleSelectConversation(id: string) {
    if (id === currentConversationId || busy || !userId) return;
    setBusy(true);
    setCurrentConversationId(id);
    try {
      const historyMsgs = await fetchConversationMessages(id, userId);
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

  // Cambiar de cuenta: cada cuenta tiene sus conversaciones, así que se empieza un chat nuevo.
  function handleChangeUser(value: string) {
    if (busy) return;
    const next = value === ANONYMOUS ? null : value;
    setUserId(next);
    try {
      localStorage.setItem(USER_STORAGE_KEY, value);
    } catch {
      // Sin acceso a localStorage: el cambio dura hasta recargar.
    }
    handleNewChat();
  }

  // Eliminar conversación
  async function handleDeleteConversation(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    if (!userId) return;
    try {
      await removeConversation(id, userId);
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
    await send(text);
  }

  async function send(text: string) {
    setBusy(true);

    const history = messages;
    const userMsgId = newId();
    // Mensaje del asistente vacío que se va completando con los eventos del stream.
    const assistantId = newId();
    setMessages((prev) => [
      ...prev,
      { id: userMsgId, role: "user", text },
      { id: assistantId, role: "assistant", text: "", steps: [], live: true },
    ]);

    const update = (fn: (m: ChatMessage) => ChatMessage) =>
      setMessages((prev) => prev.map((m) => (m.id === assistantId ? fn(m) : m)));

    try {
      await streamAgentReply(text, history, currentConversationId, userId, (event) => {
        if (
          event.type === "start" &&
          event.conversation_id !== currentConversationId
        ) {
          setCurrentConversationId(event.conversation_id);
        }
        if (event.type === "done") refreshConversations();
        update((m) => applyAgentEvent(m, event));
      });
      // Si el stream se cortó sin "done" ni "error", el mensaje deja de estar en vivo igual.
      update((m) => ({ ...m, live: false }));
    } catch (err: unknown) {
      const errorMessage =
        err instanceof Error
          ? err.message
          : "No pude responder. Probá de nuevo.";
      update((m) => ({ ...m, text: `⚠️ ${errorMessage}`, live: false }));
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
        className={`flex flex-col border-r border-stone-200 bg-white backdrop-blur-xl transition-all duration-300 ${
          sidebarOpen ? "w-72" : "w-0 -translate-x-full overflow-hidden"
        }`}
      >
        <div className="flex items-center justify-between border-b border-stone-200 p-4">
          <Link
            href="/"
            className="font-heading text-xl font-semibold text-[#7a1f34] transition-colors hover:text-[#5e1828]"
          >
            Ando
          </Link>
          <button
            onClick={handleNewChat}
            className="inline-flex items-center gap-1.5 rounded-lg bg-stone-100 px-2.5 py-1 text-xs font-medium text-stone-800 shadow-sm transition-all hover:bg-stone-200 hover:text-stone-950 active:scale-95"
            title="Iniciar nueva conversación"
          >
            <HugeiconsIcon icon={CirclePlusIcon} size={14} />
            <span>Nuevo</span>
          </button>
        </div>

        {/* Lista de Chats Previos */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          <div className="px-2 py-1 text-[11px] font-medium uppercase tracking-wider text-stone-500">
            Historial de chats
          </div>
          {conversations.length === 0 ? (
            <div className="px-3 py-6 text-center text-xs text-stone-500">
              {userId
                ? "No hay conversaciones guardadas."
                : "Sin sesión las conversaciones no se guardan. Elegí una cuenta abajo para guardarlas."}
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
                      ? "bg-stone-100 text-stone-900 font-medium shadow-sm"
                      : "text-stone-500 hover:bg-stone-50 hover:text-stone-800"
                  }`}
                >
                  <div className="flex items-center gap-2 truncate pr-2">
                    <HugeiconsIcon
                      icon={Comment01Icon}
                      size={14}
                      className={active ? "text-primary" : "text-stone-500"}
                    />
                    <span className="truncate">{c.titulo}</span>
                  </div>
                  <button
                    onClick={(e) => handleDeleteConversation(e, c.id)}
                    className="opacity-0 group-hover:opacity-100 text-stone-500 hover:text-red-400 transition-opacity p-1 rounded"
                    title="Eliminar chat"
                  >
                    <HugeiconsIcon icon={Delete02Icon} size={13} />
                  </button>
                </div>
              );
            })
          )}
        </div>

        {/* Cuenta activa: la demo no tiene login real, se elige la cuenta acá */}
        <div className="border-t border-stone-200 p-3 text-xs text-stone-500">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-stone-100 text-[10px] font-bold text-stone-700">
              {currentUser ? currentUser.nombre[0].toUpperCase() : "?"}
            </div>
            <div className="min-w-0 flex-1">
              <label
                htmlFor="account"
                className="block text-[10px] text-stone-500"
              >
                {userId ? "Sesión iniciada como" : "Sin sesión"}
              </label>
              <select
                id="account"
                value={userId ?? ANONYMOUS}
                onChange={(e) => handleChangeUser(e.target.value)}
                disabled={busy}
                className="w-full cursor-pointer truncate rounded bg-transparent text-[11px] font-medium text-stone-800 outline-none hover:text-stone-950 disabled:cursor-not-allowed [&>option]:bg-white"
              >
                <option value={ANONYMOUS}>Sin sesión (invitado)</option>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.nombre} {u.apellido} · {u.valoraciones} valoraciones
                  </option>
                ))}
                {userId && !currentUser && (
                  <option value={userId}>Cuenta actual</option>
                )}
              </select>
            </div>
          </div>
        </div>
      </aside>

      {/* Área Principal de Chat */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Barra superior */}
        <header className="flex h-12 items-center justify-between border-b border-stone-200 bg-white px-4 backdrop-blur">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen((prev) => !prev)}
              className="rounded-lg p-1.5 text-stone-500 hover:bg-stone-100 hover:text-stone-800 transition-colors"
              title={sidebarOpen ? "Ocultar historial" : "Mostrar historial"}
            >
              <HugeiconsIcon icon={Menu01Icon} size={18} />
            </button>
            <span className="text-xs font-semibold text-stone-800 truncate max-w-sm">
              {currentTitle}
            </span>
          </div>

          <button
            onClick={handleNewChat}
            className="text-xs text-stone-500 hover:text-stone-800 transition-colors sm:hidden"
          >
            + Nuevo
          </button>
        </header>

        {/* Mensajes del chat */}
        <div className="flex flex-1 justify-center overflow-hidden">
          <MessageScrollerProvider autoScroll>
            <div className="flex h-full w-full max-w-3xl flex-col gap-4">
              <div className="min-h-0 flex-1">
                <MessageScroller>
                  <MessageScrollerViewport>
                    <MessageScrollerContent
                      aria-busy={busy}
                      className="gap-4 px-4 pt-4"
                    >
                      {messages.length === 0 && (
                        <div className="flex flex-col items-center justify-center py-20 text-center text-stone-500">
                          <p className="font-heading text-2xl font-medium text-stone-800">
                            {currentUser
                              ? `¡Hola, ${currentUser.nombre}!`
                              : "¡Hola!"}
                          </p>
                          <p className="text-sm text-stone-500 mt-2 max-w-sm">
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
                                  live={m.live}
                                />
                                {m.live &&
                                  !m.text &&
                                  !m.thought &&
                                  !m.steps?.length && <ThinkingIndicator />}
                                {m.text && <Markdown>{m.text}</Markdown>}
                                <RouteTimelines
                                  steps={m.steps}
                                  contexto={messages.flatMap((x) => x.steps ?? [])}
                                  pdfBaseUrl={`${API_BASE_URL}/agent/pdfs`}
                                  generando={busy}
                                  onGenerarPdf={() => send("Pasame este plan a PDF")}
                                />
                                {!m.live && !tieneRuta(m.steps) && <PdfDownloads steps={m.steps} />}
                                {!m.live && (
                                  <MessageFooter className="px-0">
                                    <CopyAction text={m.text} />
                                  </MessageFooter>
                                )}
                              </MessageContent>
                            </Message>
                          )}
                        </MessageScrollerItem>
                      ))}

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
