import { describe, expect, it } from "vitest";

import { splitWeeklyUnique } from "./weekly-archive";

describe("splitWeeklyUnique", () => {
  it("keeps the newest generated item and sends duplicate and older items to the archive", () => {
    const items = [
      { id: "old", title: "Antiga", createdAt: "2026-08-07T20:03:29.473Z" },
      { id: "duplicate", title: "Nova", createdAt: "2026-08-11T15:20:45.201850+00:00" },
      { id: "newest", title: "Nova", createdAt: "2026-08-11T15:27:11.018969+00:00" },
    ];

    const result = splitWeeklyUnique(
      items,
      (item) => item.createdAt,
      (item) => item.title.toLowerCase(),
    );

    expect(result.current.map((item) => item.id)).toEqual(["newest"]);
    expect(result.archive.map((item) => item.id)).toEqual(["duplicate", "old"]);
  });
});
