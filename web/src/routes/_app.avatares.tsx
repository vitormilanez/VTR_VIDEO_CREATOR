import { createFileRoute } from "@tanstack/react-router";
import { useDeferredValue, useEffect, useMemo, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  AlertTriangle,
  Captions,
  CheckCircle2,
  Clapperboard,
  Clock3,
  ExternalLink,
  Film,
  Image as ImageIcon,
  Mic2,
  Plus,
  RefreshCw,
  Repeat2,
  ScanFace,
  Search,
  ShieldCheck,
  Sparkles,
  Star,
  Trash2,
  Upload,
  UserRound,
  UsersRound,
  Video,
  Volume2,
} from "lucide-react";
import { toast } from "sonner";
import { AppShell } from "@/components/app-shell";
import { ConfirmAction } from "@/components/confirm-action";
import { EmptyState } from "@/components/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  createHeyGenAvatar,
  fetchHeyGenAvatars,
  fetchHeyGenStyles,
  refreshHeyGenAvatar,
  saveSettings,
  type AvatarJob,
  type AvatarMediaPayload,
  type CreateAvatarPayload,
  type HeyGenAvatarGroup,
  type HeyGenAvatarLook,
  type HeyGenStyle,
} from "@/lib/api/local";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/avatares")({
  head: () => ({
    meta: [
      { title: "Avatares | AI Video Creator" },
      {
        name: "description",
        content: "Criação de avatares, clonagem de voz e configuração visual de vídeos.",
      },
    ],
  }),
  component: AvataresPage,
});

type CreationType = "photo" | "digital_twin" | "prompt";
type VoiceSource = "upload" | "video";
type StudioMode = "single" | "dialogue";
type Scene = { id: string; speaker: "a" | "b"; text: string };
const EMPTY_AVATAR_IDS: string[] = [];

const creationOptions: Array<{
  value: CreationType;
  label: string;
  description: string;
  icon: typeof ImageIcon;
}> = [
  {
    value: "photo",
    label: "Por foto",
    description: "Rápido e ideal para vídeos curtos.",
    icon: ImageIcon,
  },
  {
    value: "digital_twin",
    label: "Digital twin",
    description: "Mais natural, criado a partir de vídeo.",
    icon: Video,
  },
  {
    value: "prompt",
    label: "Apresentador IA",
    description: "Crie uma pessoa a partir de uma descrição.",
    icon: Sparkles,
  },
];

function AvataresPage() {
  const [activeTab, setActiveTab] = useState("library");
  const [avatars, setAvatars] = useState<HeyGenAvatarGroup[]>([]);
  const [looks, setLooks] = useState<HeyGenAvatarLook[]>([]);
  const [jobs, setJobs] = useState<AvatarJob[]>([]);
  const [styles, setStyles] = useState<HeyGenStyle[]>([]);
  const [loading, setLoading] = useState(true);
  const [avatarsFromCache, setAvatarsFromCache] = useState(false);

  async function loadData() {
    setLoading(true);
    const [avatarResult, styleResult] = await Promise.allSettled([
      fetchHeyGenAvatars(),
      fetchHeyGenStyles("cinematic"),
    ]);
    if (avatarResult.status === "fulfilled") {
      setAvatars(avatarResult.value.avatars);
      setLooks(avatarResult.value.looks);
      setJobs(avatarResult.value.jobs);
      setAvatarsFromCache(Boolean(avatarResult.value.fromCache));
    } else {
      toast.error(
        avatarResult.reason instanceof Error
          ? avatarResult.reason.message
          : "Não foi possível carregar os avatares.",
      );
    }
    if (styleResult.status === "fulfilled") {
      setStyles(styleResult.value.styles);
    }
    setLoading(false);
  }

  useEffect(() => {
    void loadData();
  }, []);

  return (
    <AppShell
      title="Avatares"
      actions={
        <Button variant="ghost" size="sm" onClick={() => void loadData()} disabled={loading}>
          <RefreshCw className={cn("mr-1 h-4 w-4", loading && "animate-spin")} />
          Atualizar
        </Button>
      }
    >
      {avatarsFromCache ? (
        <div className="mb-3 flex items-start gap-2 rounded-md border border-status-warn/40 bg-status-warn/10 p-3 text-xs">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-status-warn-foreground" />
          <div>
            A HeyGen não respondeu agora — esta lista é do último cache local e pode estar
            desatualizada (avatares removidos ou criados recentemente podem não aparecer
            corretamente). Clique em "Atualizar" para tentar de novo.
          </div>
        </div>
      ) : null}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList className="grid h-auto w-full grid-cols-3 md:w-auto">
          <TabsTrigger value="library">
            <ScanFace className="mr-1.5 h-4 w-4" />
            Meus avatares
          </TabsTrigger>
          <TabsTrigger value="create">
            <Plus className="mr-1.5 h-4 w-4" />
            Criar avatar
          </TabsTrigger>
          <TabsTrigger value="studio">
            <Clapperboard className="mr-1.5 h-4 w-4" />
            Estúdio
          </TabsTrigger>
        </TabsList>

        <TabsContent value="library">
          <AvatarLibrary
            avatars={avatars}
            looks={looks}
            jobs={jobs}
            loading={loading}
            onCreateClick={() => setActiveTab("create")}
            onJobUpdated={(updated) =>
              setJobs((current) => current.map((job) => (job.id === updated.id ? updated : job)))
            }
          />
        </TabsContent>

        <TabsContent value="create">
          <AvatarCreator
            onCreated={(job) => {
              setJobs((current) => [job, ...current]);
              toast.success("Avatar enviado. Complete o consentimento para liberar o uso.");
            }}
          />
        </TabsContent>

        <TabsContent value="studio">
          <AvatarStudio
            avatars={looks}
            styles={styles}
            onCreateClick={() => setActiveTab("create")}
          />
        </TabsContent>
      </Tabs>
    </AppShell>
  );
}

