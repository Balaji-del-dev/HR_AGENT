import { useState, type KeyboardEvent, type ReactNode } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { Controller, useForm } from 'react-hook-form'
import { X } from 'lucide-react'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { useApiV1MembersList } from '@/shared/api/generated/auth/auth'
import { useApiV1CompBandsList } from '@/shared/api/generated/requisitions/requisitions'

const schema = z.object({
  title: z.string().min(3, 'At least 3 characters').max(200),
  department: z.string().min(2, 'At least 2 characters').max(120),
  location: z.string().max(120),
  level: z.string().max(40),
  employment_type: z.enum(['full_time', 'part_time', 'contract', 'intern']),
  headcount: z.coerce.number().int().min(1, 'At least 1').max(1000),
  summary: z.string().max(5000),
  must_have_skills: z.array(z.string()).max(30),
  nice_to_have_skills: z.array(z.string()).max(30),
  comp_band_id: z.string().nullable(),
  hiring_manager_id: z.string().uuid('Pick a hiring manager'),
})
export type RequisitionValues = z.infer<typeof schema>

export const emptyRequisition: RequisitionValues = {
  title: '', department: 'Engineering', location: '', level: '', employment_type: 'full_time', headcount: 1,
  summary: '', must_have_skills: [], nice_to_have_skills: [], comp_band_id: null, hiring_manager_id: '',
}

function Field({ label, htmlFor, error, hint, children, className }: { label: string; htmlFor?: string; error?: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <div className={`grid gap-1.5 ${className ?? ''}`}>
      <Label htmlFor={htmlFor} className="text-[13px]">{label}</Label>
      {children}
      {error ? <p className="text-xs text-destructive">{error}</p> : hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  )
}

/** Type a skill and press Enter or comma. Backspace on an empty box removes the last one. */
export function SkillsInput({ id, value, onChange, tone = 'violet' }: { id: string; value: string[]; onChange: (v: string[]) => void; tone?: 'violet' | 'muted' }) {
  const [draft, setDraft] = useState('')
  const add = () => {
    const skill = draft.trim().replace(/,$/, '')
    if (skill && !value.some((v) => v.toLowerCase() === skill.toLowerCase())) onChange([...value, skill])
    setDraft('')
  }
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); add() }
    if (e.key === 'Backspace' && !draft && value.length) onChange(value.slice(0, -1))
  }
  return (
    <div className="flex min-h-10 flex-wrap items-center gap-1.5 rounded-xl border border-input bg-card px-2 py-1.5 focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50">
      {value.map((s) => (
        <span key={s} className={`inline-flex items-center gap-1 rounded-lg px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${tone === 'violet' ? 'bg-primary/15 text-violet ring-primary/30' : 'bg-muted text-foreground/85 ring-border'}`}>
          {s}<button type="button" onClick={() => onChange(value.filter((x) => x !== s))} aria-label={`Remove ${s}`} className="rounded opacity-70 hover:opacity-100"><X className="size-3" /></button>
        </span>
      ))}
      <input id={id} value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={onKey} onBlur={add}
        placeholder={value.length ? '' : 'Type a skill, press Enter'} className="min-w-28 flex-1 bg-transparent px-1 text-sm outline-none placeholder:text-muted-foreground" />
    </div>
  )
}

export function RequisitionForm({ initial, submitLabel, onSubmit, busy, onCancel }: {
  initial: RequisitionValues
  submitLabel: string
  onSubmit: (values: RequisitionValues) => void
  busy?: boolean
  onCancel?: () => void
}) {
  const managers = useApiV1MembersList({ role: 'hiring_manager' })
  const bands = useApiV1CompBandsList()
  const { control, register, handleSubmit, formState: { errors } } = useForm({ resolver: zodResolver(schema), defaultValues: initial })
  return (
    <form onSubmit={handleSubmit((values) => onSubmit(values as RequisitionValues))} noValidate className="grid gap-5">
      <Field label="Job title" htmlFor="title" error={errors.title?.message}>
        <Input id="title" {...register('title')} placeholder="e.g. Senior Python Engineer" aria-invalid={Boolean(errors.title)} />
      </Field>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Field label="Department" htmlFor="department" error={errors.department?.message}><Input id="department" {...register('department')} /></Field>
        <Field label="Location" htmlFor="location"><Input id="location" {...register('location')} placeholder="Bengaluru · hybrid" /></Field>
        <Field label="Level" htmlFor="level"><Input id="level" {...register('level')} placeholder="L4" /></Field>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Field label="Employment type">
          <Controller control={control} name="employment_type" render={({ field }) => (
            <Select value={field.value} onValueChange={field.onChange}>
              <SelectTrigger className="w-full" aria-label="Employment type"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="full_time">Full time</SelectItem><SelectItem value="part_time">Part time</SelectItem>
                <SelectItem value="contract">Contract</SelectItem><SelectItem value="intern">Intern</SelectItem>
              </SelectContent>
            </Select>
          )} />
        </Field>
        <Field label="Openings" htmlFor="headcount" error={errors.headcount?.message}><Input id="headcount" type="number" min={1} {...register('headcount')} /></Field>
        <Field label="Pay band">
          <Controller control={control} name="comp_band_id" render={({ field }) => (
            <Select value={field.value ?? 'none'} onValueChange={(v) => field.onChange(v === 'none' ? null : v)}>
              <SelectTrigger className="w-full" aria-label="Pay band"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">None yet</SelectItem>
                {bands.data?.results?.map((b) => (
                  <SelectItem key={b.id} value={b.id}>{b.department} {b.level} · {b.currency} {Number(b.min_salary).toLocaleString()}–{Number(b.max_salary).toLocaleString()}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          )} />
        </Field>
      </div>
      <Field label="Hiring manager" error={errors.hiring_manager_id?.message}>
        <Controller control={control} name="hiring_manager_id" render={({ field }) => (
          <Select value={field.value || undefined} onValueChange={field.onChange}>
            <SelectTrigger className="w-full" aria-label="Hiring manager" aria-invalid={Boolean(errors.hiring_manager_id)}><SelectValue placeholder="Choose who owns this hire" /></SelectTrigger>
            <SelectContent>{(managers.data ?? []).map((m) => <SelectItem key={m.user_id} value={m.user_id}>{m.full_name}</SelectItem>)}</SelectContent>
          </Select>
        )} />
      </Field>
      <Field label="Why this role exists" htmlFor="summary" hint="The business need. The JD agent drafts from this.">
        <Textarea id="summary" rows={3} {...register('summary')} />
      </Field>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Must-have skills" htmlFor="must" hint="Checked against every resume, with evidence.">
          <Controller control={control} name="must_have_skills" render={({ field }) => <SkillsInput id="must" value={field.value} onChange={field.onChange} />} />
        </Field>
        <Field label="Nice-to-have skills" htmlFor="nice">
          <Controller control={control} name="nice_to_have_skills" render={({ field }) => <SkillsInput id="nice" value={field.value} onChange={field.onChange} tone="muted" />} />
        </Field>
      </div>
      <div className="flex justify-end gap-2 border-t pt-4">
        {onCancel && <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>}
        <Button type="submit" disabled={busy}>{submitLabel}</Button>
      </div>
    </form>
  )
}
