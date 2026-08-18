import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  Captions,
  CheckCircle2,
  ClipboardPaste,
  Clock3,
  Film,
  Loader2,
  Mic2,
  Plus,
  RotateCcw,
  Save,
  Sparkles,
  Trash2,
  UsersRound,
} from "lucide-react";
import { toast } from "sonner";

import { ConfirmAction } from "@/components/confirm-action";
import { AvatarPicker } from "@/components/script-editor/avatar-studio";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  fetchPodcastPlan,
  generatePodcastDialogue,
  savePodcastPlan,
  submitPodcastGeneration,
  type HeyGenCatalog,
  type MusicTrack,
  type PodcastGenerationResult,
  type PodcastParticipant,
  type PodcastPlan,
  type PodcastSpeakerId,
  type PodcastTurn,
  type VoiceMood,
} from "@/lib/api/local";
import { parsePodcastScript, type ImportedPodcastTurn } from "@/lib/podcast-script";
import type { DurationPreset, MedicalReviewStatus } from "@/lib/script-editor";
import type { VideoJob } from "@/lib/mock-data";
import { cn } from "@/lib/utils";

type PodcastDraft = Omit<PodcastPlan, "scriptId" | "updatedAt">;

type PreviousConversation = Pick<PodcastDraft, "title" | "turns">;

type PaidScriptVersion = {
  scriptRevision: number;
  finalSpeechHash: string;
  contractVersion: string;
};

type StudioDefaults = {
  avatarA?: string;
  avatarB?: string | null;
  orientation?: "portrait" | "landscape";
  captions?: boolean;
  scenes?: Array<{ id?: string; speaker?: PodcastSpeakerId; text?: string }>;
};

type PodcastDuration = 30 | 45 | 60 | 90 | 120 | 180;

const DURATION_OPTIONS: PodcastDuration[] = [30, 45, 60, 90, 120, 180];

function podcastDuration(value: DurationPreset): PodcastDuration {
  return DURATION_OPTIONS.includes(value as PodcastDuration) ? (value as PodcastDuration) : 30;
}

const SPEAKER_STYLES: Record<PodcastSpeakerId, { badge: string; panel: string }> = {
  a: {
    badge: "border-sky-200 bg-sky-50 text-sky-800",
    panel: "border-sky-200/80 bg-sky-50/40",
  },
  b: {
    badge: "border-emerald-200 bg-emerald-50 text-emerald-800",
    panel: "border-emerald-200/80 bg-emerald-50/40",
  },
};

function newTurnId() {
  return (
    globalThis.crypto?.randomUUID?.() ?? `turn-${Date.now()}-${Math.random().toString(36).slice(2)}`
  );
}

function readStudioDefaults(): StudioDefaults | null {
  try {
    const raw = localStorage.getItem("ai-video-creator-studio-defaults");
    if (!raw) return null;
    return JSON.parse(raw) as StudioDefaults;
  } catch {
    return null;
  }
}

function avatarFromStudioId(
  studioId: string | null | undefined,
  avatars: HeyGenCatalog["avatars"],
) {
  if (!studioId) return undefined;
  return avatars.find((avatar) => avatar.id === studioId || avatar.groupId === studioId);
}

function initialParticipants(
  catalog: HeyGenCatalog | null,
): [PodcastParticipant, PodcastParticipant] {
  const avatars = catalog?.avatars || [];
  const voices = catalog?.voices || [];
  const defaults = readStudioDefaults();
  const firstAvatar = avatarFromStudioId(defaults?.avatarA, avatars) || avatars[0];
  const secondAvatar =
    avatarFromStudioId(defaults?.avatarB, avatars) ||
    avatars.find((avatar) => avatar.id !== firstAvatar?.id) ||
    avatars[1];
  const firstVoice = firstAvatar?.defaultVoiceId || catalog?.defaultVoiceId || voices[0]?.id || "";
  const secondVoice =
    secondAvatar?.defaultVoiceId ||
    voices.find((voice) => voice.id !== firstVoice)?.id ||
    voices[1]?.id ||
    "";
  return [
    {
      id: "a",
      name: "Apresentador",
      avatarId: firstAvatar?.id || "",
      voiceId: firstVoice,
    },
    {
      id: "b",
      name: "Especialista",
      avatarId: secondAvatar?.id || "",
      voiceId: secondVoice,
    },
  ];
}

