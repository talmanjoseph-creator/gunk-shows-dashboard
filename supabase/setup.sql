-- Show Me NYC — missed connections on Supabase.
-- Run this once in the Supabase SQL editor. It is safe to run again.
--
-- What it sets up:
--   * connections: posts and replies. Visitors can add rows and read approved
--     ones. Nothing a visitor adds is approved; only an admin can approve.
--   * connection_admins: the email addresses allowed to approve and delete.
--     Add yours in the SQL editor (see the end of this file). It is never
--     readable through the public API.

create table if not exists public.connections (
  id          bigint generated always as identity primary key,
  created_at  timestamptz not null default now(),
  parent_id   bigint references public.connections(id) on delete cascade,
  show_slug   text check (show_slug is null or show_slug ~ '^[a-z0-9-]{1,120}$'),
  night       date,
  venue       text check (venue is null or char_length(venue) <= 80),
  name        text not null check (char_length(btrim(name)) between 1 and 40),
  message     text not null check (char_length(btrim(message)) between 3 and 600),
  approved    boolean not null default false
);
create index if not exists connections_feed on public.connections (approved, created_at desc);
create index if not exists connections_parent on public.connections (parent_id);

create table if not exists public.connection_admins (
  email text primary key
);

-- True when the signed-in user's email is in connection_admins.
create or replace function public.is_connection_admin()
returns boolean
language sql stable security definer set search_path = public
as $$
  select exists (
    select 1 from public.connection_admins a
    where lower(a.email) = lower(coalesce(auth.jwt() ->> 'email', ''))
  );
$$;

-- Runs before every new row: tidy the text, make sure a reply points at an
-- approved top-level post, and stop a flood from piling up unread posts.
create or replace function public.connections_guard()
returns trigger
language plpgsql security definer set search_path = public
as $$
begin
  new.name := btrim(new.name);
  new.message := btrim(new.message);
  new.venue := nullif(btrim(coalesce(new.venue, '')), '');
  if not public.is_connection_admin() then
    new.approved := false;
  end if;
  if new.parent_id is not null then
    if not exists (
      select 1 from public.connections p
      where p.id = new.parent_id and p.approved and p.parent_id is null
    ) then
      raise exception 'You can only reply to a post that is up.';
    end if;
  end if;
  if (select count(*) from public.connections where not approved) >= 300 then
    raise exception 'Too many posts are waiting to be read. Try again later.';
  end if;
  return new;
end;
$$;

drop trigger if exists connections_guard on public.connections;
create trigger connections_guard
  before insert on public.connections
  for each row execute function public.connections_guard();

-- Row level security: the rules the public API enforces.
alter table public.connections enable row level security;
alter table public.connection_admins enable row level security;  -- no policies: closed to the API

drop policy if exists "read approved" on public.connections;
create policy "read approved" on public.connections
  for select to anon, authenticated
  using (approved or public.is_connection_admin());

drop policy if exists "anyone can submit" on public.connections;
create policy "anyone can submit" on public.connections
  for insert to anon, authenticated
  with check (approved = false);

drop policy if exists "admins approve" on public.connections;
create policy "admins approve" on public.connections
  for update to authenticated
  using (public.is_connection_admin())
  with check (public.is_connection_admin());

drop policy if exists "admins delete" on public.connections;
create policy "admins delete" on public.connections
  for delete to authenticated
  using (public.is_connection_admin());

-- Column-level permissions: visitors can only fill in these columns, so they
-- cannot set "approved", the id or the timestamp themselves.
revoke all on public.connections from anon, authenticated;
grant select on public.connections to anon, authenticated;
grant insert (parent_id, show_slug, night, venue, name, message) on public.connections to anon, authenticated;
grant update (approved) on public.connections to authenticated;
grant delete on public.connections to authenticated;
revoke all on public.connection_admins from anon, authenticated;

-- The trigger function is not meant to be called through the API.
-- (is_connection_admin stays callable: the read rule and the admin page use it,
-- and it only ever answers true or false about the caller.)
revoke execute on function public.connections_guard() from public, anon, authenticated;

-- LAST STEP, done by the owner in the SQL editor and NOT saved in the repo:
--   insert into public.connection_admins (email) values ('you@example.com')
--   on conflict do nothing;
