-- Run in a FREE Supabase project. No billing or paid Render resource is created.
create table if not exists public.test_subscriptions (
  subscription_id text primary key check (subscription_id ~ '^sub_[A-Za-z0-9]+$'),
  user_id uuid not null references auth.users(id) on delete cascade,
  customer_id text not null check (customer_id ~ '^cus_[A-Za-z0-9]+$')
);
alter table public.test_subscriptions enable row level security;
revoke all on public.test_subscriptions from anon, authenticated;
grant select on public.test_subscriptions to authenticated;
grant select, insert, update, delete on public.test_subscriptions to service_role;
create policy own_test_subscriptions on public.test_subscriptions
  for select to authenticated using ((select auth.uid()) = user_id);
-- A subscription can never be reassigned by an upsert, even with the server key.
create function public.keep_test_subscription_owner() returns trigger
language plpgsql set search_path = '' as $$
begin
  if old.user_id <> new.user_id or old.customer_id <> new.customer_id then
    raise exception 'Subscription ownership is immutable';
  end if;
  return new;
end;
$$;
create trigger keep_test_subscription_owner before update on public.test_subscriptions
  for each row execute function public.keep_test_subscription_owner();
