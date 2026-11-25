\set ON_ERROR_STOP on
BEGIN;

CREATE TABLE IF NOT EXISTS public.lg_thinq_daily_energy (
    device text NOT NULL CHECK (btrim(device) <> ''),
    day date NOT NULL,
    energy_wh bigint NOT NULL CHECK (energy_wh >= 0),
    PRIMARY KEY (device, day)
);

CREATE TABLE IF NOT EXISTS public.lg_thinq_monthly_energy (
    device text NOT NULL CHECK (btrim(device) <> ''),
    month date NOT NULL CHECK (EXTRACT(DAY FROM month) = 1),
    energy_wh bigint NOT NULL CHECK (energy_wh >= 0),
    PRIMARY KEY (device, month)
);

CREATE TEMP TABLE daily_import (LIKE public.lg_thinq_daily_energy INCLUDING ALL) ON COMMIT DROP;
CREATE TEMP TABLE monthly_import (LIKE public.lg_thinq_monthly_energy INCLUDING ALL) ON COMMIT DROP;

\copy daily_import (device, day, energy_wh) FROM 'ar-office-consumo-completo.csv' WITH (FORMAT csv, HEADER true, DELIMITER ';')
\copy monthly_import (device, month, energy_wh) FROM 'ar-office-consumo-mensal.csv' WITH (FORMAT csv, HEADER true, DELIMITER ';')

DO $$
BEGIN
    IF (SELECT count(*) FROM daily_import) <> 389
        OR EXISTS (SELECT FROM daily_import WHERE device <> 'AR - Office'
                   OR day NOT BETWEEN DATE '2025-11-01' AND DATE '2026-11-24') THEN
        RAISE EXCEPTION 'CSV diário divergente do histórico validado do AR - Office';
    END IF;

    IF (SELECT count(*) FROM monthly_import) <> 12
        OR EXISTS (SELECT FROM monthly_import WHERE device <> 'AR - Office'
                   OR month NOT BETWEEN DATE '2024-11-01' AND DATE '2025-10-01') THEN
        RAISE EXCEPTION 'Esperados 12 meses do AR - Office, de nov/2024 a out/2025';
    END IF;
END;
$$;

INSERT INTO public.lg_thinq_daily_energy (device, day, energy_wh)
SELECT device, day, energy_wh FROM daily_import
ON CONFLICT (device, day) DO UPDATE SET energy_wh = EXCLUDED.energy_wh;

INSERT INTO public.lg_thinq_monthly_energy (device, month, energy_wh)
SELECT device, month, energy_wh FROM monthly_import
ON CONFLICT (device, month) DO UPDATE SET energy_wh = EXCLUDED.energy_wh;

COMMIT;
