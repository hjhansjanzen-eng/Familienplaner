-- ═══════════════════════════════════════════════════════════
--  Familienplaner – Supabase Tabellen
--  Projekt: wbcbkrybjpmcfjoxuvch.supabase.co
--  Dieses SQL im Supabase SQL Editor ausführen (einmalig)
-- ═══════════════════════════════════════════════════════════

-- ── 1. MAHLZEITEN ───────────────────────────────────────────
-- Speichert alle Rezepte und Gerichte
create table if not exists mahlzeiten (
  id           uuid primary key default gen_random_uuid(),
  name         text not null,
  kategorie    text,
  zutaten      jsonb default '[]',
  rezept       text,
  bild_url     text,
  erstellt_am  timestamptz default now()
);

-- ── 2. WOCHENPLAN ───────────────────────────────────────────
-- Welches Gericht ist an welchem Tag / Slot geplant
create table if not exists wochenplan (
  id           uuid primary key default gen_random_uuid(),
  woche        text not null,        -- z.B. "2025-W14"
  tag          int  not null,        -- 0 = Mo, 6 = So
  slot         text not null,        -- "fruehstueck" | "mittagessen" | "abendessen"
  mahlzeit_id  uuid references mahlzeiten(id) on delete set null,
  aktualisiert timestamptz default now(),
  unique(woche, tag, slot)
);

-- ── 3. EINKAUFSLISTE ────────────────────────────────────────
-- Benutzerdefinierte Einträge + Status
create table if not exists einkaufsliste (
  id           uuid primary key default gen_random_uuid(),
  woche        text not null,
  name         text not null,
  menge        text,
  einheit      text,
  kategorie    text,
  erledigt     boolean default false,
  erstellt_am  timestamptz default now()
);

-- ── 4. FAVORITEN ────────────────────────────────────────────
-- Lieblingsmahlzeiten
create table if not exists favoriten (
  id             uuid primary key default gen_random_uuid(),
  mahlzeit_id    uuid references mahlzeiten(id) on delete cascade,
  hinzugefuegt   timestamptz default now(),
  unique(mahlzeit_id)
);

-- ── 5. EINSTELLUNGEN ────────────────────────────────────────
-- App-Konfiguration (Woche, Theme, etc.)
create table if not exists einstellungen (
  schluessel   text primary key,
  wert         jsonb,
  geaendert    timestamptz default now()
);

-- ═══════════════════════════════════════════════════════════
--  Row Level Security – für eine Familie ohne Login einfach
--  alle Operationen erlauben (anon key reicht aus)
-- ═══════════════════════════════════════════════════════════
alter table mahlzeiten    enable row level security;
alter table wochenplan    enable row level security;
alter table einkaufsliste enable row level security;
alter table favoriten     enable row level security;
alter table einstellungen enable row level security;

-- Lese- und Schreibzugriff für alle (anon key)
create policy "Alle lesen"    on mahlzeiten    for select using (true);
create policy "Alle schreiben" on mahlzeiten   for all    using (true);

create policy "Alle lesen"    on wochenplan    for select using (true);
create policy "Alle schreiben" on wochenplan   for all    using (true);

create policy "Alle lesen"    on einkaufsliste for select using (true);
create policy "Alle schreiben" on einkaufsliste for all   using (true);

create policy "Alle lesen"    on favoriten     for select using (true);
create policy "Alle schreiben" on favoriten    for all    using (true);

create policy "Alle lesen"    on einstellungen for select using (true);
create policy "Alle schreiben" on einstellungen for all   using (true);

-- ═══════════════════════════════════════════════════════════
--  Realtime aktivieren (für Echtzeit-Sync zwischen Geräten)
-- ═══════════════════════════════════════════════════════════
alter publication supabase_realtime add table mahlzeiten;
alter publication supabase_realtime add table wochenplan;
alter publication supabase_realtime add table einkaufsliste;
alter publication supabase_realtime add table favoriten;
alter publication supabase_realtime add table einstellungen;
