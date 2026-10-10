"use client";

import { useTranslation } from "react-i18next";
import { apiUrl } from "@/lib/api";
import { scopedUrl } from "@/lib/workspace-scope";
import type { NotebookEntry } from "@/lib/notebook-api";

export default function PracticeAttachments({
  entry,
  workspaceId,
}: {
  entry: NotebookEntry;
  workspaceId?: string;
}) {
  const { t } = useTranslation();
  if (!entry.attachments?.length) return null;
  return (
    <div className="mt-3 space-y-3">
      {entry.attachments.map(attachment => {
        const path = `/api/question-notebook/practice/questions/${entry.id}/attachments/${attachment.sha256}`;
        const url = apiUrl(scopedUrl(path, workspaceId));
        return (
          <div key={attachment.sha256} className="space-y-2">
            {attachment.kind === "image" && (
              // User files are served by the authenticated practice endpoint.
              // eslint-disable-next-line @next/next/no-img-element
              <img src={url} alt={attachment.name} className="max-h-96 max-w-full rounded-lg" />
            )}
            {attachment.kind === "audio" && (
              <audio controls preload="none" src={url} aria-label={attachment.name} className="w-full" />
            )}
            <a href={url} download={attachment.name} className="text-sm text-primary underline">
              {t("Download")} {attachment.name}
            </a>
          </div>
        );
      })}
    </div>
  );
}
