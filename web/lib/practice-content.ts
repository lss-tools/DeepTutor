import { apiUrl } from '@/lib/api'
import { scopedUrl } from '@/lib/workspace-scope'
import type { NotebookEntry } from '@/lib/notebook-api'

/** Older generated stems sometimes put a fenced block directly after prose. */
export function practiceMarkdown(content: string): string {
  return content.replace(/([^\n])(```[\w+-]*[ \t]*\r?\n)/g, "$1\n\n$2");
}

/** Resolve imported inline images without losing their order or graph labels. */
export function practiceAssetMarkdown(
  content: string,
  entry: Pick<NotebookEntry, 'id' | 'attachments'>,
  workspaceId?: string,
): string {
  const attachments = new Map((entry.attachments ?? []).map(asset => [asset.name, asset]))
  return content.replace(/practice-asset:([A-Za-z0-9._-]+)/g, (original, name: string) => {
    const asset = attachments.get(name)
    if (!asset) return original
    const path = `/api/question-notebook/practice/questions/${entry.id}/attachments/${asset.sha256}`
    return apiUrl(scopedUrl(path, workspaceId))
  })
}
