"use client";

import { useEffect, useRef, useState } from "react";
import { Icon } from "@/components/ui/icon";
import { SectionLabel, StatusDot } from "@/components/ui/primitives";
import { getUserId } from "@/lib/user-id";
import type { AIConversationItem, AskResponse } from "@/lib/api";

// Un turno del hilo visible: la pregunta y su respuesta (null mientras la IA piensa).
type Turn = { pregunta: string; response: AskResponse | null };

// Decorativo — fuentes que alimentan el análisis, no proviene de un endpoint (ver plan de puerto Next.js).
const IA_CONTEXTO = [
  { id: "amb", icon: "thermometer", label: "Datos ambientales actuales", fuente: "Open-Meteo · MODIS · Copernicus" },
  { id: "puntos", icon: "map", label: "Puntos de pesca y memoria territorial", fuente: "Conocimiento comunitario" },
  { id: "etno", icon: "book", label: "Hallazgos etnográficos de campo", fuente: "Trabajo de campo" },
  { id: "obs", icon: "history", label: "Histórico de observaciones comunitarias", fuente: "Bitácora WhatsApp" },
];

function NauticalBg() {
  return (
    <svg className="cr-nautical" viewBox="0 0 400 400" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <g fill="none" stroke="var(--verde)" strokeWidth="0.7">
        <circle cx="300" cy="120" r="70" />
        <circle cx="300" cy="120" r="48" />
        <circle cx="300" cy="120" r="20" />
        {Array.from({ length: 16 }).map((_, i) => {
          const a = (i * Math.PI) / 8;
          return (
            <line
              key={i}
              x1={300 + 20 * Math.cos(a)}
              y1={120 + 20 * Math.sin(a)}
              x2={300 + 70 * Math.cos(a)}
              y2={120 + 70 * Math.sin(a)}
              strokeWidth={i % 4 === 0 ? 1.2 : 0.5}
            />
          );
        })}
        <path d="M300 40 L308 120 L300 200 L292 120 Z" />
        <path d="M220 120 L300 112 L380 120 L300 128 Z" />
        {Array.from({ length: 9 }).map((_, i) => (
          <line key={"h" + i} x1="0" y1={i * 50} x2="400" y2={i * 50} strokeWidth="0.4" />
        ))}
        {Array.from({ length: 9 }).map((_, i) => (
          <line key={"v" + i} x1={i * 50} y1="0" x2={i * 50} y2="400" strokeWidth="0.4" />
        ))}
        <path d="M40 300 q30 -20 60 0 t60 0 t60 0" strokeWidth="0.8" />
        <path d="M30 340 q40 -16 80 0 t80 0" strokeWidth="0.6" />
      </g>
    </svg>
  );
}

function escapeHtml(s: string) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** Escapa todo el HTML crudo (la IA no es una fuente de confianza) y solo
 * reintroduce <b>/</b> y {chip:...} — el único formato que el diseño usa. */
function renderRich(html: string) {
  let escaped = escapeHtml(html);
  escaped = escaped.replace(/&lt;b&gt;/g, "<b>").replace(/&lt;\/b&gt;/g, "</b>");
  escaped = escaped.replace(/\{chip:([^}]+)\}/g, '<code class="cr-chip">$1</code>');
  return { __html: escaped };
}

function TypingDots() {
  return (
    <div style={{ display: "flex", gap: 5, alignItems: "center", padding: "4px 0" }}>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--salmon)", animation: "cr-dots 1.2s infinite", animationDelay: `${i * 0.16}s` }}
        />
      ))}
    </div>
  );
}

function IAMessageUser({ text }: { text: string }) {
  return (
    <div className="cr-ia-user" style={{ animation: "cr-fade-up .3s ease" }}>
      <p className="serif" style={{ margin: 0, fontStyle: "italic", fontSize: 15.5, lineHeight: 1.5, color: "var(--ink)" }}>
        {text}
      </p>
    </div>
  );
}

function AIBlock({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="cr-ia-ai" style={{ animation: "cr-fade-up .4s ease both" }}>
      <div className="cr-ia-ai-head">
        <span className="cr-ia-avatar">
          <Icon name="bot" size={15} />
        </span>
        <SectionLabel style={{ color: "var(--verde)" }}>{label}</SectionLabel>
      </div>
      <div className="cr-ia-ai-body">{children}</div>
    </div>
  );
}

