import { LB_TABS, isTabKey, splitBoard, myPinnedRow } from "./leaderboardTabs";

describe("leaderboardTabs", () => {
  test("four tabs, keys match the backend's VALID_KINDS", () => {
    expect(LB_TABS.map((t) => t.k)).toEqual(["overall", "kills", "quests", "playtime"]);
    expect(isTabKey("kills")).toBe(true);
    expect(isTabKey("nope")).toBe(false);
  });

  test("splitBoard: full board → 3 podium + rest", () => {
    const rows = Array.from({ length: 30 }, (_, i) => ({ user_id: `u${i}`, rank: i + 1 }));
    const { podium, list } = splitBoard(rows);
    expect(podium).toHaveLength(3);
    expect(list).toHaveLength(27);
    expect(list[0].user_id).toBe("u3");
  });

  test("splitBoard survives every degenerate backend answer", () => {
    expect(splitBoard(null)).toEqual({ podium: [], list: [] });
    expect(splitBoard(undefined)).toEqual({ podium: [], list: [] });
    expect(splitBoard("bad")).toEqual({ podium: [], list: [] });
    // malformed rows (no user_id) are dropped, never rendered
    expect(splitBoard([null, {}, { user_id: "a" }])).toEqual({ podium: [{ user_id: "a" }], list: [] });
    // short board: 2 entries → 2 podium slots, empty list
    const two = splitBoard([{ user_id: "a" }, { user_id: "b" }]);
    expect(two.podium).toHaveLength(2);
    expect(two.list).toHaveLength(0);
  });

  test("myPinnedRow: only pins a ranked viewer BELOW the visible rows", () => {
    expect(myPinnedRow({ rank: 31, user_id: "me" }, 30)).toEqual({ rank: 31, user_id: "me" });
    expect(myPinnedRow({ rank: 12, user_id: "me" }, 30)).toBeNull(); // already visible
    expect(myPinnedRow({ rank: 4, user_id: "me" }, 3)).toEqual({ rank: 4, user_id: "me" }); // short board
    expect(myPinnedRow(null, 30)).toBeNull();               // signed out / unranked
    expect(myPinnedRow({ rank: 0 }, 30)).toBeNull();        // zero-score month
    expect(myPinnedRow({ rank: "7" }, 3)).toBeNull();       // wrong type never crashes
  });
});
