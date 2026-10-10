import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import PracticeAttachments from "@/components/learning/practice/PracticeAttachments";
import { initI18n } from "@/i18n/init";
import type { NotebookEntry } from "@/lib/notebook-api";

initI18n("en");

it("shows images, audio and original-name downloads from one question", () => {
  const entry = {
    id: 42,
    attachments: [
      { kind: "image", name: "graph.png", sha256: "a".repeat(64) },
      { kind: "audio", name: "speech.mp3", sha256: "b".repeat(64) },
      { kind: "file", name: "worksheet.docx", sha256: "c".repeat(64) },
    ],
  } as NotebookEntry;
  const { container } = render(<PracticeAttachments entry={entry} workspaceId="math" />);
  expect(screen.getByRole("img", { name: "graph.png" })).toHaveAttribute(
    "src",
    expect.stringContaining("/questions/42/attachments/"),
  );
  expect(container.querySelector("audio")?.getAttribute("src")).toContain("dt_workspace=math");
  expect(screen.getAllByRole("link")).toHaveLength(3);
  expect(screen.getByRole("link", { name: "Download worksheet.docx" })).toHaveAttribute(
    "download",
    "worksheet.docx",
  );
});
