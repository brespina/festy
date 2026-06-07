-- festbot schema v1
-- Run this in the Supabase SQL editor on a fresh project.

-- ============================================================
-- TRIPS
-- ============================================================
create table if not exists trips (
  id             bigserial primary key,
  name           text not null,
  festival_name  text,
  start_date     date not null,
  end_date       date not null,
  status         text not null default 'planning' check (status in ('planning','active','past','archived')),
  discord_guild_id    bigint not null,
  discord_role_id     bigint,
  discord_category_id bigint,
  created_by_discord_id bigint,
  created_at     timestamptz not null default now()
);

create index if not exists idx_trips_guild on trips(discord_guild_id);
create index if not exists idx_trips_status on trips(status);

-- Map channels to trips. A trip can have multiple linked channels
-- (e.g. general, logistics, sets). One is flagged primary for bot announcements.
create table if not exists trip_channels (
  trip_id      bigint not null references trips(id) on delete cascade,
  channel_id   bigint not null,
  is_primary   boolean not null default false,
  primary key (trip_id, channel_id)
);

create index if not exists idx_trip_channels_channel on trip_channels(channel_id);

-- ============================================================
-- MEMBERS (per-trip membership)
-- ============================================================
create table if not exists members (
  id                bigserial primary key,
  trip_id           bigint not null references trips(id) on delete cascade,
  discord_user_id   bigint not null,
  display_name      text not null,
  arrival           date,
  departure         date,
  needs_ride        boolean not null default false,
  can_offer_ride    boolean not null default false,
  notes             text,
  joined_at         timestamptz not null default now(),
  unique (trip_id, discord_user_id)
);

create index if not exists idx_members_trip on members(trip_id);
create index if not exists idx_members_user on members(discord_user_id);

-- ============================================================
-- LODGING
-- ============================================================
create table if not exists lodging (
  id          bigserial primary key,
  trip_id     bigint not null references trips(id) on delete cascade,
  name        text not null,
  type        text,  -- 'airbnb', 'hotel', 'campsite', 'tent', etc.
  address     text,
  total_cost  numeric(10,2),
  capacity    int,
  notes       text,
  created_at  timestamptz not null default now()
);

create table if not exists lodging_members (
  lodging_id   bigint not null references lodging(id) on delete cascade,
  member_id    bigint not null references members(id) on delete cascade,
  amount_owed  numeric(10,2),
  paid         boolean not null default false,
  primary key (lodging_id, member_id)
);

-- ============================================================
-- PACKING
-- ============================================================
create table if not exists packing_items (
  id                     bigserial primary key,
  trip_id                bigint not null references trips(id) on delete cascade,
  item                   text not null,
  shared                 boolean not null default false,  -- group item vs personal
  assigned_to_member_id  bigint references members(id) on delete set null,
  brought                boolean not null default false,
  created_by_discord_id  bigint,
  created_at             timestamptz not null default now()
);

create index if not exists idx_packing_trip on packing_items(trip_id);

-- ============================================================
-- PHASE 2 placeholders (schema now, features later)
-- ============================================================
create table if not exists festival_sets (
  id          bigserial primary key,
  trip_id     bigint not null references trips(id) on delete cascade,
  artist      text not null,
  stage       text,
  starts_at   timestamptz not null,
  ends_at     timestamptz,
  notes       text
);

create table if not exists set_interests (
  set_id     bigint not null references festival_sets(id) on delete cascade,
  member_id  bigint not null references members(id) on delete cascade,
  primary key (set_id, member_id)
);

create table if not exists meetups (
  id           bigserial primary key,
  trip_id      bigint not null references trips(id) on delete cascade,
  location     text not null,
  meet_at      timestamptz not null,
  description  text,
  created_by_member_id bigint references members(id) on delete set null,
  created_at   timestamptz not null default now()
);

create table if not exists meetup_rsvps (
  meetup_id  bigint not null references meetups(id) on delete cascade,
  member_id  bigint not null references members(id) on delete cascade,
  status     text not null default 'yes' check (status in ('yes','no','maybe')),
  primary key (meetup_id, member_id)
);

create table if not exists expenses (
  id                 bigserial primary key,
  trip_id            bigint not null references trips(id) on delete cascade,
  paid_by_member_id  bigint references members(id) on delete set null,
  amount             numeric(10,2) not null,
  description        text,
  created_at         timestamptz not null default now()
);

create table if not exists expense_splits (
  expense_id  bigint not null references expenses(id) on delete cascade,
  member_id   bigint not null references members(id) on delete cascade,
  share       numeric(10,2) not null,
  primary key (expense_id, member_id)
);
