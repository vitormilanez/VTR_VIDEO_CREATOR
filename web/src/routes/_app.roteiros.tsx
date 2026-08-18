import { createFileRoute, Link, Outlet } from "@tanstack/react-router";
import { useState } from "react";
import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { DataToolbar } from "@/components/data-toolbar";
import { EmptyState } from "@/components/empty-state";
import { StatusChips } from "@/components/status-chips";
import { WeeklyArchiveSwitch } from "@/components/weekly-archive-switch";
import { ConfirmAction } from "@/components/confirm-action";
import { CreateScriptFromDraftDialog } from "@/components/create-script-from-draft-dialog";
import { deleteScript } from "@/lib/api/local";
import { familiaLabel, scriptStatusLabel } from "@/lib/status";
import { useStore } from "@/lib/store";
import { splitWeekly, type WeeklyView } from "@/lib/weekly-archive";
import type { RiskLevel, Script, ScriptStatus } from "@/lib/mock-data";
import { cn } from "@/lib/utils";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  CircleAlert,
  CircleCheck,
  ExternalLink,
  FileText,
  Loader2,
  MessageSquareText,
  PanelsTopLeft,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

export const Route = createFileRoute("/_app/roteiros")({
  head: () => ({
    meta: [
      { title: "Roteiros | AI Video Creator" },
      { name: "description", content: "Roteiros com validacao medica antes da producao." },
      { property: "og:title", content: "Roteiros | AI Video Creator" },
      { property: "og:description", content: "Fila de roteiros medicos." },
    ],
  }),
  component: RoteirosLayout,
});

function RoteirosLayout() {
  return <Outlet />;
}