function initialTurns(sourceText: string): PodcastTurn[] {
  const defaults = readStudioDefaults();
  const storedTurns = (defaults?.scenes || [])
    .map((scene, index) => ({
      id: scene.id || newTurnId(),
      order: index + 1,
      speakerId: scene.speaker === "b" ? ("b" as const) : ("a" as const),
      text: String(scene.text || "").trim(),
    }))
    .filter((scene) => scene.text);
  if (storedTurns.length >= 2) return storedTurns;
  return [
    {
      id: newTurnId(),
      order: 1,
      speakerId: "a",
      text: "",
    },
    {
      id: newTurnId(),
      order: 2,
      speakerId: "b",
      text: sourceText.trim(),
    },
  ];
}

function buildInitialDraft(
  title: string,
  sourceText: string,
  catalog: HeyGenCatalog | null,
  fallbackOrientation: "portrait" | "landscape",
): PodcastDraft {
  const defaults = readStudioDefaults();
  return {
    title: `Podcast — ${title}`,
    orientation: defaults?.orientation || fallbackOrientation,
    captions: defaults?.captions ?? true,
    transitionStyle: "hard_cut",
    musicTrackId: null,
    musicVolume: 0.08,
    participants: initialParticipants(catalog),
    turns: initialTurns(sourceText),
  };
}

function normalizeOrders(turns: PodcastTurn[]) {
  return turns.map((turn, index) => ({ ...turn, order: index + 1 }));
}

function conversationTurns(turns: ImportedPodcastTurn[]): PodcastTurn[] {
  return turns.map((turn, index) => ({
    id: newTurnId(),
    order: index + 1,
    speakerId: turn.speakerId,
    text: turn.text.trim(),
  }));
}

function draftSignature(draft: PodcastDraft) {
  return JSON.stringify({
    ...draft,
    participants: draft.participants.map((participant) => ({ ...participant })),
    turns: normalizeOrders(draft.turns).map((turn) => ({ ...turn, text: turn.text.trim() })),
  });
}

function dialogueText(turns: PodcastTurn[]) {
  return turns
    .map((turn) => turn.text.trim())
    .filter(Boolean)
    .join("\n\n");
}

function planProblem(draft: PodcastDraft): string | null {
  const [speakerA, speakerB] = draft.participants;
  if (!speakerA.name.trim() || !speakerB.name.trim()) return "Dê um nome aos dois participantes.";
  if (!speakerA.avatarId || !speakerB.avatarId) return "Escolha os dois avatares.";
  if (speakerA.avatarId === speakerB.avatarId)
    return "Use um avatar diferente para cada participante.";
  if (!speakerA.voiceId || !speakerB.voiceId) return "Escolha uma voz para cada participante.";
  if (speakerA.voiceId === speakerB.voiceId)
    return "Use vozes diferentes para identificar quem fala.";
  if (draft.turns.length < 2) return "Adicione pelo menos duas falas.";
  if (draft.turns.some((turn) => !turn.text.trim())) return "Preencha ou remova as falas vazias.";
  const speakers = new Set(draft.turns.map((turn) => turn.speakerId));
  if (!speakers.has("a") || !speakers.has("b")) return "Os dois participantes precisam falar.";
  if (dialogueText(draft.turns).length < 20) return "O diálogo ainda está curto demais.";
  return null;
}

