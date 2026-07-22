import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import {
  addMonths,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  isSameDay,
  isSameMonth,
  startOfMonth,
  startOfWeek,
  subMonths,
} from "date-fns";
import { ptBR } from "date-fns/locale";
import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { ConfirmAction } from "@/components/confirm-action";
import { canalLabel, postStatusLabel } from "@/lib/status";
import { useStore } from "@/lib/store";
import { setSheetStatus } from "@/lib/api/local";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, CheckCircle2, BarChart3 } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { CalendarPost } from "@/lib/mock-data";
import { toast } from "sonner";

export const Route = createFileRoute("/_app/calendario")({
  head: () => ({
    meta: [
      { title: "Calendario | AI Video Creator" },
      { name: "description", content: "Calendario editorial com status de publicacao." },
      { property: "og:title", content: "Calendario | AI Video Creator" },
      { property: "og:description", content: "Calendario editorial dos reels." },
    ],
  }),
  component: CalendarioPage,
});

const canalColor: Record<string, string> = {
  instagram: "border-status-info/40 bg-status-info/10 text-status-info",
  tiktok: "border-status-danger/40 bg-status-danger/10 text-status-danger",
  youtube_shorts:
    "border-status-warn/50 bg-status-warn/15 text-status-warn-foreground",
};

function CalendarioPage() {
  const posts = useStore((s) => s.calendarPosts);
  const updatePost = useStore((s) => s.updateCalendarPost);
  const marcarPublicado = useStore((s) => s.marcarPublicado);
  const [cursor, setCursor] = useState(new Date());
  const [editing, setEditing] = useState<CalendarPost | null>(null);
  const [novaData, setNovaData] = useState("");

  async function publicar(id: string) {
    marcarPublicado(id);
    try {
      await setSheetStatus("calendario", id, "publicado");
      toast.success("Publicado e sincronizado com o Sheets.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao sincronizar.");
    }
  }

  const start = startOfWeek(startOfMonth(cursor), { weekStartsOn: 0 });
  const end = endOfWeek(endOfMonth(cursor), { weekStartsOn: 0 });
  const days = eachDayOfInterval({ start, end });

  const pendentes = posts.filter((p) => p.status !== "publicado");

  return (
    <AppShell title="Calendario editorial">
      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <div className="rounded-xl border bg-card shadow-sm">
          <div className="flex items-center justify-between border-b px-4 py-2">
            <h2 className="font-display text-sm font-semibold capitalize">
              {format(cursor, "MMMM 'de' yyyy", { locale: ptBR })}
            </h2>
            <div className="flex gap-1">
              <Button variant="ghost" size="icon" onClick={() => setCursor((d) => subMonths(d, 1))}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setCursor(new Date())}>Hoje</Button>
              <Button variant="ghost" size="icon" onClick={() => setCursor((d) => addMonths(d, 1))}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
          <div className="grid grid-cols-7 border-b bg-muted/40 text-center text-[11px] uppercase text-muted-foreground">
            {["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sab"].map((d) => (
              <div key={d} className="py-1">{d}</div>
            ))}
          </div>
          <div className="grid grid-cols-7">
            {days.map((day) => {
              const dayPosts = posts.filter((p) => isSameDay(new Date(p.dataAgendada), day));
              const outside = !isSameMonth(day, cursor);
              return (
                <div
                  key={day.toISOString()}
                  className={cn(
                    "min-h-24 border-b border-r p-1 text-xs",
                    outside && "bg-muted/30 text-muted-foreground",
                  )}
                >
                  <div className="mb-1 font-medium">{format(day, "d")}</div>
                  <div className="space-y-1">
                    {dayPosts.map((p) => (
                      <button
                        key={p.id}
                        onClick={() => {
                          setEditing(p);
                          setNovaData(p.dataAgendada.slice(0, 10));
                        }}
                        className={cn(
                          "block w-full truncate rounded border px-1 py-0.5 text-left text-[11px]",
                          p.status === "publicado"
                            ? "border-status-success/40 bg-status-success/15 text-status-success-foreground line-through opacity-80"
                            : canalColor[p.canal],
                        )}
                        title={`${p.titulo} · ${canalLabel[p.canal]}`}
                      >
                        {p.titulo}
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="space-y-3">
          <div className="rounded-xl border bg-card shadow-sm">
            <div className="border-b px-4 py-2 font-display text-sm font-semibold">
              Posts pendentes ({pendentes.length})
            </div>
            <ul className="divide-y">
              {pendentes.map((p) => (
                <li key={p.id} className="px-4 py-2 text-sm">
                  <div className="font-medium">{p.titulo}</div>
                  <div className="mt-0.5 flex items-center justify-between text-xs text-muted-foreground">
                    <span>
                      {new Date(p.dataAgendada).toLocaleDateString("pt-BR")} · {canalLabel[p.canal]}
                    </span>
                    <StatusBadge {...postStatusLabel[p.status]} />
                  </div>
                  <div className="mt-2 flex gap-1">
                    <ConfirmAction
                      title="Marcar como publicado?"
                      description="Atualiza o status na aba Calendario do Google Sheets."
                      confirmLabel="Marcar publicado"
                      onConfirm={() => publicar(p.id)}
                      trigger={
                        <Button size="sm" variant="secondary" className="h-7 flex-1 text-xs">
                          <CheckCircle2 className="mr-1 h-3.5 w-3.5" /> Marcar publicado
                        </Button>
                      }
                    />
                  </div>

                </li>
              ))}
              {pendentes.length === 0 && (
                <li className="p-4 text-center text-xs text-muted-foreground">
                  Nenhum post pendente.
                </li>
              )}
            </ul>
          </div>

          <div className="rounded-xl border bg-card p-3 text-[11px] text-muted-foreground shadow-sm">
            Marcar como publicado atualiza o status na aba Calendario do Sheets.
            As metricas aparecem em Performance quando preenchidas na planilha.
            <BarChart3 className="ml-1 inline h-3 w-3 align-text-bottom" />
          </div>
        </div>
      </div>

      <Dialog open={!!editing} onOpenChange={(o) => { if (!o) setEditing(null); }}>
        <DialogContent>
          <DialogHeader><DialogTitle>Reagendar publicacao</DialogTitle></DialogHeader>
          {editing && (
            <div className="space-y-3">
              <div>
                <Label>Titulo</Label>
                <div className="text-sm">{editing.titulo}</div>
              </div>
              <div>
                <Label>Canal</Label>
                <div className="text-sm">{canalLabel[editing.canal]}</div>
              </div>
              <div>
                <Label>Nova data</Label>
                <Input type="date" value={novaData} onChange={(e) => setNovaData(e.target.value)} />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setEditing(null)}>Cancelar</Button>
            {editing?.status !== "publicado" && (
              <Button
                variant="secondary"
                onClick={() => {
                  if (!editing) return;
                  void publicar(editing.id);
                  setEditing(null);
                }}
              >
                Marcar como publicado
              </Button>
            )}
            <Button
              onClick={() => {
                if (!editing || !novaData) return;
                updatePost(editing.id, {
                  dataAgendada: new Date(`${novaData}T12:00:00`).toISOString(),
                  status: "agendado",
                });
                toast.success("Publicacao reagendada.");
                setEditing(null);
              }}
            >
              Salvar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppShell>
  );
}
