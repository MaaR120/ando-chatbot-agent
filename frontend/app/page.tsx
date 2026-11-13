import Link from "next/link";

export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-6 px-16 text-center">
      <div className="space-y-2">
        <h1 className="text-4xl font-bold tracking-tight text-zinc-50 sm:text-6xl">
          ANDO
        </h1>
        <h2 className="text-lg text-zinc-400 sm:text-xl">¿Hacia dónde vamos?</h2>
      </div>

      <p className="max-w-md text-sm text-zinc-500">
        Tu asistente turístico inteligente para descubrir bodegas, gastronomía, naturaleza y actividades en Mendoza.
      </p>

      <Link
        href="/chat"
        className="mt-2 inline-flex items-center gap-2 rounded-xl bg-zinc-100 px-6 py-3 text-sm font-semibold text-zinc-900 shadow-lg shadow-black/20 transition-all hover:bg-white hover:scale-105 active:scale-95"
      >
        <span>Comenzar a chatear</span>
        <span aria-hidden="true">→</span>
      </Link>
    </main>
  );
}