/** Renderiza la respuesta de la IA (párrafos + sugerencia). `showBlock` controla
 * el revelado escalonado del último turno; los turnos pasados muestran todo. La
 * pregunta sugerida solo aparece en el último turno (como en los chats grandes). */
function AssistantAnswer({
  response,
  showBlock,
  showSuggestion,
  onAsk,
}: {
  response: AskResponse;
  showBlock: (i: number) => boolean;
  showSuggestion: boolean;
  onAsk: (q: string) => void;
}) {
  const parrafos = response.parrafos ?? [];
  return (
    <AIBlock label="Análisis · CienRayas IA">
      {parrafos.map(
        (p, i) =>
          showBlock(i) && (
            <div key={i} style={{ animation: "cr-fade-up .4s ease" }}>
              {p.tipo === "texto" && p.html && <p className="cr-ia-p" dangerouslySetInnerHTML={renderRich(p.html)} />}
              {p.tipo === "datos" && p.items && (
                <div className="cr-cite">
                  <SectionLabel style={{ marginBottom: 8 }}>{p.titulo}</SectionLabel>
                  <div className="cr-cite-grid">
                    {p.items.map((d, j) => (
                      <div key={j} className="cr-cite-item">
                        <span className="serif" style={{ fontSize: 20, color: "var(--teal)", fontWeight: 600 }}>
                          {d.v}
                        </span>
                        <span style={{ fontSize: 12, color: "var(--ink-soft)", lineHeight: 1.35 }}>{d.d}</span>
                        <span className="mono cr-fuente">
                          <Icon name="dot" size={8} /> {d.fuente}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {p.tipo === "limitaciones" && p.html && (
                <div className="cr-limit">
                  <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 5 }}>
                    <Icon name="help" size={14} />
                    <SectionLabel style={{ color: "var(--salmon)" }}>{p.titulo ?? "Nota"}</SectionLabel>
                  </div>
                  <p className="cr-ia-p" style={{ margin: 0, fontSize: 13 }} dangerouslySetInnerHTML={renderRich(p.html)} />
                </div>
              )}
            </div>
          )
      )}
      {showSuggestion && response.sugerencia && showBlock(parrafos.length) && (
        <div className="cr-sugerencia" style={{ animation: "cr-fade-up .4s ease" }}>
          <SectionLabel style={{ marginBottom: 7 }}>Próxima pregunta sugerida</SectionLabel>
          <button className="cr-sug-q" onClick={() => onAsk(response.sugerencia!)}>
            <span>{response.sugerencia}</span>
            <Icon name="arrowRight" size={16} />
          </button>
        </div>
      )}
    </AIBlock>
  );
}

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const min = Math.round(diffMs / 60000);
  if (min < 1) return "ahora";
  if (min < 60) return `hace ${min} min`;
  const h = Math.round(min / 60);
  if (h < 24) return `hace ${h} h`;
  const d = Math.round(h / 24);
  return d === 1 ? "ayer" : `hace ${d} días`;
}

export function IAView() {
  // El hilo visible: cada turno es pregunta+respuesta. Un chat = una conversación
  // (conversation_id); el historial agrupa por conversación, no por mensaje suelto.
  const [turns, setTurns] = useState<Turn[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [stage, setStage] = useState(-1); // -1 idle, 0 typing, 1..N revealing blocks, 99 done (del ÚLTIMO turno)
  const [historial, setHistorial] = useState<AIConversationItem[]>([]);
  const [histOpen, setHistOpen] = useState(true);
  const [histError, setHistError] = useState(false);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  function clearTimers() {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  }

  // Fija la respuesta del último turno del hilo (el que está en vuelo).
  const withLastResponse = (ts: Turn[], r: AskResponse | null): Turn[] =>
    ts.map((t, i) => (i === ts.length - 1 ? { ...t, response: r } : t));

  function refreshHistory(uid: string) {
    fetch("/api/admin/ai/history", { headers: { "X-User-Id": uid } })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d: { historial: AIConversationItem[] }) => {
        setHistorial(d.historial ?? []);
        setHistError(false);
      })
      .catch(() => setHistError(true));
  }

  function newChat() {
    clearTimers();
    setTurns([]);
    setConversationId(null);
    setInput("");
    setStage(-1);
  }

  // Ver una conversación pasada: sus turnos ya vienen en el historial, así que se
  // pintan directo sin volver a llamar a la IA (stage 99 = hilo cerrado, sin animación).
  function loadFromHistory(c: AIConversationItem) {
    clearTimers();
    setConversationId(c.id);
    setTurns(
      c.turnos.map((t) => ({
        pregunta: t.pregunta,
        response: { parrafos: t.respuesta, sugerencia: t.sugerencia, conversation_id: c.id },
      }))
    );
    setStage(99);
  }

  function deleteHistoryItem(cid: string) {
    const uid = getUserId();
    setHistorial((hs) => hs.filter((h) => h.id !== cid)); // optimista
    if (cid === conversationId) newChat(); // no dejar visible lo que se borró
    fetch(`/api/admin/ai/history?id=${cid}`, { method: "DELETE", headers: { "X-User-Id": uid } })
      .then(() => refreshHistory(uid))
      .catch(() => refreshHistory(uid));
  }

  async function ask(q: string) {
    clearTimers();
    setInput("");
    setTurns((ts) => [...ts, { pregunta: q, response: null }]); // añade el turno al hilo
    setStage(0);

    const uid = getUserId();
    let data: AskResponse;
    try {
      const res = await fetch("/api/admin/ai/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-User-Id": uid },
        // conversationId null = conversación nueva; el backend mintea el id y lo devuelve.
        body: JSON.stringify({ pregunta: q, conversation_id: conversationId }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      data = await res.json();
    } catch {
      // El botón nunca debe quedarse colgado en "Analizando…": ante un fallo del
      // backend (p. ej. 403 por admin key), mostrar una limitación y cerrar el turno.
      setTurns((ts) =>
        withLastResponse(ts, {
          parrafos: [{ tipo: "limitaciones", titulo: "No disponible", html: "No se pudo obtener la respuesta del sistema. Intenta de nuevo en un momento.", items: null }],
          sugerencia: null,
          conversation_id: conversationId ?? "",
        })
      );
      setStage(99);
      return;
    }
    setConversationId(data.conversation_id); // fija el hilo (nuevo o existente)
    setTurns((ts) => withLastResponse(ts, data));

    const blocks = data.parrafos.length + (data.sugerencia ? 1 : 0);
    let s = 1;
    const step = () => {
      setStage(s);
      if (s < blocks) {
        s++;
        timers.current.push(setTimeout(step, 640));
      } else {
        setStage(99);
      }
    };
    timers.current.push(setTimeout(step, 400));

    refreshHistory(uid);
  }

  // Historial por usuario: la identidad vive en localStorage (solo cliente), así que
  // se carga aquí en el navegador, no en el Server Component. Sin pregunta automática.
  useEffect(() => {
    refreshHistory(getUserId());
    return clearTimers;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [stage, turns.length]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim()) return;
    ask(input.trim());
  }

  const chat = (
    <div className="cr-ia-chat">
      <NauticalBg />
      <div className="cr-ia-head">
        <div>
          <h1 className="serif" style={{ margin: 0, fontSize: 30, fontWeight: 600, color: "var(--verde)", letterSpacing: "-.01em" }}>
            Pregunta a la IA
          </h1>
          <p className="mono" style={{ margin: "5px 0 0", fontSize: 11.5, letterSpacing: ".08em", textTransform: "uppercase", color: "var(--ink-soft)" }}>
            Análisis técnico-científico · Ciénaga Grande
          </p>
        </div>
        <button type="button" className="cr-ia-new" onClick={newChat} disabled={turns.length === 0}>
          <Icon name="plus" size={15} />
          <span>Nueva conversación</span>
        </button>
      </div>

      <div className="cr-badge-aviso">
        <Icon name="help" size={14} />
        Respuesta basada en datos disponibles — no reemplaza el conocimiento de campo.
      </div>

      <div className="cr-ctx">
        <span className="cr-ctx-title mono">Contexto</span>
        <div className="cr-ctx-bar">
          {IA_CONTEXTO.map((c) => (
            <div key={c.id} className="cr-ctx-pill" title={c.fuente}>
              <span className="cr-ctx-ic">
                <Icon name={c.icon} size={13} />
              </span>
              <span className="cr-ctx-lbl">{c.label}</span>
              <StatusDot tone="teal" size={6} />
            </div>
          ))}
        </div>
      </div>

      <div className="cr-ia-thread" ref={scrollRef}>
        {turns.length === 0 && (
          <div
            style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12, padding: "48px 20px", textAlign: "center", color: "var(--ink-soft)", animation: "cr-fade-up .4s ease" }}
          >
            <span style={{ color: "var(--verde-sem)", opacity: 0.6 }}>
              <Icon name="sprout" size={38} />
            </span>
            <p className="serif" style={{ margin: 0, fontSize: 18, color: "var(--verde)" }}>
              Haz una pregunta técnica sobre la Ciénaga
            </p>
            <p style={{ margin: 0, fontSize: 13, maxWidth: 420, lineHeight: 1.5 }}>
              La IA responde con los datos ambientales disponibles y recuerda el hilo de tu
              conversación.
            </p>
          </div>
        )}

        {/* El hilo completo: cada turno del chat. Solo el último se revela con
            animación (showBlock según stage); los previos se muestran enteros. */}
        {turns.map((turn, ti) => {
          const isLast = ti === turns.length - 1;
          const showBlock = isLast ? (i: number) => stage === 99 || stage > i : () => true;
          return (
            <div key={ti}>
              <IAMessageUser text={turn.pregunta} />
              {isLast && stage === 0 && !turn.response && (
                <AIBlock label="Analizando contexto…">
                  <TypingDots />
                </AIBlock>
              )}
              {turn.response && (!isLast || stage >= 1) && (
                <AssistantAnswer response={turn.response} showBlock={showBlock} showSuggestion={isLast} onAsk={ask} />
              )}
            </div>
          );
        })}
      </div>

      <form className="cr-ia-input" onSubmit={submit}>
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Escribe tu pregunta al sistema…" />
        <button type="submit" aria-label="Enviar" disabled={stage >= 0 && stage < 99}>
          <Icon name="arrowRight" size={18} />
        </button>
      </form>
    </div>
  );

  const historialAside = (
    <aside className={"cr-ia-hist" + (histOpen ? "" : " collapsed")}>
      <button className="cr-hist-toggle" onClick={() => setHistOpen((o) => !o)}>
        <Icon name="history" size={16} />
        {histOpen && <span style={{ flex: 1, textAlign: "left" }}>Historial de sesión</span>}
        {histOpen && <Icon name="chevron" size={15} style={{ transform: "rotate(180deg)" }} />}
      </button>
      {histOpen && (
        <div className="cr-hist-list">
          {histError && historial.length === 0 && (
            <p style={{ fontSize: 12, color: "var(--ink-faint)", padding: "8px 4px" }}>
              No se pudo cargar el historial.
            </p>
          )}
          {historial.map((h) => {
            const active = h.id === conversationId;
            return (
              <div key={h.id} className={"cr-hist-item" + (active ? " active" : "")}>
                <button className="cr-hist-open" onClick={() => loadFromHistory(h)}>
                  <span style={{ fontSize: 12.5, lineHeight: 1.4, color: active ? "var(--verde)" : "var(--ink-soft)", fontWeight: active ? 600 : 400 }}>
                    {h.titulo}
                  </span>
                  <span className="mono" style={{ fontSize: 10, color: "var(--ink-faint)", marginTop: 4, display: "block" }}>
                    {relativeTime(h.updated_at)}
                    {h.turnos.length > 1 && ` · ${h.turnos.length} mensajes`}
                  </span>
                </button>
                <button className="cr-hist-del" aria-label="Borrar conversación" title="Borrar" onClick={() => deleteHistoryItem(h.id)}>
                  <Icon name="trash" size={14} />
                </button>
              </div>
            );
          })}
        </div>
      )}
    </aside>
  );

  return (
    <div className="cr-ia cr-ia-amplio">
      {historialAside}
      <div className="cr-ia-main">{chat}</div>
    </div>
  );
}
