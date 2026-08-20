import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  clearSessionResourceCache,
  loadSessionResource,
  readSessionResource,
  writeSessionResource,
} from "./session-resource-cache";

describe("session resource cache", () => {
  beforeEach(() => {
    clearSessionResourceCache();
    vi.useRealTimers();
  });

  it("deduplicates concurrent loads and reuses a fresh value", async () => {
    const loader = vi.fn(async () => ({ items: ["avatar"] }));

    const first = loadSessionResource("avatars", loader, { ttlMs: 60_000 });
    const second = loadSessionResource("avatars", loader, { ttlMs: 60_000 });

    await expect(Promise.all([first, second])).resolves.toEqual([
      { items: ["avatar"] },
      { items: ["avatar"] },
    ]);
    await expect(loadSessionResource("avatars", loader, { ttlMs: 60_000 })).resolves.toEqual({
      items: ["avatar"],
    });
    expect(loader).toHaveBeenCalledOnce();
  });

  it("keeps stale data visible while refreshing it", async () => {
    writeSessionResource("pack:s-1", { title: "Anterior" }, 0);
    let finishRefresh: ((value: { title: string }) => void) | undefined;
    const refresh = loadSessionResource(
      "pack:s-1",
      () =>
        new Promise<{ title: string }>((resolve) => {
          finishRefresh = resolve;
        }),
      { ttlMs: 60_000 },
    );

    expect(readSessionResource("pack:s-1")).toEqual({ title: "Anterior" });
    await Promise.resolve();
    expect(finishRefresh).toBeTypeOf("function");
    finishRefresh?.({ title: "Atualizado" });
    await refresh;
    expect(readSessionResource("pack:s-1")).toEqual({ title: "Atualizado" });
  });

  it("forces an explicit refresh and preserves the last value on failure", async () => {
    const loader = vi.fn(async () => "novo");
    writeSessionResource("catalog", "salvo", 60_000);

    await expect(
      loadSessionResource("catalog", loader, { ttlMs: 60_000, force: true }),
    ).resolves.toBe("novo");
    expect(loader).toHaveBeenCalledOnce();

    await expect(
      loadSessionResource(
        "catalog",
        async () => {
          throw new Error("offline");
        },
        { ttlMs: 60_000, force: true },
      ),
    ).rejects.toThrow("offline");
    expect(readSessionResource("catalog")).toBe("novo");
  });
});
