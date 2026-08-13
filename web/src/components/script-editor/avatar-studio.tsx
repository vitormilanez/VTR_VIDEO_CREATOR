import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Pencil, Plus, Trash2, UserRound } from "lucide-react";

import { ConfirmAction } from "@/components/confirm-action";
import {
  AVATAR_SET_ROLE_OPTIONS,
  avatarSetRoleLabel,
} from "@/components/script-editor/editor-options";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
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
import {
  saveAvatarSet,
  type AvatarSet,
  type AvatarSetLook,
  type AvatarSetRole,
  type HeyGenCatalog,
} from "@/lib/api/local";
import { cn } from "@/lib/utils";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      {children}
    </div>
  );
}

function sharedAvatarGroupId(
  looks: AvatarSetLook[],
  avatars: HeyGenCatalog["avatars"],
): string | null {
  const groupIds = looks.map(
    (look) => avatars.find((avatar) => avatar.id === look.avatarId)?.groupId || "",
  );
  if (groupIds.some((groupId) => !groupId) || new Set(groupIds).size !== 1) return null;
  return groupIds[0] || null;
}

export function AvatarPicker({
  value,
  avatars,
  loading,
  error,
  onChange,
}: {
  value: string;
  avatars: HeyGenCatalog["avatars"];
  loading: boolean;
  error: string | null;
  onChange: (value: string) => void;
}) {
  const selected = avatars.find((avatar) => avatar.id === value);
  const placeholder = loading
    ? "Carregando avatares..."
    : error
      ? "Nao foi possivel carregar avatares"
      : "Nenhum avatar pronto encontrado";

  if (!selected) {
    return (
      <div className="flex min-h-16 items-center gap-3 rounded-md border bg-muted/30 px-3 text-sm text-muted-foreground">
        <UserRound className="h-7 w-7 shrink-0" />
        <span>{placeholder}</span>
      </div>
    );
  }

  return (
    <Dialog>
      <DialogTrigger asChild>
        <button
          type="button"
          data-avatar-id={selected.id}
          className="flex min-h-16 w-full items-center gap-3 rounded-md border bg-background p-2 text-left shadow-sm transition-colors hover:border-primary/40 hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <AvatarThumbnail avatar={selected} className="h-14 w-14" />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-semibold">{selected.name}</span>
            <span className="block truncate text-xs text-muted-foreground">
              {selected.groupName || "Identidade HeyGen"} · {orientationLabel(selected.orientation)}
              {selected.defaultVoiceId ? " · voz padrão" : ""}
            </span>
          </span>
          <span className="shrink-0 px-1 text-xs font-medium text-primary">Trocar avatar</span>
        </button>
      </DialogTrigger>
      <DialogContent className="max-h-[86vh] max-w-4xl overflow-hidden p-0">
        <DialogHeader className="border-b px-5 py-4 pr-12">
          <DialogTitle>Escolha o avatar do vídeo</DialogTitle>
          <DialogDescription>
            A miniatura escolhida corresponde ao avatar enviado para o HeyGen.
          </DialogDescription>
        </DialogHeader>
        <div className="grid max-h-[68vh] auto-rows-max content-start grid-cols-2 gap-3 overflow-y-auto p-4 sm:grid-cols-3 md:grid-cols-4">
          {avatars.map((avatar) => {
            const active = avatar.id === value;
            return (
              <DialogClose asChild key={avatar.id}>
                <button
                  type="button"
                  data-avatar-id={avatar.id}
                  onClick={() => onChange(avatar.id)}
                  aria-pressed={active}
                  className={cn(
                    "overflow-hidden rounded-md border bg-background text-left transition-all hover:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    active && "border-primary ring-2 ring-primary/20",
                  )}
                >
                  <div className="relative h-28 bg-muted">
                    <AvatarThumbnail
                      avatar={avatar}
                      className="h-full w-full rounded-none border-0"
                      fit="contain"
                    />
                    {active ? (
                      <span className="absolute right-2 top-2 rounded bg-primary px-2 py-1 text-[10px] font-semibold text-primary-foreground">
                        Selecionado
                      </span>
                    ) : null}
                  </div>
                  <span className="block p-2.5">
                    <span className="block truncate text-xs font-semibold">{avatar.name}</span>
                    <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
                      {avatar.groupName || "Identidade HeyGen"}
                    </span>
                    <span className="mt-1 block text-[10px] uppercase text-muted-foreground">
                      {[
                        avatar.type || "avatar",
                        orientationLabel(avatar.orientation),
                        avatar.status || "status indefinido",
                        avatar.defaultVoiceId ? "voz padrão" : "",
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  </span>
                </button>
              </DialogClose>
            );
          })}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function AvatarSetSelector({
  sets,
  selectedId,
  selected,
  avatars,
  selectedLooks,
  primaryAvatarId,
  loading,
  onSelect,
  onSaved,
  onCreate,
  onEdit,
  onDelete,
  onPrimaryChange,
}: {
  sets: AvatarSet[];
  selectedId: string | null;
  selected: AvatarSet | null;
  avatars: HeyGenCatalog["avatars"];
  selectedLooks: Array<{ look: AvatarSetLook; avatar: HeyGenCatalog["avatars"][number] }>;
  primaryAvatarId: string;
  loading: boolean;
  onSelect: (avatarSet: AvatarSet) => void;
  onSaved: (avatarSet: AvatarSet) => void | Promise<void>;
  onCreate: () => void;
  onEdit: (avatarSet: AvatarSet) => void;
  onDelete: (avatarSet: AvatarSet) => void;
  onPrimaryChange: (avatarId: string) => void;
}) {
  const [draftLooks, setDraftLooks] = useState<AvatarSetLook[]>([]);
  const [choosingRole, setChoosingRole] = useState<AvatarSetRole | null>(null);
  const [savingPack, setSavingPack] = useState(false);
  const [packError, setPackError] = useState<string | null>(null);

  useEffect(() => {
    setDraftLooks(selected?.looks || []);
    setChoosingRole(null);
    setPackError(null);
  }, [selected?.id, selected?.looks, selected?.updatedAt]);

  const packDirty = Boolean(
    selected && JSON.stringify(draftLooks) !== JSON.stringify(selected.looks),
  );

  function updateDraftAvatar(role: AvatarSetRole, avatarId: string) {
    setDraftLooks((current) =>
      current.map((look) => (look.role === role ? { ...look, avatarId } : look)),
    );
    setChoosingRole(null);
    setPackError(null);
  }

  function resetDraftPack() {
    setDraftLooks(selected?.looks || []);
    setChoosingRole(null);
    setPackError(null);
  }

  async function saveDraftPack() {
    if (!selected) return;
    if (draftLooks.length < 2 || new Set(draftLooks.map((look) => look.avatarId)).size < 2) {
      setPackError("Escolha pelo menos dois looks diferentes antes de salvar o pack.");
      return;
    }
    if (new Set(draftLooks.map((look) => look.role)).size !== draftLooks.length) {
      setPackError("Cada posição precisa ter um papel diferente.");
      return;
    }
    if (!sharedAvatarGroupId(draftLooks, avatars)) {
      setPackError(
        "As posições precisam pertencer à mesma identidade HeyGen. Escolha os looks em pé/sentado do mesmo grupo.",
      );
      return;
    }
    setSavingPack(true);
    setPackError(null);
    try {
      const saved = await saveAvatarSet(
        { name: selected.name, voiceId: selected.voiceId, looks: draftLooks },
        selected.id,
      );
      await onSaved(saved);
      setDraftLooks(saved.looks);
      setChoosingRole(null);
    } catch (error) {
      setPackError(error instanceof Error ? error.message : "Nao foi possivel salvar o pack.");
    } finally {
      setSavingPack(false);
    }
  }

  if (loading) {
    return (
      <div className="rounded-lg border bg-muted/25 p-3 text-xs text-muted-foreground">
        Carregando Avatar Sets...
      </div>
    );
  }

  return (
    <div className="space-y-3 rounded-lg border bg-muted/20 p-3">
      <div className="flex flex-wrap items-center gap-2">
        {sets.length ? (
          <Select
            value={selectedId || undefined}
            onValueChange={(value) => {
              const next = sets.find((avatarSet) => avatarSet.id === value);
              if (next) onSelect(next);
            }}
          >
            <SelectTrigger className="min-w-56 flex-1 bg-background">
              <SelectValue placeholder="Selecione um Avatar Set" />
            </SelectTrigger>
            <SelectContent>
              {sets.map((avatarSet) => (
                <SelectItem key={avatarSet.id} value={avatarSet.id}>
                  {avatarSet.name} · {avatarSet.looks.length} looks
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <p className="flex-1 text-xs text-muted-foreground">Nenhum Avatar Set criado ainda.</p>
        )}
        <Button type="button" size="sm" variant="outline" onClick={onCreate}>
          <Plus className="h-3.5 w-3.5" /> Criar conjunto
        </Button>
      </div>

      {selected ? (
        <>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {draftLooks.map((look) => {
              const item =
                avatars.find((avatar) => avatar.id === look.avatarId) ||
                selectedLooks.find((candidate) => candidate.look.avatarId === look.avatarId)
                  ?.avatar;
              const primary = look.avatarId === primaryAvatarId;
              return (
                <div
                  key={`${look.role}-${look.avatarId}`}
                  className={cn(
                    "rounded-md border bg-background p-2 transition-colors",
                    primary && "border-primary ring-1 ring-primary/30",
                    choosingRole === look.role && "border-status-info bg-status-info/5",
                  )}
                >
                  <button
                    type="button"
                    onClick={() =>
                      setChoosingRole((current) => (current === look.role ? null : look.role))
                    }
                    className="flex w-full items-center gap-2 rounded-md text-left transition-colors hover:bg-muted/40"
                  >
                    {item ? (
                      <AvatarThumbnail avatar={item} className="h-14 w-14" fit="contain" />
                    ) : (
                      <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-md border bg-muted">
                        <UserRound className="h-7 w-7 text-muted-foreground" />
                      </div>
                    )}
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-xs font-semibold">{look.label}</span>
                      <span className="block truncate text-[11px] text-muted-foreground">
                        {avatarSetRoleLabel(look.role)} · {item?.name || "Look não carregado"}
                      </span>
                      <span className="mt-0.5 block text-[10px] font-medium text-status-info">
                        Clique para trocar
                      </span>
                    </span>
                  </button>
                  <div className="mt-2 flex items-center justify-between gap-2">
                    {primary ? (
                      <span className="text-[10px] font-medium text-primary">
                        Posição principal
                      </span>
                    ) : (
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="h-7 px-2 text-[11px]"
                        onClick={() => onPrimaryChange(look.avatarId)}
                      >
                        Usar como principal
                      </Button>
                    )}
                    {packDirty ? (
                      <span className="rounded-full bg-status-warning/10 px-2 py-0.5 text-[10px] text-status-warning">
                        Não salvo
                      </span>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
          {choosingRole ? (
            <div className="rounded-lg border border-status-info/30 bg-background p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div>
                  <div className="text-xs font-semibold">
                    Escolha o avatar para {avatarSetRoleLabel(choosingRole)}
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    Veja as miniaturas e clique no look que quer usar nesta posição.
                  </p>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => setChoosingRole(null)}
                >
                  Fechar
                </Button>
              </div>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {avatars.map((avatar) => {
                  const active = draftLooks.some(
                    (look) => look.role === choosingRole && look.avatarId === avatar.id,
                  );
                  const alreadyUsed = draftLooks.some(
                    (look) => look.role !== choosingRole && look.avatarId === avatar.id,
                  );
                  return (
                    <button
                      key={avatar.id}
                      type="button"
                      onClick={() => updateDraftAvatar(choosingRole, avatar.id)}
                      className={cn(
                        "flex min-w-0 items-center gap-2 rounded-md border bg-muted/20 p-2 text-left transition-colors hover:border-primary/50 hover:bg-muted/40",
                        active && "border-primary bg-primary/5 ring-1 ring-primary/30",
                        alreadyUsed && !active && "opacity-70",
                      )}
                    >
                      <AvatarThumbnail avatar={avatar} className="h-14 w-14" fit="contain" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-xs font-semibold">{avatar.name}</span>
                        <span className="block truncate text-[10px] text-muted-foreground">
                          {avatar.groupName || "Identidade HeyGen"}
                        </span>
                        {alreadyUsed && !active ? (
                          <span className="mt-0.5 block text-[10px] text-status-warning">
                            Já usado neste pack
                          </span>
                        ) : null}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : null}
          {packError ? (
            <p className="rounded-md border border-status-danger/30 bg-status-danger/5 px-3 py-2 text-xs text-status-danger">
              {packError}
            </p>
          ) : null}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-[11px] leading-4 text-muted-foreground">
              Clique em um look para trocar por miniatura. Salve o pack para usar as mudanças na
              produção.
            </p>
            <div className="flex gap-1">
              {packDirty ? (
                <>
                  <Button type="button" size="sm" variant="ghost" onClick={resetDraftPack}>
                    Descartar
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => void saveDraftPack()}
                    disabled={savingPack}
                  >
                    {savingPack ? "Salvando..." : "Salvar pack"}
                  </Button>
                </>
              ) : null}
              <Button type="button" size="sm" variant="ghost" onClick={() => onEdit(selected)}>
                <Pencil className="h-3.5 w-3.5" /> Editar
              </Button>
              <ConfirmAction
                title="Excluir este Avatar Set?"
                description="O conjunto será removido apenas da configuração local. Os looks da HeyGen não serão apagados."
                confirmLabel="Excluir conjunto"
                destructive
                onConfirm={() => onDelete(selected)}
                trigger={
                  <Button type="button" size="sm" variant="ghost" className="text-status-danger">
                    <Trash2 className="h-3.5 w-3.5" /> Excluir
                  </Button>
                }
              />
            </div>
          </div>
        </>
      ) : (
        <p className="text-xs text-muted-foreground">
          Crie um conjunto com pelo menos duas posições reais para habilitar a direção multicâmera.
        </p>
      )}
    </div>
  );
}

export function AvatarSetEditorDialog({
  open,
  initial,
  avatars,
  voices,
  onOpenChange,
  onSaved,
}: {
  open: boolean;
  initial: AvatarSet | null;
  avatars: HeyGenCatalog["avatars"];
  voices: HeyGenCatalog["voices"];
  onOpenChange: (open: boolean) => void;
  onSaved: (avatarSet: AvatarSet) => void | Promise<void>;
}) {
  const [name, setName] = useState("");
  const [voiceId, setVoiceId] = useState("");
  const [looks, setLooks] = useState<AvatarSetLook[]>([]);
  const [choosingLookIndex, setChoosingLookIndex] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    const fallbackLooks: AvatarSetLook[] = avatars.slice(0, 2).map((avatar, index) => ({
      avatarId: avatar.id,
      role: index === 0 ? "close" : "front",
      label: index === 0 ? "Close" : "Frontal",
    }));
    setName(initial?.name || "");
    setVoiceId(initial?.voiceId || avatars[0]?.defaultVoiceId || voices[0]?.id || "");
    setLooks(initial?.looks?.length ? initial.looks : fallbackLooks);
    setChoosingLookIndex(null);
    setError(null);
  }, [avatars, initial, open, voices]);

  function updateLook(index: number, patch: Partial<AvatarSetLook>) {
    setLooks((current) =>
      current.map((look, lookIndex) => (lookIndex === index ? { ...look, ...patch } : look)),
    );
  }

  function addLook() {
    const nextAvatar = avatars.find((avatar) => !looks.some((look) => look.avatarId === avatar.id));
    const nextRole = AVATAR_SET_ROLE_OPTIONS.find(
      (option) => !looks.some((look) => look.role === option.value),
    );
    if (!nextAvatar || !nextRole) {
      setError("Não há outro look ou role disponível no catálogo atual.");
      return;
    }
    setLooks((current) => [
      ...current,
      { avatarId: nextAvatar.id, role: nextRole.value, label: nextRole.label },
    ]);
    setError(null);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (looks.length < 2 || new Set(looks.map((look) => look.avatarId)).size < 2) {
      setError("Escolha pelo menos dois looks diferentes para criar duas posições.");
      return;
    }
    if (new Set(looks.map((look) => look.role)).size !== looks.length) {
      setError("Cada posição precisa ter um role diferente.");
      return;
    }
    if (!sharedAvatarGroupId(looks, avatars)) {
      setError(
        "As posições precisam pertencer à mesma identidade HeyGen. Escolha os looks em pé/sentado do mesmo grupo.",
      );
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const saved = await saveAvatarSet({ name: name.trim(), voiceId, looks }, initial?.id);
      await onSaved(saved);
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : "Nao foi possivel salvar o Avatar Set.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[88vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{initial ? "Editar Avatar Set" : "Criar Avatar Set"}</DialogTitle>
          <DialogDescription>
            Cadastre looks reais da mesma identidade HeyGen — por exemplo, em pé e sentado na mesa —
            para alternar somente entre duas posições com cortes entre cenas.
          </DialogDescription>
        </DialogHeader>
        <form className="space-y-4" onSubmit={submit}>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Nome do conjunto">
              <Input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Guilherme — Casual Azul"
                required
              />
            </Field>
            <Field label="Voz">
              <Select value={voiceId} onValueChange={setVoiceId}>
                <SelectTrigger>
                  <SelectValue placeholder="Selecione uma voz" />
                </SelectTrigger>
                <SelectContent>
                  {voices.map((voice) => (
                    <SelectItem key={voice.id} value={voice.id}>
                      {voice.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <div>
                <Label className="text-xs">Looks e posições</Label>
                <p className="text-[11px] text-muted-foreground">
                  Use dois looks diferentes da mesma identidade HeyGen. Roupa, cenário e voz devem
                  permanecer consistentes.
                </p>
              </div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={addLook}
                disabled={looks.length >= 6}
              >
                <Plus className="h-3.5 w-3.5" /> Adicionar look
              </Button>
            </div>
            <div className="space-y-2">
              {looks.map((look, index) => {
                const selectedAvatar = avatars.find((avatar) => avatar.id === look.avatarId);
                return (
                  <div
                    key={`${index}-${look.avatarId}`}
                    className="grid gap-2 rounded-lg border bg-muted/20 p-2 sm:grid-cols-[minmax(0,1.45fr)_0.8fr_1fr_auto]"
                  >
                    <div className="flex min-w-0 items-center gap-2 rounded-md border bg-background p-1.5">
                      {selectedAvatar ? (
                        <AvatarThumbnail
                          avatar={selectedAvatar}
                          className="h-14 w-14"
                          fit="contain"
                        />
                      ) : (
                        <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-md border bg-muted">
                          <UserRound className="h-6 w-6 text-muted-foreground" />
                        </div>
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium">
                          {selectedAvatar?.name || "Look não encontrado"}
                        </div>
                        <div className="truncate text-[11px] text-muted-foreground">
                          {selectedAvatar?.groupName || "Identidade HeyGen"}
                        </div>
                      </div>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        className="shrink-0"
                        onClick={() =>
                          setChoosingLookIndex((current) => (current === index ? null : index))
                        }
                      >
                        Escolher
                      </Button>
                    </div>
                    <Select
                      value={look.role}
                      onValueChange={(value) =>
                        updateLook(index, {
                          role: value as AvatarSetRole,
                          label: avatarSetRoleLabel(value as AvatarSetRole),
                        })
                      }
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {AVATAR_SET_ROLE_OPTIONS.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Input
                      value={look.label}
                      onChange={(event) => updateLook(index, { label: event.target.value })}
                      placeholder="Rótulo"
                    />
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      onClick={() =>
                        setLooks((current) => current.filter((_, lookIndex) => lookIndex !== index))
                      }
                      disabled={looks.length <= 2}
                      aria-label="Remover look"
                    >
                      <Trash2 className="h-4 w-4 text-status-danger" />
                    </Button>
                    {choosingLookIndex === index ? (
                      <div className="grid gap-2 rounded-md border bg-background p-2 sm:col-span-4 sm:grid-cols-2 lg:grid-cols-3">
                        {avatars.map((avatar) => {
                          const active = avatar.id === look.avatarId;
                          const alreadyUsed = looks.some(
                            (candidate, lookIndex) =>
                              lookIndex !== index && candidate.avatarId === avatar.id,
                          );
                          return (
                            <button
                              key={avatar.id}
                              type="button"
                              onClick={() => {
                                updateLook(index, { avatarId: avatar.id });
                                setChoosingLookIndex(null);
                              }}
                              className={cn(
                                "flex min-w-0 items-center gap-2 rounded-md border p-2 text-left transition-colors hover:border-primary/50 hover:bg-muted/30",
                                active && "border-primary bg-primary/5 ring-1 ring-primary/30",
                                alreadyUsed && !active && "opacity-70",
                              )}
                            >
                              <AvatarThumbnail
                                avatar={avatar}
                                className="h-12 w-12"
                                fit="contain"
                              />
                              <span className="min-w-0 flex-1">
                                <span className="block truncate text-xs font-semibold">
                                  {avatar.name}
                                </span>
                                <span className="block truncate text-[10px] text-muted-foreground">
                                  {avatar.groupName || "Identidade HeyGen"}
                                </span>
                                {alreadyUsed && !active ? (
                                  <span className="mt-0.5 block text-[10px] text-status-warning">
                                    Já usado em outro look
                                  </span>
                                ) : null}
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </div>
          {error ? (
            <p className="rounded-md border border-status-danger/30 bg-status-danger/5 px-3 py-2 text-xs text-status-danger">
              {error}
            </p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={saving || avatars.length < 2 || looks.length < 2}>
              {saving ? "Salvando..." : "Salvar Avatar Set"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function AvatarThumbnail({
  avatar,
  className,
  fit = "cover",
}: {
  avatar: HeyGenCatalog["avatars"][number];
  className?: string;
  fit?: "cover" | "contain";
}) {
  return (
    <span className={cn("block shrink-0 overflow-hidden rounded-md border bg-muted", className)}>
      {avatar.previewImageUrl ? (
        <img
          src={avatar.previewImageUrl}
          alt={`Miniatura de ${avatar.name}`}
          className={cn("h-full w-full", fit === "contain" ? "object-contain" : "object-cover")}
        />
      ) : (
        <UserRound className="m-auto h-full w-1/2 text-muted-foreground" />
      )}
    </span>
  );
}

function orientationLabel(orientation: "portrait" | "landscape") {
  return orientation === "portrait" ? "Vertical" : "Horizontal";
}
