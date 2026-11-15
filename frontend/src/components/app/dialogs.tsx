import { type ReactNode, useRef, useState, type DragEvent } from 'react'
import { Check, Copy, UploadCloud } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

/** Every reject, override and stage change needs a reason. */
export function ReasonDialog({ open, title, description, confirmLabel = 'Confirm', destructive, required = true, onClose, onConfirm, children }: {
  open: boolean; title: string; description?: ReactNode; confirmLabel?: string; destructive?: boolean; required?: boolean
  onClose: () => void; onConfirm: (reason: string) => void; children?: ReactNode
}) {
  const [reason, setReason] = useState('')
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-heading">{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        {children}
        <div className="grid gap-2">
          <Label htmlFor="reason">Reason{required ? '' : ' (optional)'}</Label>
          <Textarea id="reason" value={reason} onChange={(e) => setReason(e.target.value)} rows={4} autoFocus placeholder="Recorded with your name in the audit trail. Never shown to the candidate." />
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant={destructive ? 'destructive' : 'default'} disabled={required && !reason.trim()} onClick={() => { onConfirm(reason.trim()); setReason('') }}>{confirmLabel}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function CopyButton({ value, label = 'Copy' }: { value: string; label?: string }) {
  const [done, setDone] = useState(false)
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button variant="ghost" size="icon" className="size-7" aria-label={label}
          onClick={() => void navigator.clipboard?.writeText(value).then(() => { setDone(true); window.setTimeout(() => setDone(false), 1500) })}>
          {done ? <Check className="size-3.5 text-success" /> : <Copy className="size-3.5" />}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{done ? 'Copied' : label}</TooltipContent>
    </Tooltip>
  )
}

export function FileDropzone({ accept, onFile, disabled, hint, multiple, onFiles }: {
  accept: string; onFile?: (file: File) => void; onFiles?: (files: File[]) => void; disabled?: boolean; hint?: string; multiple?: boolean
}) {
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const take = (list: FileList | null) => {
    const files = Array.from(list ?? [])
    if (!files.length || disabled) return
    if (onFiles) onFiles(files)
    else onFile?.(files[0])
  }
  return (
    <div role="button" tabIndex={0} aria-disabled={disabled} aria-label="Upload files"
      onClick={() => !disabled && input.current?.click()}
      onKeyDown={(e) => { if ((e.key === 'Enter' || e.key === ' ') && !disabled) { e.preventDefault(); input.current?.click() } }}
      onDragOver={(e) => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
      onDrop={(e: DragEvent) => { e.preventDefault(); setOver(false); take(e.dataTransfer.files) }}
      className={cn('flex cursor-pointer flex-col items-center gap-1.5 rounded-2xl border-2 border-dashed p-6 text-center transition outline-none focus-visible:ring-2 focus-visible:ring-ring',
        over ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/40 hover:bg-muted/40', disabled && 'cursor-not-allowed opacity-60')}>
      <span className="grid size-10 place-items-center rounded-xl bg-primary/15 text-violet"><UploadCloud className="size-5" /></span>
      <p className="text-sm font-semibold">Drop {multiple ? 'files' : 'a file'} here, or click to choose</p>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      <input ref={input} type="file" hidden multiple={multiple} accept={accept} onChange={(e) => { take(e.target.files); e.target.value = '' }} />
    </div>
  )
}