export function PodcastEditor({
  scriptId,
  scriptTitle,
  sourceText,
  catalog,
  catalogLoading,
  catalogError,
  musicTracks,
  durationSeconds,
  onDurationChange,
  speechMode,
  voiceMood,
  medicalReviewStatus,
  humanReviewApproved,
  fallbackOrientation,
  onPersistSpeech,
  onSubmitted,
}: {
  scriptId: string;
  scriptTitle: string;
  sourceText: string;
  catalog: HeyGenCatalog | null;
  catalogLoading: boolean;
  catalogError: string | null;
  musicTracks: MusicTrack[];
  durationSeconds: DurationPreset;
  onDurationChange: (duration: DurationPreset) => void;
  speechMode: "natural" | "fiel" | "direto" | "enfatico";
  voiceMood: VoiceMood;
  medicalReviewStatus: MedicalReviewStatus;
  humanReviewApproved: boolean;
  fallbackOrientation: "portrait" | "landscape";
  onPersistSpeech: (text: string) => Promise<PaidScriptVersion>;
  onSubmitted: (jobs: VideoJob[]) => void;
}) {
  const initialInputsRef = useRef({
    scriptId,
    scriptTitle,
    sourceText,
    catalog,
    fallbackOrientation,
  });
  if (initialInputsRef.current.scriptId !== scriptId) {
    initialInputsRef.current = {
      scriptId,
      scriptTitle,
      sourceText,
      catalog,
      fallbackOrientation,
    };
  }
  const [draft, setDraft] = useState<PodcastDraft>(() =>
    buildInitialDraft(scriptTitle, sourceText, catalog, fallbackOrientation),
  );
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [savedSignature, setSavedSignature] = useState("");
  const [generationPreview, setGenerationPreview] = useState<PodcastGenerationResult | null>(null);
  const [generatingDialogue, setGeneratingDialogue] = useState(false);
  const [claudeDirection, setClaudeDirection] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const [pastedScript, setPastedScript] = useState("");
  const [importError, setImportError] = useState<string | null>(null);
  const [previousConversation, setPreviousConversation] = useState<PreviousConversation | null>(
    null,
  );
  const [conversationNotice, setConversationNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setPreviousConversation(null);
    setConversationNotice(null);
    setImportOpen(false);
    setPastedScript("");
    setImportError(null);
    fetchPodcastPlan(scriptId)
      .then((saved) => {
        if (cancelled) return;
        if (saved) {
          const restored: PodcastDraft = {
            title: saved.title,
            orientation: saved.orientation,
            captions: saved.captions,
            transitionStyle: "hard_cut",
            musicTrackId: saved.musicTrackId || null,
            musicVolume: saved.musicVolume ?? 0.08,
            participants: saved.participants,
            turns: normalizeOrders(saved.turns),
          };
          setDraft(restored);
          setSavedSignature(draftSignature(restored));
        } else {
          const initialInputs = initialInputsRef.current;
          const initial = buildInitialDraft(
            initialInputs.scriptTitle,
            initialInputs.sourceText,
            initialInputs.catalog,
            initialInputs.fallbackOrientation,
          );
          setDraft(initial);
          setSavedSignature("");
        }
      })
      .catch((error) => {
        if (!cancelled) {
          toast.error(error instanceof Error ? error.message : "Não foi possível abrir o podcast.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [scriptId]);

  useEffect(() => {
    if (loading || !catalog?.avatars.length) return;
    setDraft((current) => {
      const defaults = initialParticipants(catalog);
      const avatarIds = new Set(catalog.avatars.map((avatar) => avatar.id));
      const voiceIds = new Set(catalog.voices.map((voice) => voice.id));
      const participants = current.participants.map((participant, index) => {
        const fallback = defaults[index];
        const avatarId = avatarIds.has(participant.avatarId)
          ? participant.avatarId
          : fallback.avatarId;
        const avatar = catalog.avatars.find((candidate) => candidate.id === avatarId);
        const voiceId = voiceIds.has(participant.voiceId)
          ? participant.voiceId
          : avatar?.defaultVoiceId || fallback.voiceId;
        return { ...participant, avatarId, voiceId };
      }) as [PodcastParticipant, PodcastParticipant];
      if (participants[1].avatarId === participants[0].avatarId) {
        participants[1] = {
          ...participants[1],
          avatarId:
            catalog.avatars.find((avatar) => avatar.id !== participants[0].avatarId)?.id || "",
        };
      }
      if (participants[1].voiceId === participants[0].voiceId) {
        participants[1] = {
          ...participants[1],
          voiceId: catalog.voices.find((voice) => voice.id !== participants[0].voiceId)?.id || "",
        };
      }
      return { ...current, participants };
    });
  }, [catalog, loading]);

  const problem = useMemo(() => planProblem(draft), [draft]);
  const currentSignature = useMemo(() => draftSignature(draft), [draft]);
  const dirty = currentSignature !== savedSignature;
  const wordCount = useMemo(
    () => dialogueText(draft.turns).split(/\s+/).filter(Boolean).length,
    [draft.turns],
  );
  const estimatedSeconds = Math.max(0, Math.round(wordCount / 2.4));
  const medicalBlocked = medicalReviewStatus === "required" && !humanReviewApproved;
  const participantById = useMemo(
    () => new Map(draft.participants.map((participant) => [participant.id, participant])),
    [draft.participants],
  );

  function updateParticipant(speakerId: PodcastSpeakerId, patch: Partial<PodcastParticipant>) {
    setDraft((current) => ({
      ...current,
      participants: current.participants.map((participant) =>
        participant.id === speakerId ? { ...participant, ...patch } : participant,
      ) as [PodcastParticipant, PodcastParticipant],
    }));
  }

  function chooseParticipantAvatar(speakerId: PodcastSpeakerId, avatarId: string) {
    const avatar = catalog?.avatars.find((candidate) => candidate.id === avatarId);
    updateParticipant(speakerId, {
      avatarId,
      ...(avatar?.defaultVoiceId ? { voiceId: avatar.defaultVoiceId } : {}),
    });
  }

  function updateTurn(turnId: string, patch: Partial<PodcastTurn>) {
    setDraft((current) => ({
      ...current,
      turns: current.turns.map((turn) => (turn.id === turnId ? { ...turn, ...patch } : turn)),
    }));
  }

  function addTurn(afterIndex = draft.turns.length - 1) {
    setDraft((current) => {
      const previous = current.turns[afterIndex];
      const nextSpeaker: PodcastSpeakerId = previous?.speakerId === "a" ? "b" : "a";
      const turns = [...current.turns];
      turns.splice(afterIndex + 1, 0, {
        id: newTurnId(),
        order: afterIndex + 2,
        speakerId: nextSpeaker,
        text: "",
      });
      return { ...current, turns: normalizeOrders(turns) };
    });
  }

  function moveTurn(index: number, direction: -1 | 1) {
    setDraft((current) => {
      const destination = index + direction;
      if (destination < 0 || destination >= current.turns.length) return current;
      const turns = [...current.turns];
      [turns[index], turns[destination]] = [turns[destination], turns[index]];
      return { ...current, turns: normalizeOrders(turns) };
    });
  }

  function removeTurn(turnId: string) {
    setDraft((current) => ({
      ...current,
      turns: normalizeOrders(current.turns.filter((turn) => turn.id !== turnId)),
    }));
  }

  function applyConversation(
    turns: ImportedPodcastTurn[],
    notice: string,
    suggestedTitle?: string,
  ) {
    setPreviousConversation({ title: draft.title, turns: draft.turns });
    setDraft((current) => ({
      ...current,
      title: suggestedTitle?.trim() || current.title,
      turns: conversationTurns(turns),
    }));
    setGenerationPreview(null);
    setConversationNotice(notice);
  }

  function undoConversationChange() {
    if (!previousConversation) return;
    setDraft((current) => ({
      ...current,
      title: previousConversation.title,
      turns: previousConversation.turns,
    }));
    setPreviousConversation(null);
    setConversationNotice(null);
    toast.success("Conversa anterior restaurada.");
  }

  async function handleGenerateDialogue() {
    setGeneratingDialogue(true);
    try {
      const [host, guest] = draft.participants;
      const result = await generatePodcastDialogue(scriptId, {
        sourceText,
        hostName: host.name.trim(),
        guestName: guest.name.trim(),
        direction: claudeDirection.trim(),
        durationSeconds: podcastDuration(durationSeconds),
      });
      applyConversation(
        result.turns,
        `${result.turnCount} falas do Claude aplicadas ao rascunho. Revise antes de salvar.`,
        result.title,
      );
      toast.success("Conversa criada pelo Claude. Nada foi salvo ainda.");
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Não foi possível gerar a conversa com Claude.",
      );
    } finally {
      setGeneratingDialogue(false);
    }
  }

  function handleImportScript() {
    try {
      const imported = parsePodcastScript(pastedScript);
      applyConversation(
        imported,
        `${imported.length} falas importadas para o rascunho. Revise antes de salvar.`,
      );
      setImportError(null);
      setImportOpen(false);
      setPastedScript("");
      toast.success("Roteiro HOST/GUEST importado. Nada foi salvo ainda.");
    } catch (error) {
      setImportError(error instanceof Error ? error.message : "Não foi possível ler o roteiro.");
    }
  }

  async function persistPodcast() {
    const validation = planProblem(draft);
    if (validation) throw new Error(validation);
    const version = await onPersistSpeech(dialogueText(draft.turns));
    const saved = await savePodcastPlan(scriptId, {
      ...draft,
      title: draft.title.trim(),
      participants: draft.participants.map((participant) => ({
        ...participant,
        name: participant.name.trim(),
      })) as [PodcastParticipant, PodcastParticipant],
      turns: normalizeOrders(draft.turns).map((turn) => ({ ...turn, text: turn.text.trim() })),
    });
    const nextDraft: PodcastDraft = {
      title: saved.title,
      orientation: saved.orientation,
      captions: saved.captions,
      transitionStyle: "hard_cut",
      musicTrackId: saved.musicTrackId || null,
      musicVolume: saved.musicVolume ?? 0.08,
      participants: saved.participants,
      turns: saved.turns,
    };
    setDraft(nextDraft);
    setSavedSignature(draftSignature(nextDraft));
    return version;
  }

  async function handleSave() {
    setSaving(true);
    try {
      await persistPodcast();
      toast.success("Podcast salvo e fala final sincronizada com o roteiro.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Não foi possível salvar o podcast.");
    } finally {
      setSaving(false);
    }
  }

  async function handleSubmit() {
    setSubmitting(true);
    try {
      const version = await persistPodcast();
      const result = await submitPodcastGeneration(scriptId, {
        orientation: draft.orientation,
        durationSeconds,
        speechMode,
        voiceMood,
        captions: draft.captions,
        expectedScriptRevision: version.scriptRevision,
        expectedFinalSpeechHash: version.finalSpeechHash,
        contractVersion: version.contractVersion,
      });
      setGenerationPreview(result.generation);
      onSubmitted(result.jobs);
      toast.success(
        `${result.jobs.length} ${result.jobs.length === 1 ? "fala enviada" : "falas enviadas"} para produção.`,
      );
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Não foi possível gerar o podcast.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-64 items-center justify-center rounded-xl border bg-card text-sm text-muted-foreground shadow-sm">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Abrindo estrutura do podcast...
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <section className="overflow-hidden rounded-xl border bg-card shadow-sm">
        <div className="border-b bg-gradient-to-r from-sky-50/80 via-background to-emerald-50/70 px-4 py-4 sm:px-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-start gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-sky-200 bg-white text-sky-700 shadow-sm">
                <UsersRound className="h-5 w-5" />
              </span>
              <div>
                <h2 className="font-display text-base font-semibold">Podcast com dois avatares</h2>
                <p className="mt-1 max-w-2xl text-xs leading-5 text-muted-foreground">
                  Cada fala é produzida com o avatar e a voz do participante correto. No final, o
                  app reúne os clipes em uma única linha do tempo com cortes secos.
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2 text-[11px] text-muted-foreground">
              <span className="rounded-full border bg-background px-2.5 py-1">
                {draft.turns.length} falas
              </span>
              <span className="rounded-full border bg-background px-2.5 py-1">
                {wordCount} palavras
              </span>
              <span className="rounded-full border bg-background px-2.5 py-1">
                ≈ {estimatedSeconds}s
              </span>
            </div>
          </div>
        </div>

        <div className="grid gap-4 p-4 sm:p-5 lg:grid-cols-2">
          {draft.participants.map((participant) => {
            const style = SPEAKER_STYLES[participant.id];
            return (
              <div
                key={participant.id}
                className={cn("space-y-3 rounded-xl border p-3", style.panel)}
              >
                <div className="flex items-center justify-between gap-2">
                  <span
                    className={cn(
                      "rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
                      style.badge,
                    )}
                  >
                    Participante {participant.id.toUpperCase()}
                  </span>
                  <span className="text-[11px] text-muted-foreground">
                    {draft.turns.filter((turn) => turn.speakerId === participant.id).length} falas
                  </span>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor={`podcast-name-${participant.id}`} className="text-xs">
                    Nome no roteiro
                  </Label>
                  <Input
                    id={`podcast-name-${participant.id}`}
                    value={participant.name}
                    maxLength={80}
                    onChange={(event) =>
                      updateParticipant(participant.id, { name: event.target.value })
                    }
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Avatar</Label>
                  <AvatarPicker
                    value={participant.avatarId}
                    avatars={catalog?.avatars || []}
                    loading={catalogLoading}
                    error={catalogError}
                    onChange={(avatarId) => chooseParticipantAvatar(participant.id, avatarId)}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor={`podcast-voice-${participant.id}`} className="text-xs">
                    Voz
                  </Label>
                  <Select
                    value={participant.voiceId}
                    onValueChange={(voiceId) => updateParticipant(participant.id, { voiceId })}
                  >
                    <SelectTrigger
                      id={`podcast-voice-${participant.id}`}
                      aria-label={`Voz de ${participant.name || `participante ${participant.id}`}`}
                    >
                      <SelectValue placeholder="Escolha uma voz" />
                    </SelectTrigger>
                    <SelectContent>
                      {(catalog?.voices || []).map((voice) => (
                        <SelectItem key={voice.id} value={voice.id}>
                          {voice.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section className="rounded-xl border bg-card p-4 shadow-sm sm:p-5">
        <div>
          <h2 className="font-display text-sm font-semibold">Crie a conversa</h2>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            Comece com uma proposta do Claude ou cole um diálogo pronto. Nos dois casos, o resultado
            entra apenas como rascunho para sua revisão.
          </p>
        </div>

        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <div className="rounded-xl border border-sky-200/80 bg-sky-50/40 p-4">
            <div className="flex items-start gap-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-sky-200 bg-white text-sky-700 shadow-sm">
                <Sparkles className="h-4 w-4" />
              </span>
              <div>
                <h3 className="text-sm font-semibold">Gerar com Claude</h3>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  O Claude usa o título e a fala atual como fonte, alternando perguntas curtas e
                  respostas educativas.
                </p>
              </div>
            </div>
            <div className="mt-3 space-y-1.5">
              <Label htmlFor="podcast-claude-direction" className="text-xs">
                Orientação opcional
              </Label>
              <Input
                id="podcast-claude-direction"
                value={claudeDirection}
                maxLength={800}
                placeholder="Ex.: priorize como funciona, resultados e cuidados."
                onChange={(event) => setClaudeDirection(event.target.value)}
              />
            </div>
            <Button
              type="button"
              size="sm"
              className="mt-3"
              disabled={
                generatingDialogue ||
                saving ||
                submitting ||
                sourceText.trim().length < 20 ||
                draft.participants.some((participant) => !participant.name.trim())
              }
              onClick={() => void handleGenerateDialogue()}
            >
              {generatingDialogue ? (
                <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="mr-1.5 h-4 w-4" />
              )}
              {generatingDialogue ? "Criando conversa..." : "Gerar conversa"}
            </Button>
          </div>

          <div className="rounded-xl border border-emerald-200/80 bg-emerald-50/40 p-4">
            <div className="flex items-start gap-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-emerald-200 bg-white text-emerald-700 shadow-sm">
                <ClipboardPaste className="h-4 w-4" />
              </span>
              <div>
                <h3 className="text-sm font-semibold">Colar roteiro pronto</h3>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  Use HOST para o participante A e GUEST para o participante B. Cada rótulo vira uma
                  fala separada na linha do tempo.
                </p>
              </div>
            </div>
            <div className="mt-3 rounded-lg border bg-background/80 px-3 py-2 font-mono text-[11px] leading-5 text-muted-foreground">
              HOST: Doutor, o que precisamos entender?
              <br />
              GUEST: Primeiro, vamos separar os fatos.
            </div>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="mt-3"
              onClick={() => {
                setImportError(null);
                setImportOpen(true);
              }}
            >
              <ClipboardPaste className="mr-1.5 h-4 w-4" /> Colar roteiro HOST/GUEST
            </Button>
          </div>
        </div>

        {conversationNotice ? (
          <div
            role="status"
            className="mt-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-status-info/30 bg-status-info/5 px-3 py-2 text-xs"
          >
            <span className="text-status-info">{conversationNotice}</span>
            {previousConversation ? (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-7 px-2 text-[11px]"
                onClick={undoConversationChange}
              >
                <RotateCcw className="mr-1 h-3.5 w-3.5" /> Desfazer substituição
              </Button>
            ) : null}
          </div>
        ) : null}
      </section>

      <section className="rounded-xl border bg-card p-4 shadow-sm sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-display text-sm font-semibold">Linha do tempo da conversa</h2>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              Uma ideia por fala. Prefira pergunta curta, resposta clara e uma conclusão prática.
            </p>
          </div>
          <Button type="button" size="sm" variant="secondary" onClick={() => addTurn()}>
            <Plus className="mr-1.5 h-4 w-4" /> Adicionar fala
          </Button>
        </div>

        <div className="mt-4 space-y-3">
          {draft.turns.map((turn, index) => {
            const participant = participantById.get(turn.speakerId);
            const style = SPEAKER_STYLES[turn.speakerId];
            return (
              <article key={turn.id} className={cn("rounded-xl border p-3", style.panel)}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="flex h-7 w-7 items-center justify-center rounded-full border bg-background text-xs font-semibold tabular-nums">
                      {index + 1}
                    </span>
                    <div
                      className="flex rounded-lg border bg-background p-1"
                      aria-label={`Quem fala no trecho ${index + 1}`}
                    >
                      {draft.participants.map((candidate) => (
                        <button
                          key={candidate.id}
                          type="button"
                          aria-pressed={turn.speakerId === candidate.id}
                          onClick={() => updateTurn(turn.id, { speakerId: candidate.id })}
                          className={cn(
                            "cursor-pointer rounded-md px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                            turn.speakerId === candidate.id
                              ? SPEAKER_STYLES[candidate.id].badge
                              : "text-muted-foreground hover:bg-muted",
                          )}
                        >
                          {candidate.name || `Participante ${candidate.id.toUpperCase()}`}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      aria-label={`Mover fala ${index + 1} para cima`}
                      disabled={index === 0}
                      onClick={() => moveTurn(index, -1)}
                    >
                      <ArrowUp className="h-4 w-4" />
                    </Button>
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      aria-label={`Mover fala ${index + 1} para baixo`}
                      disabled={index === draft.turns.length - 1}
                      onClick={() => moveTurn(index, 1)}
                    >
                      <ArrowDown className="h-4 w-4" />
                    </Button>
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      aria-label={`Excluir fala ${index + 1}`}
                      disabled={draft.turns.length <= 2}
                      className="text-muted-foreground hover:bg-status-danger/10 hover:text-status-danger"
                      onClick={() => removeTurn(turn.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
                <div className="mt-3">
                  <Label htmlFor={`podcast-turn-${turn.id}`} className="sr-only">
                    Fala {index + 1} de {participant?.name || `participante ${turn.speakerId}`}
                  </Label>
                  <Textarea
                    id={`podcast-turn-${turn.id}`}
                    value={turn.text}
                    maxLength={1200}
                    rows={3}
                    placeholder={
                      turn.speakerId === "a"
                        ? "Faça uma pergunta curta e fácil de entender."
                        : "Responda de forma educativa, direta e segura."
                    }
                    className="min-h-24 resize-y bg-background leading-6"
                    onChange={(event) => updateTurn(turn.id, { text: event.target.value })}
                  />
                  <div className="mt-1.5 flex items-center justify-between text-[11px] text-muted-foreground">
                    <span className="inline-flex items-center gap-1">
                      <Mic2 className="h-3.5 w-3.5" /> {participant?.name || "Participante"}
                    </span>
                    <span>{turn.text.length}/1200</span>
                  </div>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="mt-2 h-7 px-2 text-[11px]"
                  onClick={() => addTurn(index)}
                >
                  <Plus className="mr-1 h-3.5 w-3.5" /> Inserir fala depois
                </Button>
              </article>
            );
          })}
        </div>
      </section>

      <section className="rounded-xl border bg-card p-4 shadow-sm sm:p-5">
        <div className="grid gap-4 lg:grid-cols-[1fr_1fr_1fr]">
          <div className="space-y-1.5">
            <Label htmlFor="podcast-duration" className="text-xs">
              Duração de referência
            </Label>
            <Select
              value={String(durationSeconds)}
              onValueChange={(value) => onDurationChange(Number(value) as DurationPreset)}
            >
              <SelectTrigger id="podcast-duration">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DURATION_OPTIONS.map((duration) => (
                  <SelectItem key={duration} value={String(duration)}>
                    {duration} segundos
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="podcast-orientation" className="text-xs">
              Formato
            </Label>
            <Select
              value={draft.orientation}
              onValueChange={(orientation: "portrait" | "landscape") =>
                setDraft((current) => ({ ...current, orientation }))
              }
            >
              <SelectTrigger id="podcast-orientation">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="portrait">Vertical 9:16</SelectItem>
                <SelectItem value="landscape">Horizontal 16:9</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="podcast-music" className="text-xs">
              Trilha final
            </Label>
            <Select
              value={draft.musicTrackId || "none"}
              onValueChange={(value) =>
                setDraft((current) => ({
                  ...current,
                  musicTrackId: value === "none" ? null : value,
                }))
              }
            >
              <SelectTrigger id="podcast-music">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Sem trilha</SelectItem>
                {musicTracks.map((track) => (
                  <SelectItem key={track.id} value={track.id}>
                    {track.name} · {track.artist}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <button
            type="button"
            aria-pressed={draft.captions}
            onClick={() => setDraft((current) => ({ ...current, captions: !current.captions }))}
            className={cn(
              "flex cursor-pointer items-start gap-3 rounded-xl border p-3 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              draft.captions && "border-primary/40 bg-primary/5",
            )}
          >
            <Captions className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
            <span>
              <span className="block text-xs font-semibold">Legendas automáticas</span>
              <span className="mt-1 block text-[11px] leading-4 text-muted-foreground">
                Usa o texto de cada fala como fonte das legendas.
              </span>
            </span>
          </button>
          <div className="flex items-start gap-3 rounded-xl border bg-muted/20 p-3">
            <Film className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
            <div>
              <div className="text-xs font-semibold">Corte seco entre participantes</div>
              <p className="mt-1 text-[11px] leading-4 text-muted-foreground">
                Evita misturar vozes e mantém cada sincronização labial intacta.
              </p>
            </div>
          </div>
        </div>

        {problem ? (
          <div className="mt-4 rounded-lg border border-status-warning/30 bg-status-warning/5 px-3 py-2 text-xs text-status-warning">
            {problem}
          </div>
        ) : medicalBlocked ? (
          <div className="mt-4 rounded-lg border border-status-warning/30 bg-status-warning/5 px-3 py-2 text-xs text-status-warning">
            Salve o diálogo e conclua a revisão médica na aba Roteiro antes de gerar os clipes.
          </div>
        ) : (
          <div className="mt-4 flex items-center gap-2 rounded-lg border border-status-success/30 bg-status-success/5 px-3 py-2 text-xs text-status-success">
            <CheckCircle2 className="h-4 w-4 shrink-0" /> Estrutura pronta para salvar.
          </div>
        )}

        {generationPreview ? (
          <div className="mt-4 rounded-lg border border-status-info/30 bg-status-info/5 p-3">
            <div className="flex items-center gap-2 text-xs font-semibold">
              <Clock3 className="h-4 w-4 text-status-info" /> Produção enviada
            </div>
            <p className="mt-1 text-[11px] leading-4 text-muted-foreground">
              {generationPreview.turnCount} clipes serão gerados separadamente e reunidos na ordem
              acima quando estiverem prontos.
            </p>
          </div>
        ) : null}

        <div className="mt-4 flex flex-wrap justify-end gap-2 border-t pt-4">
          <Button
            type="button"
            variant="secondary"
            disabled={saving || submitting || generatingDialogue || Boolean(problem) || !dirty}
            onClick={() => void handleSave()}
          >
            {saving ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
            ) : (
              <Save className="mr-1.5 h-4 w-4" />
            )}
            {saving ? "Salvando..." : dirty ? "Salvar podcast" : "Podcast salvo"}
          </Button>
          <ConfirmAction
            title="Gerar uma fala por vez?"
            description={`${draft.turns.length} clipes serão enviados ao HeyGen, cada um com o avatar e a voz do participante correto. A montagem final será feita automaticamente em corte seco.`}
            confirmLabel={`Gerar ${draft.turns.length} clipes`}
            confirmDisabled={
              Boolean(problem) || medicalBlocked || saving || submitting || generatingDialogue
            }
            onConfirm={handleSubmit}
            trigger={
              <Button
                type="button"
                disabled={
                  Boolean(problem) || medicalBlocked || saving || submitting || generatingDialogue
                }
              >
                {submitting ? (
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                ) : (
                  <Film className="mr-1.5 h-4 w-4" />
                )}
                {submitting ? "Enviando..." : "Gerar podcast"}
              </Button>
            }
          />
        </div>
      </section>

      <Dialog
        open={importOpen}
        onOpenChange={(open) => {
          setImportOpen(open);
          if (!open) setImportError(null);
        }}
      >
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Colar conversa HOST/GUEST</DialogTitle>
            <DialogDescription>
              Cada bloco vira uma fala. HOST corresponde ao participante A e GUEST ao participante
              B. A importação substitui apenas o rascunho atual; nada será salvo automaticamente.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="podcast-pasted-script">Roteiro no formato HOST/GUEST</Label>
            <Textarea
              id="podcast-pasted-script"
              value={pastedScript}
              rows={14}
              className="min-h-72 resize-y font-mono text-sm leading-6"
              placeholder={
                "HOST: Doutor, essa medicação pode superar as opções atuais?\n\nGUEST: Ela é promissora, mas ainda está em estudo."
              }
              onChange={(event) => {
                setPastedScript(event.target.value);
                if (importError) setImportError(null);
              }}
            />
            <p className="text-xs leading-5 text-muted-foreground">
              Linhas quebradas sem um novo rótulo continuam na fala anterior. Também aceitamos
              APRESENTADOR, CONVIDADO e ESPECIALISTA.
            </p>
            {importError ? (
              <div
                role="alert"
                className="rounded-lg border border-status-danger/30 bg-status-danger/5 px-3 py-2 text-xs text-status-danger"
              >
                {importError}
              </div>
            ) : null}
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setImportOpen(false)}>
              Cancelar
            </Button>
            <Button type="button" disabled={!pastedScript.trim()} onClick={handleImportScript}>
              <ClipboardPaste className="mr-1.5 h-4 w-4" /> Importar e substituir rascunho
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
