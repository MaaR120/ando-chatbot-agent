type Parada = {
  orden: number;
  id: string;
  nombre: string;
  llegada: string;
  duracion_min: number | null;
  traslado_siguiente_min: number | null;
  distancia_siguiente_m: number | null;
  aviso_horario: string | null;
};

type Ruta = {
  paradas: Parada[];
  distancia_total_m?: number;
  tiempo_total_min?: number;
};

type Step = { tool: string; output?: unknown };

type Lugar = {
  id?: string;
  precio_min?: number | null;
  puntuacion?: number | null;
  departamento?: string | null;
  zona?: string | null;
  descripcion?: string | null;
};

type Datos = { precio: number | null; puntuacion: number | null; zona: string | null; descripcion: string | null };

function precio(valor: number | null | undefined) {
  if (valor == null) return null;
  return valor === 0 ? "Gratis" : `desde $${valor.toLocaleString("es-AR")}`;
}

function preciosPorId(steps: Step[]) {
  const datos = new Map<string, Datos>();
  for (const s of steps) {
    if (s.tool !== "search_pois_tool" || !Array.isArray(s.output)) continue;
    for (const l of s.output as Lugar[]) if (l?.id) datos.set(l.id, {
        precio: l.precio_min ?? null,
        puntuacion: l.puntuacion ?? null,
        zona: [l.departamento, l.zona && l.zona !== "General" ? l.zona : null].filter(Boolean).join(" · ") || null,
        descripcion: l.descripcion ?? null,
      });
  }
  return datos;
}

function duracion(minutos: number) {
  const horas = Math.floor(minutos / 60);
  const resto = minutos % 60;
  if (!horas) return `${resto} min`;
  return resto ? `${horas} h ${String(resto).padStart(2, "0")}` : `${horas} h`;
}

const km = (metros: number) => `${(metros / 1000).toLocaleString("es-AR", { maximumFractionDigits: 1 })} km`;

function esRuta(output: unknown): output is Ruta {
  return !!output && typeof output === "object" && Array.isArray((output as Ruta).paradas) && (output as Ruta).paradas.length > 0;
}

type Pdf = { file_id: string; filename: string };

function ultimoPdf(steps: Step[]): Pdf | null {
  const pdfs = steps
    .filter((s) => s.tool === "generar_pdf")
    .map((s) => s.output as Pdf | null)
    .filter((p): p is Pdf => !!p?.file_id);
  return pdfs.at(-1) ?? null;
}

type Accion = { pdf: Pdf | null; pdfBaseUrl: string; generando: boolean; onGenerarPdf: () => void };

const BOTON =
  "rounded-md border border-[#7a1f34] px-2.5 py-1 text-xs font-medium text-[#7a1f34] transition-colors hover:bg-[#7a1f34] hover:text-white disabled:pointer-events-none disabled:opacity-50";

function BotonPdf({ pdf, pdfBaseUrl, generando, onGenerarPdf }: Accion) {
  if (pdf) {
    return (
      <a className={BOTON} href={`${pdfBaseUrl}/${pdf.file_id}?filename=${encodeURIComponent(pdf.filename)}`}>
        Descargar PDF
      </a>
    );
  }
  return (
    <button type="button" className={BOTON} disabled={generando} onClick={onGenerarPdf}>
      Generar PDF
    </button>
  );
}

function Timeline({ ruta, titulo, precios, accion }: { ruta: Ruta; titulo: string; precios: Map<string, Datos>; accion: Accion | null }) {
  const total = [
    `${ruta.paradas.length} paradas`,
    ruta.tiempo_total_min ? duracion(ruta.tiempo_total_min) : null,
    ruta.distancia_total_m ? km(ruta.distancia_total_m) : null,
  ].filter(Boolean);
  return (
    <section className="w-full max-w-xl rounded-xl border border-stone-200 bg-stone-50 px-4 py-3">
      <header className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-[#7a1f34]">{titulo}</h3>
          <span className="font-mono text-[11px] text-stone-500">{total.join(" · ")}</span>
        </div>
        {accion && <BotonPdf {...accion} />}
      </header>
      <ol>
        {ruta.paradas.map((p, i) => {
          const ultima = i === ruta.paradas.length - 1;
          return (
            <li key={`${p.id}-${i}`} className="grid grid-cols-[3.25rem_1rem_1fr] gap-x-2">
              <div className="pt-0.5 text-right">
                <div className="font-mono text-sm font-semibold text-stone-900">{p.llegada}</div>
                {p.duracion_min ? <div className="font-mono text-[10px] text-stone-500">{duracion(p.duracion_min)}</div> : null}
              </div>
              <div className="flex flex-col items-center">
                <span className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full bg-[#7a1f34]" />
                {!ultima && <span className="w-px flex-1 bg-stone-300" />}
              </div>
              <div className={ultima ? "pb-1" : "pb-3"}>
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-sm font-medium text-stone-900">{p.nombre}</span>
                  <span className="flex shrink-0 items-baseline gap-2 font-mono text-xs">
                    {precios.get(p.id)?.puntuacion != null && (
                      <span className="text-amber-600" aria-label={`Puntuación ${precios.get(p.id)?.puntuacion} de 5`}>
                        ★ {precios.get(p.id)!.puntuacion!.toLocaleString("es-AR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}
                      </span>
                    )}
                    {precio(precios.get(p.id)?.precio) && (
                      <span className="font-semibold text-[#7a1f34]">{precio(precios.get(p.id)?.precio)}</span>
                    )}
                  </span>
                </div>
                {precios.get(p.id)?.zona && <div className="text-xs text-stone-500">{precios.get(p.id)?.zona}</div>}
                {precios.get(p.id)?.descripcion && (
                  <p className="mt-0.5 line-clamp-2 text-xs leading-snug text-stone-600">{precios.get(p.id)?.descripcion}</p>
                )}
                {p.aviso_horario && <div className="mt-0.5 text-xs text-amber-700">{p.aviso_horario}</div>}
                {!ultima && p.traslado_siguiente_min ? (
                  <div className="mt-1.5 font-mono text-[11px] text-stone-500">
                    ↓ {duracion(p.traslado_siguiente_min)} de traslado
                    {p.distancia_siguiente_m ? ` · ${km(p.distancia_siguiente_m)}` : ""}
                  </div>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

export function tieneRuta(steps?: Step[] | null) {
  return (steps ?? []).some((s) => s.tool === "optimize_route_tool" && esRuta(s.output));
}

type Props = {
  steps?: Step[] | null;
  contexto: Step[];
  pdfBaseUrl: string;
  generando: boolean;
  onGenerarPdf: () => void;
};

export function RouteTimelines({ steps, contexto, pdfBaseUrl, generando, onGenerarPdf }: Props) {
  const rutas = (steps ?? []).filter((s) => s.tool === "optimize_route_tool").map((s) => s.output).filter(esRuta);
  if (!rutas.length) return null;
  const precios = preciosPorId(contexto);
  return (
    <div className="flex flex-col gap-2">
      {rutas.map((ruta, i) => (
        <Timeline
          key={i}
          ruta={ruta}
          titulo={rutas.length > 1 ? `Ruta ${i + 1}` : "Ruta"}
          precios={precios}
          accion={i === 0 ? { pdf: ultimoPdf(contexto), pdfBaseUrl, generando, onGenerarPdf } : null}
        />
      ))}
    </div>
  );
}
