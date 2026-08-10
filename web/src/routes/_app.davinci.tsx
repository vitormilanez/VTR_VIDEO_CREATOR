import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { CheckCircle2, Clapperboard, Download, Film, FolderArchive, Music2, Sparkles, Subtitles } from "lucide-react";

export const Route = createFileRoute("/_app/davinci")({
  head: () => ({
    meta: [
      { title: "DaVinci Resolve | AI Video Creator" },
      {
        name: "description",
        content: "Finalizacao profissional dos videos do AI Video Creator no DaVinci Resolve.",
      },
    ],
  }),
  component: DaVinciPage,
});

const tracks = [
  { label: "V4", title: "Textos e overlays", icon: Sparkles },
  { label: "V3", title: "Slides e imagens", icon: Film },
  { label: "V2", title: "B-roll e cenas", icon: Clapperboard },
  { label: "V1", title: "Avatar / vídeo principal", icon: Film },
  { label: "A3", title: "Efeitos sonoros", icon: Music2 },
  { label: "A2", title: "Música", icon: Music2 },
  { label: "A1", title: "Voz / áudio principal", icon: Music2 },
  { label: "SUB", title: "Legendas", icon: Subtitles },
];

function DaVinciPage() {
  return (
    <AppShell title="DaVinci Resolve">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
        <section className="rounded-2xl border bg-card p-5 shadow-sm md:p-7">
          <div className="flex flex-col gap-5 md:flex-row md:items-center md:justify-between">
            <div className="max-w-2xl">
              <div className="mb-3 flex items-center gap-2">
                <Badge variant="secondary">Finalizacao profissional</Badge>
                <Badge variant="outline">9:16 · 1080 × 1920</Badge>
              </div>
              <h2 className="font-display text-2xl font-bold tracking-tight md:text-3xl">
                Termine no DaVinci sem reconstruir o vídeo
              </h2>
              <p className="mt-2 text-sm leading-6 text-muted-foreground md:text-base">
                Esta área prepara a timeline, os assets e as legendas do AI Video Creator para uma
                edição manual final no DaVinci Resolve. O render automático atual continua independente.
              </p>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              <Button disabled title="Será habilitado quando o exportador FCPXML estiver conectado">
                <Download className="mr-2 h-4 w-4" />
                Exportar para DaVinci
              </Button>
            </div>
          </div>
        </section>

        <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
          <Card>
            <CardHeader>
              <CardTitle>Timeline planejada</CardTitle>
              <CardDescription>
                Estrutura alvo para preservar a edição inteligente em trilhas editáveis.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {tracks.map((track) => (
                <div key={track.label} className="flex items-center gap-3 rounded-lg border bg-background p-3">
                  <div className="flex h-9 w-12 shrink-0 items-center justify-center rounded-md bg-muted font-mono text-xs font-semibold">
                    {track.label}
                  </div>
                  <track.icon className="h-4 w-4 text-muted-foreground" />
                  <span className="text-sm font-medium">{track.title}</span>
                </div>
              ))}
            </CardContent>
          </Card>

          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Pacote de exportação</CardTitle>
                <CardDescription>Primeira fase sem dependência obrigatória do DaVinci.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                {[
                  "Timeline FCPXML editável",
                  "Vídeo principal e B-roll",
                  "Slides, imagens e overlays",
                  "Áudio, música e efeitos",
                  "Legendas e timestamps",
                  "Manifesto do projeto para diagnóstico",
                ].map((item) => (
                  <div key={item} className="flex items-start gap-2">
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                    <span>{item}</span>
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <FolderArchive className="h-5 w-5" />
                  Próximo slice
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm text-muted-foreground">
                <p>
                  Conectar esta tela aos vídeos produzidos, reutilizar a timeline/eventos da pós-produção
                  e gerar um ZIP portátil com FCPXML + assets.
                </p>
                <p>
                  Depois, avaliar um DaVinci Bridge opcional para automação local via scripting sem
                  substituir o pipeline FFmpeg existente.
                </p>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
