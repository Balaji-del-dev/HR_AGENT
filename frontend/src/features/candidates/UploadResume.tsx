import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Progress } from '@/components/ui/progress'
import { FileDropzone } from '@/components/app/dialogs'
import { ErrorAlert } from '@/components/app/states'
import { apiV1CandidatesDocumentsUploadUrlCreate } from '@/shared/api/generated/candidates/candidates'
import { apiV1DocumentsCompleteCreate } from '@/shared/api/generated/documents/documents'
import { apiFetch } from '@/shared/api/http'

/** Ask for a short-lived upload link, send the file to quarantine, then start the scan-read-mask pipeline. */
export async function uploadResume(candidateId: string, file: File): Promise<string> {
  const link = await apiV1CandidatesDocumentsUploadUrlCreate(candidateId, { filename: file.name, content_type: file.type, size_bytes: file.size })
  const form = new FormData()
  form.append('file', file)
  await apiFetch(link.upload_url, { method: 'POST', body: form })
  await apiV1DocumentsCompleteCreate(link.document_id)
  return link.document_id
}

export function UploadResume({ candidateId }: { candidateId: string }) {
  const queryClient = useQueryClient()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const upload = async (file: File) => {
    setBusy(true); setError(null)
    try {
      await uploadResume(candidateId, file)
      toast.success('Resume uploaded', { description: 'It is being scanned, read and masked. The parsing agent runs next.' })
      void queryClient.invalidateQueries()
    } catch (caught) { setError(caught) } finally { setBusy(false) }
  }
  return (
    <div className="space-y-2">
      <FileDropzone accept=".pdf,.docx" disabled={busy} onFile={(f) => void upload(f)} hint="PDF or DOCX, up to 10 MB. Files are scanned before anyone reads them." />
      {busy && <Progress value={66} className="h-1" />}
      <ErrorAlert error={error} />
    </div>
  )
}