function AvatarLibrary({
  avatars,
  looks,
  jobs,
  loading,
  onCreateClick,
  onJobUpdated,
}: {
  avatars: HeyGenAvatarGroup[];
  looks: HeyGenAvatarLook[];
  jobs: AvatarJob[];
  loading: boolean;
  onCreateClick: () => void;
  onJobUpdated: (job: AvatarJob) => void;
}) {
  const [refreshingId, setRefreshingId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"all" | "favorites" | "portrait" | "landscape">("all");
  const [savingPreferenceId, setSavingPreferenceId] = useState<string | null>(null);
  const deferredSearch = useDeferredValue(search.trim().toLocaleLowerCase("pt-BR"));
  const settings = useStore((state) => state.settings);
  const setSettings = useStore((state) => state.setSettings);
  const defaultAvatarId = settings.heygen?.defaultAvatarId || null;
  const favoriteAvatarIds = settings.heygen?.favoriteAvatarIds || EMPTY_AVATAR_IDS;
  const favoriteSet = useMemo(() => new Set(favoriteAvatarIds), [favoriteAvatarIds]);

  const visibleLooks = useMemo(() => {
    const filtered = looks.filter((look) => {
      const matchesSearch = deferredSearch
        ? `${look.name} ${look.group_name}`.toLocaleLowerCase("pt-BR").includes(deferredSearch)
        : true;
      const matchesFilter =
        filter === "all" ||
        (filter === "favorites" && favoriteSet.has(look.id)) ||
        (filter === "portrait" && look.preferred_orientation !== "landscape") ||
        (filter === "landscape" && look.preferred_orientation === "landscape");
      return matchesSearch && matchesFilter;
    });
    return filtered.sort((left, right) => {
      if (left.id === defaultAvatarId) return -1;
      if (right.id === defaultAvatarId) return 1;
      const favoriteOrder = Number(favoriteSet.has(right.id)) - Number(favoriteSet.has(left.id));
      if (favoriteOrder) return favoriteOrder;
      return `${left.group_name} ${left.name}`.localeCompare(
        `${right.group_name} ${right.name}`,
        "pt-BR",
      );
    });
  }, [defaultAvatarId, deferredSearch, favoriteSet, filter, looks]);

  async function saveAvatarPreferences(
    next: { defaultAvatarId: string | null; favoriteAvatarIds: string[] },
    feedback: string,
    pendingId: string,
  ) {
    setSavingPreferenceId(pendingId);
    try {
      const saved = await saveSettings({ ...settings, heygen: next });
      setSettings(saved);
      toast.success(feedback);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Não foi possível salvar a preferência.",
      );
    } finally {
      setSavingPreferenceId(null);
    }
  }

  function toggleFavorite(look: HeyGenAvatarLook) {
    const isFavorite = favoriteSet.has(look.id);
    const nextFavorites = isFavorite
      ? favoriteAvatarIds.filter((id) => id !== look.id)
      : [...favoriteAvatarIds, look.id];
    void saveAvatarPreferences(
      { defaultAvatarId, favoriteAvatarIds: nextFavorites },
      isFavorite ? "Avatar removido dos favoritos." : "Avatar adicionado aos favoritos.",
      look.id,
    );
  }

  function makeDefault(look: HeyGenAvatarLook) {
    void saveAvatarPreferences(
      { defaultAvatarId: look.id, favoriteAvatarIds },
      `${look.name} definido como avatar padrão.`,
      look.id,
    );
  }

  async function refreshJob(job: AvatarJob) {
    setRefreshingId(job.id);
    try {
      onJobUpdated(await refreshHeyGenAvatar(job.id));
      toast.success("Status atualizado.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Não foi possível atualizar.");
    } finally {
      setRefreshingId(null);
    }
  }

  return (
    <div className="space-y-4">
      {jobs.length > 0 ? (
        <section className="rounded-md border bg-card">
          <div className="border-b px-4 py-3">
            <h2 className="text-sm font-semibold">Em preparação</h2>
          </div>
          <div className="divide-y">
            {jobs.map((job) => (
              <div
                key={job.id}
                className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center"
              >
                <StatusIcon status={job.status} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{job.name}</div>
                  <div className="text-xs text-muted-foreground">
                    {creationTypeLabel(job.creationType)} · {statusLabel(job.status)}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {job.consentUrl ? (
                    <Button variant="secondary" size="sm" asChild>
                      <a href={job.consentUrl} target="_blank" rel="noreferrer">
                        <ShieldCheck className="mr-1 h-4 w-4" />
                        Dar consentimento
                      </a>
                    </Button>
                  ) : null}
                  <Button
                    variant="ghost"
                    size="icon"
                    title="Atualizar status"
                    onClick={() => void refreshJob(job)}
                    disabled={refreshingId === job.id}
                  >
                    <RefreshCw
                      className={cn("h-4 w-4", refreshingId === job.id && "animate-spin")}
                    />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section>
        <div className="mb-3 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 className="text-sm font-semibold">Biblioteca</h2>
            <p className="text-xs text-muted-foreground">
              Organize identidades privadas e escolha o avatar usado automaticamente nos vídeos.
            </p>
          </div>
          <Badge variant="outline">
            {looks.length} {looks.length === 1 ? "avatar" : "avatares"} em {avatars.length}{" "}
            {avatars.length === 1 ? "identidade" : "identidades"}
          </Badge>
        </div>
        <div className="mb-4 grid gap-2 rounded-lg border bg-card p-3 md:grid-cols-[minmax(0,1fr)_220px]">
          <div className="relative">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Buscar por avatar ou identidade"
              aria-label="Buscar avatares"
              className="pl-9"
            />
          </div>
          <Select
            value={filter}
            onValueChange={(value) =>
              setFilter(value as "all" | "favorites" | "portrait" | "landscape")
            }
          >
            <SelectTrigger aria-label="Filtrar avatares">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos os avatares</SelectItem>
              <SelectItem value="favorites">Somente favoritos</SelectItem>
              <SelectItem value="portrait">Verticais</SelectItem>
              <SelectItem value="landscape">Horizontais</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {loading ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {[1, 2, 3].map((item) => (
              <div key={item} className="h-52 animate-pulse rounded-md border bg-muted" />
            ))}
          </div>
        ) : visibleLooks.length ? (
          <div className="space-y-6">
            {avatars.map((avatar) => {
              const avatarLooks = visibleLooks.filter((look) => look.group_id === avatar.id);
              if (!avatarLooks.length) return null;
              return (
                <section key={avatar.id}>
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <h3 className="text-sm font-semibold">{avatar.name}</h3>
                    <span className="text-xs text-muted-foreground">
                      {avatarLooks.length} {avatarLooks.length === 1 ? "visual" : "visuais"}
                    </span>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                    {avatarLooks.map((look) => (
                      <article
                        key={look.id}
                        className={cn(
                          "overflow-hidden rounded-md border bg-card transition-colors",
                          look.id === defaultAvatarId && "border-primary ring-1 ring-primary/30",
                        )}
                      >
                        <div className="relative aspect-[16/9] bg-muted">
                          {look.preview_image_url ? (
                            <img
                              src={look.preview_image_url}
                              alt={`Prévia do avatar ${look.name}`}
                              className="h-full w-full object-cover"
                            />
                          ) : (
                            <div className="flex h-full items-center justify-center text-muted-foreground">
                              <UserRound className="h-9 w-9" />
                            </div>
                          )}
                          <Button
                            type="button"
                            size="icon"
                            variant="secondary"
                            className="absolute right-2 top-2 h-9 w-9 cursor-pointer bg-background/90 shadow-sm backdrop-blur-sm"
                            onClick={() => toggleFavorite(look)}
                            disabled={savingPreferenceId === look.id}
                            aria-label={
                              favoriteSet.has(look.id)
                                ? `Remover ${look.name} dos favoritos`
                                : `Adicionar ${look.name} aos favoritos`
                            }
                            title={favoriteSet.has(look.id) ? "Remover dos favoritos" : "Favoritar"}
                          >
                            <Star
                              className={cn(
                                "h-4 w-4",
                                favoriteSet.has(look.id) &&
                                  "fill-status-warn text-status-warn-foreground",
                              )}
                            />
                          </Button>
                        </div>
                        <div className="space-y-3 p-3">
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <h4 className="truncate text-sm font-semibold">{look.name}</h4>
                              <p className="text-xs text-muted-foreground">
                                {look.preferred_orientation === "landscape"
                                  ? "Horizontal"
                                  : "Vertical"}
                              </p>
                            </div>
                            <StatusBadge status={look.status || "processing"} />
                          </div>
                          {look.id === defaultAvatarId ? (
                            <div className="flex min-h-9 items-center gap-2 rounded-md bg-status-success/10 px-3 text-xs font-semibold text-status-success-foreground">
                              <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                              Avatar padrão
                            </div>
                          ) : (
                            <Button
                              type="button"
                              size="sm"
                              variant="secondary"
                              className="w-full cursor-pointer"
                              onClick={() => makeDefault(look)}
                              disabled={
                                look.status !== "completed" || savingPreferenceId === look.id
                              }
                            >
                              <CheckCircle2 className="mr-1.5 h-4 w-4" />
                              Definir como padrão
                            </Button>
                          )}
                        </div>
                      </article>
                    ))}
                  </div>
                </section>
              );
            })}
          </div>
        ) : looks.length ? (
          <EmptyState
            icon={<Search className="h-5 w-5" />}
            title="Nenhum avatar encontrado"
            description="Ajuste a busca ou o filtro para ver outros avatares."
            action={
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  setSearch("");
                  setFilter("all");
                }}
              >
                Limpar filtros
              </Button>
            }
          />
        ) : (
          <EmptyState
            icon={<ScanFace className="h-5 w-5" />}
            title="Crie a primeira identidade"
            description="Para vídeos mais naturais, comece com um digital twin usando um vídeo curto, rosto visível e voz limpa. Depois ele aparece aqui para produção."
            action={
              <Button size="sm" onClick={onCreateClick}>
                <Plus className="mr-1.5 h-4 w-4" />
                Criar avatar
              </Button>
            }
          />
        )}
      </section>
    </div>
  );
}

function AvatarCreator({ onCreated }: { onCreated: (job: AvatarJob) => void }) {
  const [creationType, setCreationType] = useState<CreationType>("photo");
  const [name, setName] = useState("");
  const [appearancePrompt, setAppearancePrompt] = useState("");
  const [mediaFiles, setMediaFiles] = useState<File[]>([]);
  const [voiceFile, setVoiceFile] = useState<File | null>(null);
  const [cloneVoice, setCloneVoice] = useState(true);
  const [voiceSource, setVoiceSource] = useState<VoiceSource>("upload");
  const [consentAccepted, setConsentAccepted] = useState(false);
  const [creating, setCreating] = useState(false);

  const mediaAccept =
    creationType === "digital_twin" ? "video/mp4,video/webm" : "image/jpeg,image/png";
  const mediaHint =
    creationType === "digital_twin"
      ? "Vídeo MP4 ou WebM, com boa luz e áudio claro, até 30 MB."
      : creationType === "prompt"
        ? "Até 3 fotos de referência em JPG ou PNG, até 32 MB cada."
        : "Uma foto frontal em JPG ou PNG, com boa luz, até 32 MB.";

  function handleMediaSelection(files: FileList | null) {
    const selected = Array.from(files || []);
    setMediaFiles(creationType === "prompt" ? selected.slice(0, 3) : selected.slice(0, 1));
  }

  async function createAvatar() {
    setCreating(true);
    try {
      const payload: CreateAvatarPayload = {
        name,
        creationType,
        appearancePrompt,
        media: await Promise.all(mediaFiles.map(fileToMedia)),
        cloneVoice,
        voiceSource: cloneVoice ? voiceSource : undefined,
        voiceMedia:
          cloneVoice && voiceSource === "upload" && voiceFile
            ? await fileToMedia(voiceFile)
            : undefined,
        consentAccepted,
      };
      const job = await createHeyGenAvatar(payload);
      onCreated(job);
      setName("");
      setAppearancePrompt("");
      setMediaFiles([]);
      setVoiceFile(null);
      setConsentAccepted(false);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Não foi possível criar o avatar.");
    } finally {
      setCreating(false);
    }
  }

  const ready =
    name.trim().length >= 2 &&
    consentAccepted &&
    (creationType === "prompt" ? appearancePrompt.trim().length >= 12 : mediaFiles.length > 0) &&
    (!cloneVoice ||
      (voiceSource === "video" && creationType === "digital_twin") ||
      Boolean(voiceFile));

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
      <div className="space-y-4">
        <section className="rounded-md border bg-card p-4">
          <div className="mb-4">
            <h2 className="text-sm font-semibold">1. Como deseja criar?</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Escolha o nível de realismo adequado ao uso do cliente.
            </p>
          </div>
          <div className="grid gap-2 md:grid-cols-3">
            {creationOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => {
                  setCreationType(option.value);
                  setMediaFiles([]);
                  setVoiceSource(option.value === "digital_twin" ? "video" : "upload");
                }}
                className={cn(
                  "cursor-pointer rounded-md border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  creationType === option.value
                    ? "border-primary bg-primary/5"
                    : "hover:bg-muted/60",
                )}
              >
                <option.icon className="mb-3 h-5 w-5 text-primary" />
                <div className="text-sm font-semibold">{option.label}</div>
                <div className="mt-1 text-xs leading-4 text-muted-foreground">
                  {option.description}
                </div>
              </button>
            ))}
          </div>
        </section>

        <section className="rounded-md border bg-card p-4">
          <h2 className="mb-4 text-sm font-semibold">2. Identidade visual</h2>
          <div className="space-y-4">
            <div className="space-y-1">
              <Label htmlFor="avatar-name">Nome do avatar</Label>
              <Input
                id="avatar-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Ex.: Dra. Marina"
              />
            </div>

            {creationType === "prompt" ? (
              <div className="space-y-1">
                <Label htmlFor="appearance">Descrição da aparência</Label>
                <Textarea
                  id="appearance"
                  rows={4}
                  value={appearancePrompt}
                  onChange={(event) => setAppearancePrompt(event.target.value)}
                  placeholder="Ex.: médica brasileira, cerca de 40 anos, postura acolhedora, roupa clínica moderna, enquadramento de meio corpo..."
                />
              </div>
            ) : null}

            <FilePicker
              id="avatar-media"
              label={
                creationType === "digital_twin"
                  ? "Vídeo da pessoa"
                  : creationType === "prompt"
                    ? "Fotos de referência (opcional)"
                    : "Foto principal"
              }
              hint={mediaHint}
              accept={mediaAccept}
              multiple={creationType === "prompt"}
              files={mediaFiles}
              onChange={handleMediaSelection}
              onClear={() => setMediaFiles([])}
            />
          </div>
        </section>

        <section className="rounded-md border bg-card p-4">
          <div className="mb-4 flex items-center justify-between gap-4">
            <div>
              <h2 className="text-sm font-semibold">3. Voz</h2>
              <p className="mt-1 text-xs text-muted-foreground">
                Use a voz real ou mantenha uma voz pronta do HeyGen.
              </p>
            </div>
            <Switch checked={cloneVoice} onCheckedChange={setCloneVoice} aria-label="Clonar voz" />
          </div>
          {cloneVoice ? (
            <div className="space-y-3">
              {creationType === "digital_twin" ? (
                <div
                  className="grid grid-cols-2 gap-2"
                  role="radiogroup"
                  aria-label="Origem da voz"
                >
                  <button
                    type="button"
                    role="radio"
                    aria-checked={voiceSource === "video"}
                    onClick={() => setVoiceSource("video")}
                    className={cn(
                      "flex min-h-12 items-center gap-2 rounded-md border px-3 text-left text-sm transition-colors",
                      voiceSource === "video"
                        ? "border-primary bg-primary/5 text-foreground"
                        : "text-muted-foreground hover:bg-muted/60",
                    )}
                  >
                    <Volume2 className="h-4 w-4 shrink-0" />
                    <span>
                      <span className="block font-medium">Voz do vídeo</span>
                      <span className="block text-xs">Mais simples</span>
                    </span>
                  </button>
                  <button
                    type="button"
                    role="radio"
                    aria-checked={voiceSource === "upload"}
                    onClick={() => setVoiceSource("upload")}
                    className={cn(
                      "flex min-h-12 items-center gap-2 rounded-md border px-3 text-left text-sm transition-colors",
                      voiceSource === "upload"
                        ? "border-primary bg-primary/5 text-foreground"
                        : "text-muted-foreground hover:bg-muted/60",
                    )}
                  >
                    <Mic2 className="h-4 w-4 shrink-0" />
                    <span>
                      <span className="block font-medium">Outro áudio</span>
                      <span className="block text-xs">MP3 ou WAV</span>
                    </span>
                  </button>
                </div>
              ) : null}

              {voiceSource === "video" && creationType === "digital_twin" ? (
                <div className="flex items-start gap-3 rounded-md border border-dashed p-4">
                  <Video className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
                  <div>
                    <p className="text-sm font-medium">Usar o áudio do vídeo selecionado</p>
                    <p className="mt-1 text-xs leading-4 text-muted-foreground">
                      O HeyGen criará a voz junto com o Digital twin. Prefira um trecho sem música,
                      ruído ou outras pessoas falando.
                    </p>
                  </div>
                </div>
              ) : (
                <FilePicker
                  id="voice-media"
                  label="Amostra de voz"
                  hint="MP3 ou WAV, voz limpa e sem música, até 32 MB."
                  accept="audio/mpeg,audio/wav"
                  files={voiceFile ? [voiceFile] : []}
                  onChange={(files) => setVoiceFile(files?.[0] || null)}
                  onClear={() => setVoiceFile(null)}
                  icon={Mic2}
                />
              )}
            </div>
          ) : (
            <div className="rounded-md border border-dashed p-4 text-xs text-muted-foreground">
              A voz será escolhida na produção do vídeo.
            </div>
          )}
        </section>

        <section className="rounded-md border bg-card p-4">
          <h2 className="mb-3 text-sm font-semibold">4. Autorização</h2>
          <label className="flex cursor-pointer items-start gap-3 rounded-md border p-3">
            <Checkbox
              checked={consentAccepted}
              onCheckedChange={(value) => setConsentAccepted(value === true)}
              className="mt-0.5"
            />
            <span>
              <span className="block text-sm font-medium">
                Tenho autorização para usar esta imagem e esta voz
              </span>
              <span className="mt-1 block text-xs leading-4 text-muted-foreground">
                O titular deverá concluir também o consentimento oficial do HeyGen antes do avatar
                ser usado em vídeos.
              </span>
            </span>
          </label>
        </section>
      </div>

      <aside className="space-y-3">
        <section className="rounded-md border bg-card p-4">
          <h2 className="text-sm font-semibold">Resumo</h2>
          <div className="mt-4 space-y-3 text-xs">
            <SummaryRow label="Tipo" value={creationTypeLabel(creationType)} />
            <SummaryRow label="Identidade" value={name || "Não informada"} />
            <SummaryRow
              label="Imagem"
              value={
                mediaFiles.length
                  ? `${mediaFiles.length} ${mediaFiles.length === 1 ? "arquivo" : "arquivos"}`
                  : creationType === "prompt"
                    ? "Opcional"
                    : "Pendente"
              }
            />
            <SummaryRow
              label="Voz"
              value={
                !cloneVoice
                  ? "Escolher depois"
                  : voiceSource === "video" && creationType === "digital_twin"
                    ? "Áudio do vídeo"
                    : voiceFile?.name || "Pendente"
              }
            />
          </div>
          <ConfirmAction
            title="Criar avatar no HeyGen?"
            description="Os arquivos selecionados serão enviados ao HeyGen. A criação pode consumir créditos e ainda exigirá o consentimento do titular."
            confirmLabel="Criar avatar"
            onConfirm={() => void createAvatar()}
            trigger={
              <Button className="mt-4 w-full" disabled={!ready || creating}>
                <Sparkles className="mr-1.5 h-4 w-4" />
                {creating ? "Enviando..." : "Criar avatar"}
              </Button>
            }
          />
        </section>

        <section className="rounded-md border border-status-success/30 bg-status-success/5 p-4">
          <div className="flex gap-3">
            <ShieldCheck className="h-5 w-5 shrink-0 text-status-success" />
            <div>
              <h3 className="text-sm font-semibold">Privacidade</h3>
              <p className="mt-1 text-xs leading-4 text-muted-foreground">
                Fotos, vídeo e áudio não vão para o Sheets. O backend os envia diretamente para a
                criação e salva somente os identificadores e o status.
              </p>
            </div>
          </div>
        </section>

        <section className="rounded-md border bg-muted/25 p-4">
          <h3 className="text-sm font-semibold">Boas práticas</h3>
          <ul className="mt-2 space-y-2 text-xs text-muted-foreground">
            <li>Rosto visível, sem filtros ou óculos escuros.</li>
            <li>Ambiente silencioso para a clonagem de voz.</li>
            <li>Use o digital twin para movimentos mais naturais.</li>
          </ul>
        </section>
      </aside>
    </div>
  );
}

