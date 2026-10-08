import { expect, test } from "vitest";
import { basename } from "./workflow";
test("native filenames preserve unicode and spaces on all platforms", () => {
  expect(basename("C:\\vidéos\\face test.mp4")).toBe("face test.mp4");
  expect(basename("/tmp/日本語.mp4")).toBe("日本語.mp4");
});
