import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { AppShell } from "@/components/app-shell";
import { useStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";

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

  const [temas, setTemas] = useState(settings.temasPrioritarios.join("\n"));
  const [palavras, setPalavras] = useState(
    settings.palavrasProibidas.join("\n"),
  );

  return (
    <AppShell
      title="Configuracoes"
      actions={
        <Button
          size="sm"
          onClick={() => {
            setSettings({
              ...settings,
              temasPrioritarios: temas.split("\n").map((s) => s.trim()).filter(Boolean),
              palavrasProibidas: palavras.split("\n").map((s) => s.trim()).filter(Boolean),
            });
            toast.success("Configuracoes salvas.");
          }}
        >
          Salvar
        </Button>
      }
    >
      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-md border bg-card p-4">
          <h2 className="mb-3 text-sm font-semibold">Editorial</h2>
          <div className="space-y-3">
            <div>
              <Label className="text-xs">Temas prioritarios (um por linha)</Label>
              <Textarea
                rows={6}
                value={temas}
                onChange={(e) => setTemas(e.target.value)}
              />
            </div>
            <div>
              <Label className="text-xs">Palavras proibidas (um por linha)</Label>
              <Textarea
                rows={6}
                value={palavras}
                onChange={(e) => setPalavras(e.target.value)}
              />
              <p className="mt-1 text-[11px] text-muted-foreground">
                Serao usadas para bloquear roteiros com sensacionalismo ou
                promessa de resultado.
              </p>
            </div>
          </div>
        </section>

        <section className="rounded-md border bg-card p-4">
          <h2 className="mb-3 text-sm font-semibold">Integracoes</h2>
          <div className="space-y-3">
            <IntegrationRow
              label="HeyGen (video)"
              desc="Necessario para producao de videos."
              value={settings.integracoes.heygen}
              onChange={(v) =>
                setSettings({
                  ...settings,
                  integracoes: { ...settings.integracoes, heygen: v },
                })
              }
            />
            <IntegrationRow
              label="Meta Graph API"
              desc="Necessario para metricas de Instagram/Reels."
              value={settings.integracoes.meta}
              onChange={(v) =>
                setSettings({
                  ...settings,
                  integracoes: { ...settings.integracoes, meta: v },
                })
              }
            />
            <IntegrationRow
              label="Google Sheets"
              desc="Import/export opcional da esteira editorial."
              value={settings.integracoes.googleSheets}
              onChange={(v) =>
                setSettings({
                  ...settings,
                  integracoes: { ...settings.integracoes, googleSheets: v },
                })
              }
            />
          </div>
          <p className="mt-3 text-[11px] text-muted-foreground">
            Chaves de API (HEYGEN_API_KEY, META_ACCESS_TOKEN, credenciais Google)
            ficam apenas no backend. Este toggle simula a conexao ate a fase de
            integracao real.
          </p>
        </section>

        <section className="rounded-md border bg-card p-4 lg:col-span-2">
          <h2 className="mb-2 text-sm font-semibold">Dados de exemplo</h2>
          <p className="mb-3 text-xs text-muted-foreground">
            Restaurar o estado inicial (uma tendencia, uma ideia, um roteiro
            aguardando validacao, um post pendente).
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
        <span
          className={
            "text-xs " +
            (value ? "text-status-success" : "text-muted-foreground")
          }
        >
          {value ? "Conectado" : "Nao conectado"}
        </span>
        <Switch checked={value} onCheckedChange={onChange} />
      </div>
    </div>
  );
}
