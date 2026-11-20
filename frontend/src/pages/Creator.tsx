import {Plus, Rocket, ShieldCheck} from 'lucide-react';
import {useForm} from 'react-hook-form';
import {zodResolver} from '@hookform/resolvers/zod';
import {z} from 'zod';
import {useNavigate} from 'react-router-dom';
import {PageHeading} from '@/components/layout/AppShell';
import {Tag} from '@/components/ui/badge';
import {Button} from '@/components/ui/button';
import {Panel, SectionHeading} from '@/components/ui/panel';
import {useFactory} from '@/hooks/useFactory';
import {StudioCreator} from '@/studio';

/** Espelha os limites aceitos pelo backend (POST /api/missions). */
const missionSchema = z.object({
  name: z.string().trim().min(1, 'Informe o nome').max(200),
  description: z.string().trim().min(1, 'Descreva o objetivo'),
  criteria: z.string().trim().min(1, 'Inclua ao menos um critério'),
  constraints: z.string(),
  workspace: z.string().min(1),
  template: z.string(),
  assets: z.array(z.string()),
  max_executions: z.coerce.number().int().min(1).max(200),
  mission_timeout: z.coerce.number().int().min(1).max(14400),
  agent_timeout: z.coerce.number().int().min(60).max(900),
  dry_run: z.boolean(),
});
type MissionForm = z.input<typeof missionSchema>;

function FieldError({message}: {message?: string}) {
  return message ? <span className="text-[11px] text-warn">{message}</span> : null;
}

function LegacyCreator() {
  const {data, busy, operate, setModal} = useFactory();
  const navigate = useNavigate();
  const {register, handleSubmit, watch, setValue, formState: {errors}} = useForm<MissionForm>({
    resolver: zodResolver(missionSchema),
    defaultValues: {name: '', description: '', criteria: '', constraints: '', workspace: data?.workspaces[0]?.id ?? 'managed', template: '', assets: [], max_executions: 100, mission_timeout: 3600, agent_timeout: 180, dry_run: true},
  });
  const template = watch('template');
  const isWeb = !!template;

  const submit = handleSubmit(async values => {
    const v = missionSchema.parse(values);
    const result = await operate('missions', {
      name: v.name, description: v.description, criteria: v.criteria, constraints: v.constraints, workspace: v.workspace, dry_run: v.dry_run,
      ...(v.template ? {template: v.template, assets: v.assets} : {}),
      limits: {max_executions: v.max_executions, mission_timeout: v.mission_timeout, agent_timeout: v.agent_timeout},
    });
    if (result?.dry_run) setModal({title: 'Dry-run validado', value: result});
    else if (typeof result?.id === 'string') navigate(`/missoes/${result.id}`);
  });

  return (
    <Panel className="mt-6 max-w-4xl p-4">
      <details>
        <summary>Criação técnica legada / dry-run</summary>
        <div className="mt-4">
          <SectionHeading icon={<Rocket size={20} />} title="Defina a próxima missão" aside={<Tag>PYTHON WORKFLOW</Tag>} />
          <p className="mb-6 text-[13px] text-ink-muted">O plano e as aprovações são produzidos pelos agentes existentes. Escrita exige certificação atual.</p>
          <form onSubmit={submit} className="flex flex-col gap-5" noValidate>
            <label>Nome da missão<input {...register('name')} placeholder="Ex.: Gerenciador de tarefas Python" maxLength={200} /><FieldError message={errors.name?.message} /></label>
            <label>Descrição detalhada<textarea {...register('description')} rows={4} placeholder="Descreva o objetivo e as entregas esperadas." /><FieldError message={errors.description?.message} /></label>
            <label>Critérios de aceite<textarea {...register('criteria')} rows={3} placeholder="Um critério verificável por linha." /><FieldError message={errors.criteria?.message} /></label>
            <label>Restrições técnicas<textarea {...register('constraints')} rows={2} placeholder="Tecnologias, limites e restrições." /></label>
            <label>Tipo de projeto
              <select
                {...register('template')}
                onChange={e => {
                  setValue('template', e.target.value);
                  if (e.target.value) { setValue('agent_timeout', 600); setValue('max_executions', 150); setValue('mission_timeout', 10800); }
                }}
              >
                <option value="">Python (utilitário, script, biblioteca)</option>
                {data?.templates?.map(t => <option key={t.id} value={t.id}>{t.label}</option>)}
              </select>
            </label>
            {isWeb && (
              <fieldset className="m-0 rounded-md border border-line-input p-4">
                <legend className="px-1 text-[12px] text-ink-soft">Imagens do cliente (pasta images/)</legend>
                {data?.assets?.length ? (
                  <div className="flex flex-col gap-2">
                    {data.assets.map(a => <label key={a} className="flex-row items-center gap-2"><input type="checkbox" value={a} {...register('assets')} />{a}</label>)}
                  </div>
                ) : <p className="m-0 text-[12px] text-ink-muted">Coloque PNG, JPG ou WebP em images/ na raiz da fábrica.</p>}
              </fieldset>
            )}
            <label>Workspace autorizado
              <select {...register('workspace')}>{data?.workspaces.map(w => <option value={w.id} key={w.id}>{w.label}</option>)}</select>
            </label>
            <div className="grid gap-5 sm:grid-cols-3">
              <label>Limite de execuções<input type="number" min={1} max={200} {...register('max_executions')} /><FieldError message={errors.max_executions?.message} /></label>
              <label>Duração máxima (segundos)<input type="number" min={1} max={14400} {...register('mission_timeout')} /><FieldError message={errors.mission_timeout?.message} /></label>
              <label>Tempo por agente (segundos)<input type="number" min={60} max={900} {...register('agent_timeout')} /><FieldError message={errors.agent_timeout?.message} /></label>
            </div>
            <label className="flex-row items-center gap-2"><input type="checkbox" {...register('dry_run')} />Dry-run: validar sem criar workspace ou chamar agentes</label>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#25364b] pt-5">
              <span className="flex items-center gap-2 text-[12px] text-ink-muted"><ShieldCheck size={14} />Início explícito após criação</span>
              <Button type="submit" disabled={busy}><Plus size={16} />{busy ? 'Validando…' : 'Criar missão'}</Button>
            </div>
          </form>
        </div>
      </details>
    </Panel>
  );
}

export function Creator() {
  const {access, data, refresh} = useFactory();
  const navigate = useNavigate();
  return (
    <>
      <PageHeading title="Mission Creator" description="Da ideia ao escopo aprovado. O desenvolvimento só começa depois da sua aprovação." />
      <StudioCreator access={access} briefs={data?.briefs || []} onMission={id => { refresh(); navigate(`/missoes/${id}`); }} />
      <LegacyCreator />
    </>
  );
}
