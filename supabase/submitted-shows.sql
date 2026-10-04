-- Show Me NYC — shows sent in by bands and promoters, on Supabase.
-- Run this once in the Supabase SQL editor, after setup.sql (it uses
-- is_connection_admin() from there). It is safe to run again.
--
-- What it sets up:
--   * submitted_shows: one row per show sent in on submit.html. Visitors can
--     add rows and read approved ones. Nothing a visitor adds is approved;
--     only an admin (the same people as for missed connections) can approve.
--   * contact_email is write-only for visitors. Nobody can read it through
--     the public API; an admin reads it through submitted_show_contacts().

create table if not exists public.submitted_shows (
  id            bigint generated always as identity primary key,
  created_at    timestamptz not null default now(),
  night         date not null,
  start_time    text not null default ''
                check (start_time = '' or start_time ~ '^(1[0-2]|[1-9]):[0-5][0-9] (AM|PM)$'),
  venue         text not null check (char_length(btrim(venue)) between 2 and 80),
  acts          text not null check (char_length(btrim(acts)) between 2 and 300),
  note          text not null default '' check (char_length(note) <= 140),
  age           text not null default '' check (age in ('', 'AA', '16', '18', '21')),
  ticket_url    text not null default ''
                check (ticket_url = '' or (char_length(ticket_url) <= 500
                       and ticket_url ~* '^https://[a-z0-9-]+(\.[a-z0-9-]+)+(/[^\s"<>]*)?$')),
  contact_email text check (contact_email is null or (char_length(contact_email) <= 120
                       and contact_email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$')),
  approved      boolean not null default false
);
create index if not exists submitted_shows_feed on public.submitted_shows (approved, night);

-- Runs before every new row: tidy the text, refuse tracking links and dates
-- that make no sense, and stop a flood from piling up unread rows.
create or replace function public.submitted_shows_guard()
returns trigger
language plpgsql security definer set search_path = public
as $$
declare
  today date := (now() at time zone 'America/New_York')::date;
begin
  new.venue := regexp_replace(btrim(new.venue), '\s+', ' ', 'g');
  new.acts := regexp_replace(btrim(new.acts), '\s+', ' ', 'g');
  new.note := regexp_replace(btrim(coalesce(new.note, '')), '\s+', ' ', 'g');
  new.start_time := btrim(coalesce(new.start_time, ''));
  new.age := coalesce(new.age, '');
  new.ticket_url := btrim(coalesce(new.ticket_url, ''));
  new.contact_email := nullif(btrim(coalesce(new.contact_email, '')), '');
  if not public.is_connection_admin() then
    new.approved := false;
  end if;
  if new.night < today - 1 or new.night > today + 366 then
    raise exception 'Pick a date from today to a year from now.';
  end if;
  if new.ticket_url ~* '^https://([a-z0-9-]+\.)*(evyy\.net|pxf\.io|sjv\.io)(/|$)' then
    raise exception 'Use the direct ticket link, not a tracking link.';
  end if;
  if exists (
    select 1 from public.submitted_shows s
    where s.night = new.night and lower(s.venue) = lower(new.venue) and lower(s.acts) = lower(new.acts)
  ) then
    raise exception 'That show has already been sent in.';
  end if;
  if (select count(*) from public.submitted_shows where not approved) >= 200 then
    raise exception 'Too many shows are waiting to be checked. Try again later.';
  end if;
  return new;
end;
$$;

drop trigger if exists submitted_shows_guard on public.submitted_shows;
create trigger submitted_shows_guard
  before insert on public.submitted_shows
  for each row execute function public.submitted_shows_guard();

-- Row level security: the rules the public API enforces.
alter table public.submitted_shows enable row level security;

drop policy if exists "read approved shows" on public.submitted_shows;
create policy "read approved shows" on public.submitted_shows
  for select to anon, authenticated
  using (approved or public.is_connection_admin());

drop policy if exists "anyone can submit a show" on public.submitted_shows;
create policy "anyone can submit a show" on public.submitted_shows
  for insert to anon, authenticated
  with check (approved = false);

drop policy if exists "admins approve shows" on public.submitted_shows;
create policy "admins approve shows" on public.submitted_shows
  for update to authenticated
  using (public.is_connection_admin())
  with check (public.is_connection_admin());

drop policy if exists "admins delete shows" on public.submitted_shows;
create policy "admins delete shows" on public.submitted_shows
  for delete to authenticated
  using (public.is_connection_admin());

-- Column-level permissions. Visitors can fill in the listing and a contact
-- email, but cannot set "approved", the id or the timestamp. contact_email
-- is left out of the select list on purpose: no API role can read it.
revoke all on public.submitted_shows from anon, authenticated;
grant select (id, created_at, night, start_time, venue, acts, note, age, ticket_url, approved)
  on public.submitted_shows to anon, authenticated;
grant insert (night, start_time, venue, acts, note, age, ticket_url, contact_email)
  on public.submitted_shows to anon, authenticated;
grant update (approved) on public.submitted_shows to authenticated;
grant delete on public.submitted_shows to authenticated;

-- The contact emails, for an admin only. Anyone else gets no rows.
create or replace function public.submitted_show_contacts()
returns table (id bigint, contact_email text)
language sql stable security definer set search_path = public
as $$
  select s.id, s.contact_email
  from public.submitted_shows s
  where public.is_connection_admin() and s.contact_email is not null;
$$;
revoke execute on function public.submitted_show_contacts() from public, anon;
grant execute on function public.submitted_show_contacts() to authenticated;

-- The trigger function is not meant to be called through the API.
revoke execute on function public.submitted_shows_guard() from public, anon, authenticated;