function AvatarStudio({
  avatars,
  styles,
  onCreateClick,
}: {
  avatars: HeyGenAvatarLook[];
  styles: HeyGenStyle[];
  onCreateClick: () => void;
}) {
  const configuredDefaultAvatarId = useStore(
    (state) => state.settings.heygen?.defaultAvatarId || null,
  );
  const [mode, setMode] = useState<StudioMode>("single");
  const [avatarA, setAvatarA] = useState("");
  const [avatarB, setAvatarB] = useState("");
  const [orientation, setOrientation] = useState<"portrait" | "landscape">("portrait");
  const [styleId, setStyleId] = useState("");
  const [singlePrompt, setSinglePrompt] = useState("");
  const [captions, setCaptions] = useState(true);
  const [broll, setBroll] = useState(true);
  const [transition, setTransition] = useState("clean-cut");
  const [scenes, setScenes] = useState<Scene[]>([
    { id: crypto.randomUUID(), speaker: "a", text: "" },
    { id: crypto.randomUUID(), speaker: "b", text: "" },
  ]);

  useEffect(() => {
    try {
      const saved = localStorage.getItem("ai-video-creator-studio-defaults");
      if (!saved) return;
      const defaults = JSON.parse(saved) as {
        mode?: StudioMode;
        avatarA?: string;
        avatarB?: string | null;
        orientation?: "portrait" | "landscape";
        styleId?: string | null;
        captions?: boolean;
        broll?: boolean;
        transition?: string;
        singlePrompt?: string;
        scenes?: Scene[];
      };
      if (defaults.mode) setMode(defaults.mode);
      if (defaults.avatarA) setAvatarA(defaults.avatarA);
      if (defaults.avatarB) setAvatarB(defaults.avatarB);
      if (defaults.orientation) setOrientation(defaults.orientation);
      if (defaults.styleId) setStyleId(defaults.styleId);
      if (typeof defaults.captions === "boolean") setCaptions(defaults.captions);
      if (typeof defaults.broll === "boolean") setBroll(defaults.broll);
      if (defaults.transition) setTransition(defaults.transition);
      if (defaults.singlePrompt) setSinglePrompt(defaults.singlePrompt);
      if (defaults.scenes?.length) setScenes(defaults.scenes);
    } catch {
      /* configuracao local antiga ou invalida */
    }
  }, []);

  const visibleStyles = useMemo(
    () =>
      styles.filter((style) =>
        orientation === "portrait" ? style.aspect_ratio === "9:16" : style.aspect_ratio === "16:9",
      ),
    [orientation, styles],
  );
  const selectedAvatarA = avatars.find((avatar) => avatar.id === avatarA);
  const selectedAvatarB = avatars.find((avatar) => avatar.id === avatarB);

  useEffect(() => {
    if (avatars.length && !avatars.some((avatar) => avatar.id === avatarA)) {
      setAvatarA(
        avatars.some((avatar) => avatar.id === configuredDefaultAvatarId)
          ? configuredDefaultAvatarId || avatars[0].id
          : avatars[0].id,
      );
    }
    if (
      avatars.length > 1 &&
      (avatarB === avatarA || !avatars.some((avatar) => avatar.id === avatarB))
    ) {
      setAvatarB(avatars.find((avatar) => avatar.id !== avatarA)?.id || "");
    }
  }, [avatars, avatarA, avatarB, configuredDefaultAvatarId]);

  useEffect(() => {
    if (styleId && !visibleStyles.some((style) => style.style_id === styleId)) {
      setStyleId("");
    }
  }, [orientation, styleId, visibleStyles]);

  function saveStudioDefaults() {
    const selectedStyle = styles.find((style) => style.style_id === styleId);
    const configuration = {
      mode,
      avatarA,
      avatarB: mode === "dialogue" ? avatarB : null,
      orientation,
      styleId: styleId || null,
      styleName: selectedStyle?.name || "Clean",
      captions,
      broll,
      transition,
      singlePrompt,
      scenes: mode === "dialogue" ? scenes : [],
      savedAt: new Date().toISOString(),
    };
    localStorage.setItem("ai-video-creator-studio-defaults", JSON.stringify(configuration));
    toast.success("Briefing salvo e preferências aplicadas aos próximos roteiros.");
  }

  function alternateSpeakers() {
    setScenes((current) =>
      current.map((scene, index) => ({ ...scene, speaker: index % 2 === 0 ? "a" : "b" })),
    );
  }

  function moveScene(index: number, direction: -1 | 1) {
    setScenes((current) => {
      const destination = index + direction;
      if (destination < 0 || destination >= current.length) return current;
      const reordered = [...current];
      [reordered[index], reordered[destination]] = [reordered[destination], reordered[index]];
      return reordered;
    });
  }

  if (avatars.length === 0) {
    return (
      <EmptyState
        icon={<Clapperboard className="h-5 w-5" />}
        title="Estúdio liberado depois do primeiro avatar"
        description="Crie ou sincronize um avatar para montar vídeos com um apresentador, dois participantes e estilos cinematic."
        action={
          <Button size="sm" onClick={onCreateClick}>
            <Plus className="mr-1.5 h-4 w-4" />
            Criar avatar
          </Button>
        }
      />
    );
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
      <div className="space-y-4">
        <section className="rounded-md border bg-card p-4">
          <h2 className="mb-3 text-sm font-semibold">Formato da apresentação</h2>
          <div className="grid gap-2 sm:grid-cols-2">
            <StudioModeButton
              active={mode === "single"}
              icon={UserRound}
              title="Um apresentador"
              description="Explicação direta com um avatar."
              onClick={() => setMode("single")}
            />
            <StudioModeButton
              active={mode === "dialogue"}
              icon={UsersRound}
              title="Diálogo com 2 avatares"
              description="Cenas alternadas, perguntas e respostas."
              onClick={() => setMode("dialogue")}
            />
          </div>
        </section>

        <section className="rounded-md border bg-card p-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-1">
              <Label>{mode === "dialogue" ? "Participante 1" : "Apresentador"}</Label>
              <AvatarSelect
                value={avatarA}
                onChange={setAvatarA}
                avatars={avatars}
                placeholder="Selecione o avatar"
              />
            </div>
            {mode === "dialogue" ? (
              <div className="space-y-1">
                <Label>Participante 2</Label>
                <AvatarSelect
                  value={avatarB}
                  onChange={setAvatarB}
                  avatars={avatars.filter((avatar) => avatar.id !== avatarA)}
                  placeholder="Selecione o segundo avatar"
                />
              </div>
            ) : (
              <div className="space-y-1">
                <Label>Formato</Label>
                <OrientationSelect value={orientation} onChange={setOrientation} />
              </div>
            )}
          </div>
          {mode === "dialogue" ? (
            <div className="mt-4 grid gap-4 border-t pt-4 md:grid-cols-2">
              <div className="space-y-1">
                <Label>Formato</Label>
                <OrientationSelect value={orientation} onChange={setOrientation} />
              </div>
              <div className="space-y-1">
                <Label>Transição entre falas</Label>
                <Select value={transition} onValueChange={setTransition}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="clean-cut">Corte limpo</SelectItem>
                    <SelectItem value="split-screen">Tela dividida na abertura</SelectItem>
                    <SelectItem value="question-card">Cartão com a pergunta</SelectItem>
                    <SelectItem value="reaction">Reação e resposta</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          ) : null}
        </section>

        <section className="rounded-md border bg-card p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold">Direção visual</h2>
              <p className="mt-1 text-xs text-muted-foreground">
                Estilos cinematic oficiais compatíveis com o formato escolhido.
              </p>
            </div>
            <Badge variant="outline">{visibleStyles.length} estilos</Badge>
          </div>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            <button
              type="button"
              onClick={() => setStyleId("")}
              className={cn(
                "flex aspect-video cursor-pointer flex-col items-center justify-center rounded-md border bg-muted/40 p-3 text-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                !styleId ? "border-primary ring-1 ring-primary" : "hover:bg-muted",
              )}
            >
              <Film className="mb-2 h-5 w-5 text-primary" />
              <span className="text-xs font-semibold">Clean</span>
              <span className="text-[11px] text-muted-foreground">Visual clínico atual</span>
            </button>
            {visibleStyles.map((style) => (
              <button
                key={style.style_id}
                type="button"
                onClick={() => setStyleId(style.style_id)}
                className={cn(
                  "group relative aspect-video cursor-pointer overflow-hidden rounded-md border bg-muted text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  styleId === style.style_id
                    ? "border-primary ring-1 ring-primary"
                    : "hover:border-muted-foreground/40",
                )}
              >
                {style.thumbnail_url ? (
                  <img
                    src={style.thumbnail_url}
                    alt={`Estilo ${style.name}`}
                    className="h-full w-full object-cover"
                  />
                ) : null}
                <span className="absolute inset-x-0 bottom-0 bg-black/75 px-2 py-1.5 text-xs font-medium text-white">
                  {style.name}
                </span>
              </button>
            ))}
          </div>
        </section>

        <section className="rounded-md border bg-card p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold">
                {mode === "dialogue" ? "Roteiro por cenas" : "Briefing do vídeo"}
              </h2>
              <p className="mt-1 text-xs text-muted-foreground">
                {mode === "dialogue"
                  ? "Cada fala vira uma cena e a montagem alterna os apresentadores."
                  : "Defina o assunto, a intenção e a mensagem principal."}
              </p>
            </div>
            {mode === "dialogue" ? (
              <div className="flex gap-2">
                <Button variant="ghost" size="sm" onClick={alternateSpeakers}>
                  <Repeat2 className="mr-1 h-4 w-4" />
                  Alternar falas
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() =>
                    setScenes((current) => [
                      ...current,
                      {
                        id: crypto.randomUUID(),
                        speaker: current.at(-1)?.speaker === "a" ? "b" : "a",
                        text: "",
                      },
                    ])
                  }
                >
                  <Plus className="mr-1 h-4 w-4" />
                  Fala
                </Button>
              </div>
            ) : null}
          </div>
          {mode === "dialogue" ? (
            <div className="space-y-2">
              {scenes.map((scene, index) => (
                <div
                  key={scene.id}
                  className={cn(
                    "rounded-md border p-3",
                    scene.speaker === "a"
                      ? "border-status-info/35 bg-status-info/5"
                      : "border-status-success/35 bg-status-success/5",
                  )}
                >
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      <span className="text-xs font-semibold">Fala {index + 1}</span>
                      <div className="flex rounded-md border bg-background p-0.5">
                        <SpeakerButton
                          active={scene.speaker === "a"}
                          avatar={selectedAvatarA}
                          fallback="Participante 1"
                          onClick={() =>
                            setScenes((current) =>
                              current.map((item) =>
                                item.id === scene.id ? { ...item, speaker: "a" } : item,
                              ),
                            )
                          }
                        />
                        <SpeakerButton
                          active={scene.speaker === "b"}
                          avatar={selectedAvatarB}
                          fallback="Participante 2"
                          onClick={() =>
                            setScenes((current) =>
                              current.map((item) =>
                                item.id === scene.id ? { ...item, speaker: "b" } : item,
                              ),
                            )
                          }
                        />
                      </div>
                    </div>
                    <div className="flex">
                      <Button
                        variant="ghost"
                        size="icon"
                        title="Mover fala para cima"
                        disabled={index === 0}
                        onClick={() => moveScene(index, -1)}
                      >
                        <ArrowUp className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        title="Mover fala para baixo"
                        disabled={index === scenes.length - 1}
                        onClick={() => moveScene(index, 1)}
                      >
                        <ArrowDown className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        title="Remover fala"
                        disabled={scenes.length <= 2}
                        onClick={() =>
                          setScenes((current) => current.filter((item) => item.id !== scene.id))
                        }
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                  <Textarea
                    id={`scene-${scene.id}`}
                    rows={2}
                    value={scene.text}
                    onChange={(event) =>
                      setScenes((current) =>
                        current.map((item) =>
                          item.id === scene.id ? { ...item, text: event.target.value } : item,
                        ),
                      )
                    }
                    placeholder={
                      scene.speaker === "a"
                        ? "Por que a fome aumenta à noite?"
                        : "Nem sempre é falta de controle. Vamos entender..."
                    }
                  />
                </div>
              ))}
            </div>
          ) : (
            <Textarea
              rows={5}
              value={singlePrompt}
              onChange={(event) => setSinglePrompt(event.target.value)}
              placeholder="Ex.: vídeo educativo sobre fome noturna, tom acolhedor, sem prescrever tratamentos, com exemplos do cotidiano..."
            />
          )}
        </section>
      </div>

      <aside className="space-y-3">
        <section className="rounded-md border bg-card p-4">
          <h2 className="text-sm font-semibold">Acabamento</h2>
          <div className="mt-4 space-y-3">
            <SettingSwitch
              icon={Captions}
              label="Legendas"
              description="Sincronizadas com cada fala"
              checked={captions}
              onChange={setCaptions}
            />
            <SettingSwitch
              icon={Clapperboard}
              label="B-roll inteligente"
              description="Imagens de apoio e motion graphics"
              checked={broll}
              onChange={setBroll}
            />
          </div>
        </section>

        <section className="rounded-md border bg-card p-4">
          <h2 className="text-sm font-semibold">Como será produzido</h2>
          <div className="mt-4 space-y-3">
            <ProcessStep
              number="1"
              title={mode === "dialogue" ? "Gerar cada participante" : "Gerar apresentador"}
              description={
                mode === "dialogue"
                  ? "Cada avatar recebe somente as próprias falas."
                  : "O avatar segue o briefing e o estilo selecionado."
              }
            />
            <ProcessStep
              number="2"
              title={mode === "dialogue" ? "Montar as cenas" : "Aplicar acabamento"}
              description={
                mode === "dialogue"
                  ? "As cenas são alternadas na ordem do roteiro."
                  : "Entram legendas, B-roll e identidade visual."
              }
            />
            <ProcessStep
              number="3"
              title="Revisar antes de publicar"
              description="O vídeo permanece na fila de produção para aprovação."
            />
          </div>
          <Button className="mt-4 w-full" onClick={saveStudioDefaults}>
            <CheckCircle2 className="mr-1.5 h-4 w-4" />
            Salvar briefing
          </Button>
        </section>

        <section className="rounded-md border border-status-info/30 bg-status-info/5 p-4">
          <div className="flex gap-3">
            <UsersRound className="h-5 w-5 shrink-0 text-status-info" />
            <div>
              <h3 className="text-sm font-semibold">Diálogo realista</h3>
              <p className="mt-1 text-xs leading-4 text-muted-foreground">
                A alternância de cenas é mais previsível que tentar colocar dois avatares no mesmo
                enquadramento. Tela dividida pode aparecer na abertura e no encerramento.
              </p>
            </div>
          </div>
        </section>
      </aside>
    </div>
  );
}