export function RoteirosPage() {
  const scripts = useStore((s) => s.scripts);
  const videoJobs = useStore((s) => s.videoJobs);
  const calendarPosts = useStore((s) => s.calendarPosts);
  const removeScript = useStore((s) => s.removeScript);
  const [status, setStatus] = useState("todos");
  const [prioridade, setPrioridade] = useState("todas");
  const [busca, setBusca] = useState("");
  const [weeklyView, setWeeklyView] = useState<WeeklyView>("current");
  const [selectedScript, setSelectedScript] = useState<Script | null>(null);
  const [deletingScriptId, setDeletingScriptId] = useState<string | null>(null);

  const weekly = splitWeekly(scripts, (script) => script.criadoEm);
  const weeklyScripts = weeklyView === "current" ? weekly.current : weekly.archive;

  const filtered = weeklyScripts.filter((s) => {
    if (status !== "todos" && s.status !== status) return false;
    if (prioridade !== "todas" && s.prioridade !== prioridade) return false;
    const searchable = [s.titulo, s.tema, s.hook, s.cuidadosMedicos].join(" ").toLowerCase();
    if (busca && !searchable.includes(busca.toLowerCase())) return false;
    return true;
  });

  const ordered = [...filtered].sort(
    (a, b) => new Date(b.criadoEm).getTime() - new Date(a.criadoEm).getTime(),
  );

  const counts: Record<ScriptStatus, number> = {
    aguardando_validacao: 0,
    em_revisao: 0,
    aprovado_clinicamente: 0,
    rejeitado: 0,
  };
  weeklyScripts.forEach((s) => (counts[s.status] += 1));
  const usedScriptIds = new Set(
    videoJobs.filter((job) => job.status !== "erro").map((job) => job.scriptId),
  );
  const usedCount = weeklyScripts.filter((script) => usedScriptIds.has(script.id)).length;
  const scheduledScriptIds = new Set(
    calendarPosts
      .map((post) => post.scriptId)
      .filter((scriptId): scriptId is string => Boolean(scriptId)),
  );

  async function excluirRoteiro(script: Script) {
    if (deletingScriptId) return;
    setDeletingScriptId(script.id);
    try {
      await deleteScript(script.id);
      removeScript(script.id);
      if (selectedScript?.id === script.id) setSelectedScript(null);
      toast.success(`Roteiro “${script.titulo}” excluído.`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Não foi possível excluir o roteiro.");
    } finally {
      setDeletingScriptId(null);
    }
  }

  return (
    <AppShell title="Roteiros" actions={<CreateScriptFromDraftDialog />}>
      <WeeklyArchiveSwitch
        className="mb-3"
        value={weeklyView}
        onChange={setWeeklyView}
        currentCount={weekly.current.length}
        archiveCount={weekly.archive.length}
      />
      {usedCount > 0 ? (
        <div className="mb-3 flex items-center gap-2 rounded-md border border-status-success/30 bg-status-success/5 px-3 py-2 text-xs">
          <CircleCheck className="h-4 w-4 shrink-0 text-status-success" />
          <span>
            {usedCount === 1
              ? "1 roteiro já foi utilizado em vídeo. Ele está identificado na lista."
              : `${usedCount} roteiros já foram utilizados em vídeos. Eles estão identificados na lista.`}
          </span>
        </div>
      ) : null}
      <StatusChips
        className="mb-3"
        value={status}
        onChange={setStatus}
        options={[
          {
            value: "aguardando_validacao",
            label: "Rascunho",
            tone: "neutral",
            count: counts.aguardando_validacao,
          },
          { value: "em_revisao", label: "Em edicao", tone: "info", count: counts.em_revisao },
          {
            value: "aprovado_clinicamente",
            label: "Prontos",
            tone: "success",
            count: counts.aprovado_clinicamente,
          },
          { value: "rejeitado", label: "Rejeitados", tone: "neutral", count: counts.rejeitado },
        ]}
      />
      <DataToolbar search={busca} onSearch={setBusca} placeholder="Buscar roteiro...">
        <Select value={prioridade} onValueChange={setPrioridade}>
          <SelectTrigger className="h-8 w-40">
            <SelectValue placeholder="Prioridade" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="todas">Todas as prioridades</SelectItem>
            <SelectItem value="alta">Alta</SelectItem>
            <SelectItem value="media">Media</SelectItem>
            <SelectItem value="baixa">Baixa</SelectItem>
          </SelectContent>
        </Select>
      </DataToolbar>

      {ordered.length === 0 ? (
        <EmptyState
          icon={<FileText className="h-4 w-4" />}
          title={
            weeklyScripts.length === 0
              ? weeklyView === "current"
                ? "Nenhum roteiro criado nesta semana"
                : "O arquivo de roteiros está vazio"
              : "Nenhum roteiro encontrado"
          }
          description={
            weeklyScripts.length === 0
              ? weeklyView === "current"
                ? "Quando uma ideia virar roteiro, ela aparecerá aqui automaticamente."
                : "Roteiros de semanas anteriores serão preservados aqui."
              : "Ajuste os filtros para ampliar os resultados."
          }
          action={
            <Button asChild size="sm" variant="secondary">
              <Link to="/ideias">Ir para Ideias</Link>
            </Button>
          }
        />
      ) : (
        <TooltipProvider delayDuration={180}>
          <div className="overflow-x-auto rounded-xl border bg-card shadow-sm">
            <Table className="min-w-[1040px] table-fixed">
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[26%]">Roteiro</TableHead>
                  <TableHead className="w-[22%]">Resumo</TableHead>
                  <TableHead className="w-[22%]">Fala</TableHead>
                  <TableHead className="w-[9%] text-center">Sinais</TableHead>
                  <TableHead className="w-[9%]">Status</TableHead>
                  <TableHead className="w-[12%] text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {ordered.map((s) => {
                  const hasVideo = usedScriptIds.has(s.id);
                  const hasCalendarPost = scheduledScriptIds.has(s.id);
                  const deletionProtected = hasVideo || hasCalendarPost;
                  return (
                    <TableRow key={s.id} className="group">
                      <TableCell className="align-top py-4">
                        <Link
                          to="/roteiros/$id"
                          params={{ id: s.id }}
                          className="line-clamp-2 font-semibold leading-5 transition-colors hover:text-status-info hover:underline"
                        >
                          {s.titulo}
                        </Link>
                        <div className="mt-2 flex flex-wrap items-center gap-1.5">
                          <span className="rounded-md bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                            {familiaLabel[s.categoria]}
                          </span>
                          {usedScriptIds.has(s.id) ? (
                            <Badge
                              variant="outline"
                              className="h-5 border-status-success/40 px-1.5 text-[10px] text-status-success"
                            >
                              <CircleCheck className="mr-1 h-3 w-3" />
                              Vídeo produzido
                            </Badge>
                          ) : null}
                        </div>
                      </TableCell>
                      <TableCell className="align-top py-4">
                        <ScriptPreviewButton
                          label="Abrir resumo completo"
                          text={scriptSummary(s)}
                          onClick={() => setSelectedScript(s)}
                        />
                      </TableCell>
                      <TableCell className="align-top py-4">
                        <ScriptPreviewButton
                          label="Abrir fala completa"
                          text={scriptSpokenText(s)}
                          onClick={() => setSelectedScript(s)}
                        />
                      </TableCell>
                      <TableCell className="align-top py-3 text-center">
                        <ScriptSignals script={s} />
                      </TableCell>
                      <TableCell className="align-top py-4">
                        <StatusBadge {...scriptStatusLabel[s.status]} />
                      </TableCell>
                      <TableCell className="align-top py-3 text-right">
                        <div className="flex justify-end gap-1">
                          <Button asChild size="sm" variant="secondary">
                            <Link to="/packs" search={{ scriptId: s.id }}>
                              <PanelsTopLeft className="mr-1 h-3.5 w-3.5" /> Pack
                            </Link>
                          </Button>
                          <Button asChild size="icon" variant="ghost">
                            <Link
                              to="/roteiros/$id"
                              params={{ id: s.id }}
                              aria-label={`Abrir roteiro ${s.titulo}`}
                            >
                              <ExternalLink className="h-3.5 w-3.5" />
                            </Link>
                          </Button>
                          <ConfirmAction
                            destructive
                            title={
                              deletionProtected
                                ? "Este roteiro não pode ser excluído"
                                : "Excluir roteiro?"
                            }
                            description={
                              deletionProtected
                                ? hasVideo
                                  ? "Existe um vídeo ou uma prévia vinculada. O roteiro será preservado para manter o histórico da produção."
                                  : "Existe um item do Calendário vinculado. Remova ou altere o agendamento antes de excluir o roteiro."
                                : `“${s.titulo}” será removido do banco de dados junto com Scene Plan, slides e Pack locais. Esta ação não pode ser desfeita pelo app.`
                            }
                            confirmLabel="Excluir roteiro"
                            confirmDisabled={deletionProtected || deletingScriptId === s.id}
                            onConfirm={() => void excluirRoteiro(s)}
                            trigger={
                              <Button
                                size="icon"
                                variant="ghost"
                                aria-label={`Excluir roteiro ${s.titulo}`}
                                title="Excluir roteiro"
                                disabled={deletingScriptId !== null}
                                className="text-muted-foreground hover:bg-status-danger/10 hover:text-status-danger"
                              >
                                {deletingScriptId === s.id ? (
                                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                ) : (
                                  <Trash2 className="h-3.5 w-3.5" />
                                )}
                              </Button>
                            }
                          />
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </TooltipProvider>
      )}

      <Dialog
        open={selectedScript !== null}
        onOpenChange={(open) => {
          if (!open) setSelectedScript(null);
        }}
      >
        <DialogContent className="max-h-[85vh] max-w-3xl overflow-y-auto">
          {selectedScript ? (
            <>
              <DialogHeader className="pr-8">
                <DialogTitle className="leading-snug">{selectedScript.titulo}</DialogTitle>
                <DialogDescription className="flex flex-wrap items-center gap-2 pt-1">
                  <span>{familiaLabel[selectedScript.categoria]}</span>
                  <span aria-hidden="true">•</span>
                  <span>{selectedScript.formatoSugerido}</span>
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-5">
                <section className="rounded-lg border bg-muted/30 p-4">
                  <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    <FileText className="h-4 w-4 text-status-info" /> Resumo
                  </div>
                  <p className="text-sm leading-6">{scriptSummary(selectedScript)}</p>
                </section>
                <section className="rounded-lg border border-status-info/25 bg-status-info/5 p-4">
                  <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    <MessageSquareText className="h-4 w-4 text-status-info" /> Fala completa
                  </div>
                  <p className="whitespace-pre-line text-sm leading-7">
                    {scriptSpokenText(selectedScript)}
                  </p>
                </section>
                <div className="flex justify-end">
                  <Button asChild>
                    <Link to="/roteiros/$id" params={{ id: selectedScript.id }}>
                      Abrir roteiro
                      <ExternalLink className="ml-2 h-4 w-4" />
                    </Link>
                  </Button>
                </div>
              </div>
            </>
          ) : null}
        </DialogContent>
      </Dialog>
    </AppShell>
  );
}

function ScriptPreviewButton({
  label,
  text,
  onClick,
}: {
  label: string;
  text: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="w-full cursor-pointer rounded-md p-1 text-left transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <span className="line-clamp-2 text-xs leading-5 text-muted-foreground">{text}</span>
      <span className="mt-1 block text-[10px] font-medium text-status-info opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
        Ver completo
      </span>
    </button>
  );
}

const riskDotClass: Record<RiskLevel, string> = {
  baixo: "bg-status-success ring-status-success/25",
  medio: "bg-status-warn ring-status-warn/30",
  alto: "bg-status-danger ring-status-danger/25",
};

const riskDescription: Record<RiskLevel, string> = {
  baixo: "Risco baixo — conteúdo educativo com baixa chance de interpretação perigosa.",
  medio: "Risco médio — exige atenção ao contexto e revisão cuidadosa da linguagem.",
  alto: "Risco alto — tema sensível que requer validação médica antes da produção.",
};

function ScriptSignals({ script }: { script: Script }) {
  return (
    <div className="flex items-center justify-center gap-1">
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            aria-label={riskDescription[script.risco]}
            className="inline-flex h-9 w-9 cursor-help items-center justify-center rounded-md transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <span
              aria-hidden="true"
              className={cn("h-3 w-3 rounded-full ring-4", riskDotClass[script.risco])}
            />
          </button>
        </TooltipTrigger>
        <TooltipContent className="max-w-xs border bg-popover p-3 text-left leading-5 text-popover-foreground shadow-lg">
          {riskDescription[script.risco]}
        </TooltipContent>
      </Tooltip>
      {script.cuidadosMedicos ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              aria-label="Ver cuidados médicos"
              className="inline-flex h-9 w-9 cursor-help items-center justify-center rounded-md text-status-warn-foreground transition-colors hover:bg-status-warn/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <CircleAlert className="h-4 w-4" />
            </button>
          </TooltipTrigger>
          <TooltipContent className="max-w-sm border bg-popover p-3 text-left text-popover-foreground shadow-lg">
            <div className="mb-1 text-xs font-semibold">Cuidados médicos</div>
            <p className="text-xs leading-5 text-muted-foreground">{script.cuidadosMedicos}</p>
          </TooltipContent>
        </Tooltip>
      ) : null}
    </div>
  );
}

function scriptSummary(script: Script): string {
  return script.hook?.trim() || script.tema?.trim() || "Resumo não informado.";
}

function scriptSpokenText(script: Script): string {
  if (script.textoFalado?.trim()) return script.textoFalado.trim();
  return [script.hook, script.dorConflito, script.explicacaoSimples, script.virada, script.cta]
    .map((part) => part?.trim())
    .filter(Boolean)
    .join("\n\n");
}
