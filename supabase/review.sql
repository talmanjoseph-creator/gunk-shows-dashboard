-- Show Me NYC — a reviewer that can check what is waiting, but not approve it.
-- Run this once in the Supabase SQL editor, after setup.sql and
-- submitted-shows.sql. It is safe to run again.
--
-- What it sets up:
--   * connection_reviewers: the email addresses allowed to review. A reviewer
--     (an agent, or a person helping out) can read the shows and posts that
--     are waiting and leave a verdict on each. A reviewer can NOT approve,
--     take down or delete anything, and never sees a contact email.
--   * review_verdict / review_note / reviewed_at on both tables. The owner
--     sees them on mc-admin.html next to each waiting item.
--   * Three functions, the only way a reviewer touches the data:
--       review_queue_shows()   the sent-in shows that are waiting
--       review_queue_posts()   the missed-connections posts that are waiting
--       set_review(kind, id, verdict, note)
--   The existing rules for visitors and the owner are not changed.

create table if not exists public.connection_reviewers (
  email text primary key
);
alter table public.connection_reviewers enable row level security;  -- no policies: closed to the API
revoke all on public.connection_reviewers from anon, authenticated;

-- True when the signed-in user's email is in connection_reviewers.
create or replace function public.is_connection_reviewer()
returns boolean
language sql stable security definer set search_path = public
as $$
  select exists (
    select 1 from public.connection_reviewers r
    where lower(r.email) = lower(coalesce(auth.jwt() ->> 'email', ''))
  );
$$;

alter table public.submitted_shows
  add column if not exists review_verdict text check (review_verdict in ('ok', 'hold', 'unsure')),
  add column if not exists review_note    text check (char_length(review_note) <= 300),
  add column if not exists reviewed_at    timestamptz;
alter table public.connections
  add column if not exists review_verdict text check (review_verdict in ('ok', 'hold', 'unsure')),
  add column if not exists review_note    text check (char_length(review_note) <= 300),
  add column if not exists reviewed_at    timestamptz;

-- The verdict columns are for the owner and the reviewer only. connections
-- used to allow reading every column, so narrow it to the public ones; the
-- pages ask for these columns by name. (submitted_shows already works this way.)
revoke select on public.connections from anon, authenticated;
grant select (id, created_at, parent_id, show_slug, night, venue, name, message, approved)
  on public.connections to anon, authenticated;

-- Sent-in shows that are waiting. No contact email.
create or replace function public.review_queue_shows()
returns table (
  id bigint, created_at timestamptz, night date, start_time text, venue text, acts text,
  note text, age text, ticket_url text,
  review_verdict text, review_note text, reviewed_at timestamptz
)
language sql stable security definer set search_path = public
as $$
  select s.id, s.created_at, s.night, s.start_time, s.venue, s.acts, s.note, s.age, s.ticket_url,
         s.review_verdict, s.review_note, s.reviewed_at
  from public.submitted_shows s
  where (public.is_connection_admin() or public.is_connection_reviewer()) and not s.approved
  order by s.night, s.id;
$$;

-- Posts and replies that are waiting. A reply comes with the post it answers.
create or replace function public.review_queue_posts()
returns table (
  id bigint, created_at timestamptz, parent_id bigint, parent_message text,
  show_slug text, night date, venue text, name text, message text,
  review_verdict text, review_note text, reviewed_at timestamptz
)
language sql stable security definer set search_path = public
as $$
  select c.id, c.created_at, c.parent_id, p.message, c.show_slug, c.night, c.venue, c.name, c.message,
         c.review_verdict, c.review_note, c.reviewed_at
  from public.connections c
  left join public.connections p on p.id = c.parent_id
  where (public.is_connection_admin() or public.is_connection_reviewer()) and not c.approved
  order by c.created_at, c.id;
$$;

-- Leave a verdict on one waiting item. It changes nothing else about the row.
create or replace function public.set_review(p_kind text, p_id bigint, p_verdict text, p_note text default '')
returns void
language plpgsql security definer set search_path = public
as $$
declare
  n text := left(regexp_replace(btrim(coalesce(p_note, '')), '\s+', ' ', 'g'), 300);
  hit int;
begin
  if not (public.is_connection_admin() or public.is_connection_reviewer()) then
    raise exception 'Not allowed.';
  end if;
  if p_verdict is null or p_verdict not in ('ok', 'hold', 'unsure') then
    raise exception 'The verdict must be ok, hold or unsure.';
  end if;
  if p_kind = 'show' then
    update public.submitted_shows
       set review_verdict = p_verdict, review_note = n, reviewed_at = now()
     where id = p_id and not approved;
  elsif p_kind = 'post' then
    update public.connections
       set review_verdict = p_verdict, review_note = n, reviewed_at = now()
     where id = p_id and not approved;
  else
    raise exception 'The kind must be show or post.';
  end if;
  get diagnostics hit = row_count;
  if hit = 0 then
    raise exception 'Nothing waiting with that number.';
  end if;
end;
$$;

-- Signed-in users may call these; each one answers only an admin or a reviewer.
revoke execute on function public.review_queue_shows() from public, anon;
revoke execute on function public.review_queue_posts() from public, anon;
revoke execute on function public.set_review(text, bigint, text, text) from public, anon;
grant execute on function public.review_queue_shows() to authenticated;
grant execute on function public.review_queue_posts() to authenticated;
grant execute on function public.set_review(text, bigint, text, text) to authenticated;

-- LAST STEP, done by the owner and NOT saved in the repo:
--   1. Supabase dashboard > Authentication > Users > Add user: an email and
--      password for the reviewer.
--   2. In the SQL editor:
--        insert into public.connection_reviewers (email) values ('reviewer@example.com')
--        on conflict do nothing;
