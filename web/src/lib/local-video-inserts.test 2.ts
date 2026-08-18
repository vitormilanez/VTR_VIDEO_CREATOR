import { describe, expect, it } from "vitest";
import type { LocalVideoKitInsert } from "@/lib/api/local";
import {
  createNextUnusedInsert,
  updateInsertTime,
  validateLocalVideoKitInserts,
} from "@/lib/local-video-inserts";

const FIRST_INSERT: LocalVideoKitInsert = {
  id: "insert-1",
  uploadId: "kit-insert-0123456789abcdef",
  sourceName: "apoio.mp4",
  sourceDurationSeconds: 12,
  timelineStartSeconds: 5,
  timelineEndSeconds: 8,
  sourceStartSeconds: 0,
  sourceEndSeconds: 3,
};

describe("local video inserts", () => {
  it("mantém a duração do clipe sincronizada ao mover a entrada no vídeo", () => {
    const updated = updateInsertTime(FIRST_INSERT, "timelineStartSeconds", 10);

    expect(updated.timelineStartSeconds).toBe(10);
    expect(updated.timelineEndSeconds).toBe(13);
    expect(updated.sourceStartSeconds).toBe(0);
    expect(updated.sourceEndSeconds).toBe(3);
  });

  it("reutiliza o mesmo arquivo começando depois do último trecho usado", () => {
    const next = createNextUnusedInsert(FIRST_INSERT, [FIRST_INSERT], "insert-2");

    expect(next).toMatchObject({
      sourceStartSeconds: 3,
      sourceEndSeconds: 6,
      timelineStartSeconds: 9,
      timelineEndSeconds: 12,
    });
  });

  it("avisa quando a mesma imagem ou o mesmo momento é repetido", () => {
    const repeated: LocalVideoKitInsert = {
      ...FIRST_INSERT,
      id: "insert-2",
      timelineStartSeconds: 7,
      timelineEndSeconds: 9,
      sourceStartSeconds: 2,
      sourceEndSeconds: 4,
    };

    expect(validateLocalVideoKitInserts([FIRST_INSERT, repeated], 30)).toEqual(
      expect.arrayContaining([
        "Insert 2: dois inserts ocupam o mesmo momento do vídeo.",
        "Insert 2: esse trecho do clipe já foi usado.",
      ]),
    );
  });

  it("aceita arquivos diferentes usando os mesmos segundos internos", () => {
    const otherVideo: LocalVideoKitInsert = {
      ...FIRST_INSERT,
      id: "insert-2",
      uploadId: "kit-insert-fedcba9876543210",
      sourceName: "outro-apoio.mp4",
      timelineStartSeconds: 10,
      timelineEndSeconds: 13,
    };

    expect(validateLocalVideoKitInserts([FIRST_INSERT, otherVideo], 30)).toEqual([]);
  });
});
