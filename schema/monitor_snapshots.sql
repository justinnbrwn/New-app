create table public.monitor_snapshots (
  user_id uuid primary key references auth.users(id) on delete cascade,
  observed_at timestamptz not null,
  workers jsonb not null check (jsonb_typeof(workers) = 'array' and jsonb_array_length(workers) <= 200 and octet_length(workers::text) <= 65536)
);
alter table public.monitor_snapshots enable row level security;
revoke all on public.monitor_snapshots from anon, authenticated;
grant select on public.monitor_snapshots to authenticated;
grant select, insert, update, delete on public.monitor_snapshots to service_role;
create policy own_monitor_snapshot on public.monitor_snapshots for select to authenticated
  using ((select auth.uid()) = user_id);
create function public.publish_monitor_snapshot(owner_id uuid, seen_at timestamptz, worker_data jsonb)
returns void language sql security invoker set search_path = '' as $$
  insert into public.monitor_snapshots(user_id, observed_at, workers)
  values(owner_id, seen_at, worker_data)
  on conflict(user_id) do update set observed_at=excluded.observed_at, workers=excluded.workers
  where public.monitor_snapshots.observed_at < excluded.observed_at;
$$;
revoke all on function public.publish_monitor_snapshot(uuid,timestamptz,jsonb) from public, anon, authenticated;
grant execute on function public.publish_monitor_snapshot(uuid,timestamptz,jsonb) to service_role;
