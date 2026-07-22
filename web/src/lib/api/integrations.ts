// Stubs de integracao. Nao chamar; existem apenas para marcar onde as
// integracoes reais entrarao (backend/Edge Functions) na fase 2.
// TODO(cloud): mover para server functions com chaves em process.env.

export async function fetchTrendsFromBackend(): Promise<never> {
  throw new Error("Integracao de tendencias nao implementada.");
}

export async function createHeyGenVideo(_scriptId: string): Promise<never> {
  throw new Error("Integracao HeyGen nao implementada.");
}

export async function fetchMetaInsights(_postId: string): Promise<never> {
  throw new Error("Integracao Meta Graph nao implementada.");
}

export async function importFromGoogleSheets(): Promise<never> {
  throw new Error("Integracao Google Sheets nao implementada.");
}
