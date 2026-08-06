import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { useStore } from "@/lib/store";
import { fetchInstagramStatus, saveSettings, type InstagramStatus } from "@/lib/api/local";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { Instagram, Loader2, RefreshCcw, Save } from "lucide-react";
import { defaultSettings } from "@/lib/mock-data";

type RadarFonte = "google_news" | "gdelt" | "pubmed" | "reddit" | "serpapi";

const radarSources: Array<{ id: RadarFonte; label: string; description: string }> = [
  {
    id: "google_news",
    label: "Google News",
    description: "Notícias brasileiras recentes",
  },
  {
    id: "gdelt",
    label: "GDELT",
    description: "Mídia global e alto volume",
  },
  {
    id: "pubmed",
    label: "PubMed",
    description: "Estudos científicos recentes",
  },
  {
    id: "reddit",
    label: "Reddit",
    description: "Dúvidas reais do público",
  },
  {
    id: "serpapi",
    label: "Google Trends",
    description: "Opcional, usa SERPAPI_KEY",
  },
];

export const Route = createFileRoute("/_app/configuracoes")({
  head: () => ({
    meta: [
      { title: "Configuracoes | AI Video Creator" },
      {
        name: "description",
        content:
          "Temas prioritarios, palavras proibidas e status das integracoes (HeyGen, Meta, Sheets).",
      },
      { property: "og:title", content: "Configuracoes | AI Video Creator" },
      {
        property: "og:description",
        content: "Configuracoes da esteira editorial.",
      },
    ],
  }),
  component: ConfiguracoesPage,
});