function FilePicker({
  id,
  label,
  hint,
  accept,
  multiple,
  files,
  onChange,
  onClear,
  icon: Icon = Upload,
}: {
  id: string;
  label: string;
  hint: string;
  accept: string;
  multiple?: boolean;
  files: File[];
  onChange: (files: FileList | null) => void;
  onClear: () => void;
  icon?: typeof Upload;
}) {
  return (
    <div className="space-y-1">
      <Label>{label}</Label>
      <div className="flex min-h-24 items-center gap-3 rounded-md border border-dashed p-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
          <Icon className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          {files.length ? (
            <>
              <div className="truncate text-sm font-medium">
                {files.map((file) => file.name).join(", ")}
              </div>
              <div className="text-xs text-muted-foreground">
                {formatBytes(files.reduce((total, file) => total + file.size, 0))}
              </div>
            </>
          ) : (
            <>
              <div className="text-sm font-medium">Selecione o arquivo</div>
              <div className="text-xs leading-4 text-muted-foreground">{hint}</div>
            </>
          )}
        </div>
        {files.length ? (
          <Button variant="ghost" size="icon" title="Remover arquivo" onClick={onClear}>
            <Trash2 className="h-4 w-4" />
          </Button>
        ) : (
          <Button variant="secondary" size="sm" asChild>
            <label htmlFor={id} className="cursor-pointer">
              Escolher
            </label>
          </Button>
        )}
        <input
          id={id}
          type="file"
          accept={accept}
          multiple={multiple}
          className="sr-only"
          onChange={(event) => onChange(event.target.files)}
        />
      </div>
    </div>
  );
}