function ConfiguracoesPage() {
  const settings = useStore((s) => s.settings);
  const setSettings = useStore((s) => s.setSettings);
  const resetSeed = useStore((s) => s.resetSeed);
  const currentRadar = settings.radar ?? defaultSettings.radar;
  const currentIntegrations = settings.integracoes ?? defaultSettings.integracoes;

  const [temas, setTemas] = useState(settings.temasPrioritarios.join("\n"));
  const [palavras, setPalavras] = useState(settings.palavrasProibidas.join("\n"));
  const [termosExtras, setTermosExtras] = useState(currentRadar.termosExtras.join("\n"));
  const [fontes, setFontes] = useState<RadarFonte[]>(
    currentRadar.fontes ?? defaultSettings.radar.fontes,
  );
  const [periodo, setPeriodo] = useState(currentRadar.periodo);
  const [limite, setLimite] = useState(String(currentRadar.limitePorBusca));
  const [potencialMinimo, setPotencialMinimo] = useState(String(currentRadar.potencialMinimo));
  const [integracoes, setIntegracoes] = useState(currentIntegrations);
  const [saving, setSaving] = useState(false);
  const [instagramStatus, setInstagramStatus] = useState<InstagramStatus | null>(null);
  const [checkingInstagram, setCheckingInstagram] = useState(false);

  useEffect(() => {
    setTemas(settings.temasPrioritarios.join("\n"));
    setPalavras(settings.palavrasProibidas.join("\n"));
    const nextRadar = settings.radar ?? defaultSettings.radar;
    setTermosExtras(nextRadar.termosExtras.join("\n"));
    setFontes(nextRadar.fontes ?? defaultSettings.radar.fontes);
    setPeriodo(nextRadar.periodo);
    setLimite(String(nextRadar.limitePorBusca));
    setPotencialMinimo(String(nextRadar.potencialMinimo));
    setIntegracoes(settings.integracoes ?? defaultSettings.integracoes);
  }, [settings]);

  const testarInstagram = useCallback(async (showToast = true) => {
    setCheckingInstagram(true);
    try {
      const status = await fetchInstagramStatus();
      setInstagramStatus(status);
      setIntegracoes((current) => ({ ...current, meta: status.connected }));
      if (showToast) {
        if (status.connected) toast.success(`Instagram @${status.account?.username} conectado.`);
        else toast.error(status.detail);
      }
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Nao foi possivel testar o Instagram.";
      setInstagramStatus({ configured: false, connected: false, account: null, detail: message });
      if (showToast) toast.error(message);
    } finally {
      setCheckingInstagram(false);
    }
  }, []);

  useEffect(() => {
    void testarInstagram(false);
  }, [testarInstagram]);

  async function salvar() {
    const next = {
      ...settings,
      temasPrioritarios: lines(temas),
      palavrasProibidas: lines(palavras),
      radar: {
        termosExtras: lines(termosExtras),
        fontes: fontes.length ? fontes : defaultSettings.radar.fontes,
        periodo,
        limitePorBusca: clampNumber(limite, 1, 50, 20),
        potencialMinimo: clampNumber(potencialMinimo, 1, 10, 1),
      },
      integracoes,
    };
    setSaving(true);
    try {
      const saved = await saveSettings(next);
      setSettings(saved);
      toast.success("Configurações salvas no backend.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Não foi possível salvar.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <AppShell
      title="Configuracoes"
      actions={
        <Button size="sm" onClick={() => void salvar()} disabled={saving}>
          {saving ? (
            <Loader2 className="mr-1 h-4 w-4 animate-spin" />
          ) : (
            <Save className="mr-1 h-4 w-4" />
          )}
          {saving ? "Salvando..." : "Salvar"}
        </Button>
      }
    >
      <div className="grid gap-4 xl:grid-cols-2">
        <section className="rounded-md border bg-card p-4">
          <h2 className="mb-3 text-sm font-semibold">Editorial</h2>
          <div className="space-y-3">
            <div>
              <Label className="text-xs">Temas prioritarios (um por linha)</Label>
              <Textarea rows={6} value={temas} onChange={(e) => setTemas(e.target.value)} />
            </div>
            <div>
              <Label className="text-xs">Palavras proibidas (um por linha)</Label>
              <Textarea rows={6} value={palavras} onChange={(e) => setPalavras(e.target.value)} />
              <p className="mt-1 text-[11px] text-muted-foreground">
                Serao usadas para bloquear roteiros com sensacionalismo ou promessa de resultado.
              </p>
            </div>
          </div>
        </section>

        <section className="rounded-md border bg-card p-4">
          <h2 className="mb-3 text-sm font-semibold">Radar de tendências</h2>
          <div className="space-y-3">
            <div>
              <Label className="text-xs">Termos extras do buscador (um por linha)</Label>
              <Textarea
                rows={6}
                value={termosExtras}
                onChange={(e) => setTermosExtras(e.target.value)}
                placeholder={"atividade física\nsono\ncompulsão alimentar"}
              />
              <p className="mt-1 text-[11px] text-muted-foreground">
                A busca usa temas prioritários + termos extras para montar consultas no Google News.
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <div>
                <Label className="text-xs">Janela</Label>
                <Select
                  value={periodo}
                  onValueChange={(value) => setPeriodo(value as typeof periodo)}
                >
                  <SelectTrigger className="mt-1.5">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="dia">Último dia</SelectItem>
                    <SelectItem value="semana">Última semana</SelectItem>
                    <SelectItem value="quinzena">Últimos 15 dias</SelectItem>
                    <SelectItem value="mes">Últimos 30 dias</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="radar-limit" className="text-xs">
                  Salvar até
                </Label>
                <Input
                  id="radar-limit"
                  className="mt-1.5"
                  type="number"
                  min={1}
                  max={50}
                  value={limite}
                  onChange={(event) => setLimite(event.target.value)}
                />
              </div>
              <div>
                <Label htmlFor="radar-min" className="text-xs">
                  Potencial mínimo
                </Label>
                <Input
                  id="radar-min"
                  className="mt-1.5"
                  type="number"
                  min={1}
                  max={10}
                  value={potencialMinimo}
                  onChange={(event) => setPotencialMinimo(event.target.value)}
                />
              </div>
            </div>
            <div>
              <Label className="text-xs">Fontes de busca</Label>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {radarSources.map((source) => (
                  <label
                    key={source.id}
                    className="flex cursor-pointer items-start gap-3 rounded-md border p-3"
                  >
                    <Checkbox
                      checked={fontes.includes(source.id)}
                      onCheckedChange={(checked) => {
                        setFontes((current) =>
                          checked
                            ? Array.from(new Set([...current, source.id]))
                            : current.filter((item) => item !== source.id),
                        );
                      }}
                      className="mt-0.5"
                    />
                    <span>
                      <span className="block text-sm font-medium">{source.label}</span>
                      <span className="block text-xs text-muted-foreground">
                        {source.description}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section className="rounded-md border bg-card p-4">
          <h2 className="mb-3 text-sm font-semibold">Integracoes</h2>
          <div className="space-y-3">
            <IntegrationRow
              label="HeyGen (video)"
              desc="Necessario para producao de videos."
              value={integracoes.heygen}
              onChange={(v) => setIntegracoes((current) => ({ ...current, heygen: v }))}
            />
            <div className="rounded border p-3">
              <div className="flex items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-3">
                  <Instagram className="h-5 w-5 shrink-0" />
                  <div className="min-w-0">
                    <div className="text-sm font-medium">Instagram / Meta Graph API</div>
                    <div className="truncate text-xs text-muted-foreground">
                      {instagramStatus?.connected
                        ? `@${instagramStatus.account?.username ?? "conta profissional"}`
                        : (instagramStatus?.detail ?? "Verificando credenciais do backend...")}
                    </div>
                  </div>
                </div>
                <span
                  className={
                    "shrink-0 text-xs " +
                    (instagramStatus?.connected ? "text-status-success" : "text-muted-foreground")
                  }
                >
                  {checkingInstagram
                    ? "Verificando..."
                    : instagramStatus?.connected
                      ? "Conectado"
                      : "Nao conectado"}
                </span>
              </div>
              <Button
                className="mt-3"
                size="sm"
                variant="secondary"
                disabled={checkingInstagram}
                onClick={() => void testarInstagram()}
              >
                {checkingInstagram ? (
                  <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCcw className="mr-1 h-4 w-4" />
                )}
                Testar conexao
              </Button>
            </div>
            <IntegrationRow
              label="Google Sheets"
              desc="Import/export opcional da esteira editorial."
              value={integracoes.googleSheets}
              onChange={(v) => setIntegracoes((current) => ({ ...current, googleSheets: v }))}
            />
          </div>
          <p className="mt-3 text-[11px] text-muted-foreground">
            As chaves ficam apenas no backend. A conexao do Instagram acima e validada em tempo real
            e habilita a publicacao de Reels e Stories na tela de cada video pronto.
          </p>
        </section>

        <section className="rounded-md border bg-card p-4">
          <h2 className="mb-2 text-sm font-semibold">Dados de exemplo</h2>
          <p className="mb-3 text-xs text-muted-foreground">
            Restaurar o estado inicial (uma tendencia, uma ideia, um roteiro aguardando validacao,
            um post pendente).
          </p>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              resetSeed();
              toast("Dados de exemplo restaurados.");
            }}
          >
            Restaurar seed
          </Button>
        </section>
      </div>
    </AppShell>
  );
}

function lines(value: string): string[] {
  return Array.from(
    new Set(
      value
        .split("\n")
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  );
}

function clampNumber(value: string, min: number, max: number, fallback: number): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(min, Math.min(max, Math.round(parsed)));
}

function IntegrationRow({
  label,
  desc,
  value,
  onChange,
}: {
  label: string;
  desc: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between rounded border p-3">
      <div>
        <div className="text-sm font-medium">{label}</div>
        <div className="text-xs text-muted-foreground">{desc}</div>
      </div>
      <div className="flex items-center gap-2">
        <span className={"text-xs " + (value ? "text-status-success" : "text-muted-foreground")}>
          {value ? "Conectado" : "Nao conectado"}
        </span>
        <Switch checked={value} onCheckedChange={onChange} />
      </div>
    </div>
  );
}