function AvatarSelect({
  value,
  onChange,
  avatars,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  avatars: HeyGenAvatarLook[];
  placeholder: string;
}) {
  const selected = avatars.find((avatar) => avatar.id === value);
  return (
    <div className="grid grid-cols-[48px_1fr] items-center gap-2">
      <div className="h-12 w-12 overflow-hidden rounded-md border bg-muted">
        {selected?.preview_image_url ? (
          <img src={selected.preview_image_url} alt="" className="h-full w-full object-cover" />
        ) : (
          <UserRound className="m-3 h-6 w-6 text-muted-foreground" />
        )}
      </div>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="min-w-0">
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent>
          {avatars.map((avatar) => (
            <SelectItem key={avatar.id} value={avatar.id}>
              {avatar.name} · {avatar.group_name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

function SpeakerButton({
  active,
  avatar,
  fallback,
  onClick,
}: {
  active: boolean;
  avatar?: HeyGenAvatarLook;
  fallback: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      title={avatar?.name || fallback}
      onClick={onClick}
      className={cn(
        "flex h-7 max-w-40 items-center gap-1.5 rounded px-2 text-xs transition-colors",
        active ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted",
      )}
    >
      {avatar?.preview_image_url ? (
        <img src={avatar.preview_image_url} alt="" className="h-5 w-5 rounded object-cover" />
      ) : (
        <UserRound className="h-4 w-4" />
      )}
      <span className="truncate">{avatar?.name || fallback}</span>
    </button>
  );
}

function OrientationSelect({
  value,
  onChange,
}: {
  value: "portrait" | "landscape";
  onChange: (value: "portrait" | "landscape") => void;
}) {
  return (
    <Select value={value} onValueChange={(next) => onChange(next as "portrait" | "landscape")}>
      <SelectTrigger>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="portrait">Vertical · Reels e TikTok</SelectItem>
        <SelectItem value="landscape">Horizontal · YouTube</SelectItem>
      </SelectContent>
    </Select>
  );
}

function StudioModeButton({
  active,
  icon: Icon,
  title,
  description,
  onClick,
}: {
  active: boolean;
  icon: typeof UserRound;
  title: string;
  description: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex cursor-pointer items-center gap-3 rounded-md border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        active ? "border-primary bg-primary/5" : "hover:bg-muted/60",
      )}
    >
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-muted">
        <Icon className="h-5 w-5 text-primary" />
      </div>
      <span>
        <span className="block text-sm font-semibold">{title}</span>
        <span className="block text-xs text-muted-foreground">{description}</span>
      </span>
    </button>
  );
}

function SettingSwitch({
  icon: Icon,
  label,
  description,
  checked,
  onChange,
}: {
  icon: typeof Captions;
  label: string;
  description: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <Icon className="h-4 w-4 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <div className="text-xs font-medium">{label}</div>
        <div className="text-[11px] text-muted-foreground">{description}</div>
      </div>
      <Switch checked={checked} onCheckedChange={onChange} aria-label={label} />
    </div>
  );
}

function ProcessStep({
  number,
  title,
  description,
}: {
  number: string;
  title: string;
  description: string;
}) {
  return (
    <div className="flex gap-3">
      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border bg-background text-[11px] font-semibold">
        {number}
      </div>
      <div>
        <div className="text-xs font-medium">{title}</div>
        <div className="mt-0.5 text-[11px] leading-4 text-muted-foreground">{description}</div>
      </div>
    </div>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b pb-2 last:border-0 last:pb-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="max-w-[180px] truncate text-right font-medium">{value}</span>
    </div>
  );
}

function StatusIcon({ status }: { status: string }) {
  if (status === "completed") {
    return <CheckCircle2 className="h-5 w-5 shrink-0 text-status-success" />;
  }
  return <Clock3 className="h-5 w-5 shrink-0 text-status-warn" />;
}

function StatusBadge({ status }: { status: string }) {
  const completed = status === "completed";
  const failed = status === "failed";
  return (
    <Badge
      variant="outline"
      className={cn(
        completed && "border-status-success/40 text-status-success",
        failed && "border-status-danger/40 text-status-danger",
      )}
    >
      {statusLabel(status)}
    </Badge>
  );
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    completed: "Pronto",
    processing: "Processando",
    pending_consent: "Aguardando consentimento",
    failed: "Falhou",
  };
  return labels[status] || "Em preparação";
}

function creationTypeLabel(type: CreationType) {
  return {
    photo: "Avatar por foto",
    digital_twin: "Digital twin",
    prompt: "Apresentador IA",
  }[type];
}

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

async function fileToMedia(file: File): Promise<AvatarMediaPayload> {
  const dataUrl = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error(`Não foi possível ler ${file.name}.`));
    reader.readAsDataURL(file);
  });
  return {
    name: file.name,
    mimeType: file.type,
    data: dataUrl.slice(dataUrl.indexOf(",") + 1),
  };
}
