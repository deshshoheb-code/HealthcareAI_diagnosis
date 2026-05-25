-- ─────────────────────────────────────────────────────────────────────────────
-- CLINICAL AI PLATFORM — SUPABASE SCHEMA
-- Run this once in your Supabase SQL editor.
-- Supabase Auth (auth.users) is used for doctor identity — no separate table needed.
-- ─────────────────────────────────────────────────────────────────────────────


-- ─────────────────────────────────────────────
-- EXTENSIONS
-- ─────────────────────────────────────────────

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";


-- ─────────────────────────────────────────────
-- DOCTOR PROFILES
-- Extends Supabase auth.users with clinical metadata.
-- Automatically populated on first login / signup.
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.doctor_profiles (
    id          UUID        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email       TEXT        NOT NULL,
    full_name   TEXT        NOT NULL,
    hospital    TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_doctor_profiles_updated_at
    BEFORE UPDATE ON public.doctor_profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ─────────────────────────────────────────────
-- PATIENTS
-- One row per unique patient.
-- Populated by Stage 1A from extracted PatientInfo.
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.patients (
    id                  UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    doctor_id           UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

    -- Core demographics (extracted by Stage 1A)
    name                TEXT,
    age                 INTEGER,
    gender              TEXT,
    contact_number      TEXT,
    address             TEXT,

    -- Admission
    admission_datetime  TIMESTAMPTZ,
    patient_id_external TEXT,           -- hospital MRN if provided in clinical notes

    -- Raw chief complaints text (what the doctor typed)
    chief_complain_raw  TEXT,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trigger_patients_updated_at
    BEFORE UPDATE ON public.patients
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE INDEX idx_patients_doctor_id ON public.patients(doctor_id);


-- ─────────────────────────────────────────────
-- SESSIONS
-- One row per pipeline run (one per patient per visit).
-- Tied to a LangGraph thread_id and Celery task_id.
-- ─────────────────────────────────────────────

CREATE TYPE session_status AS ENUM (
    'starting',
    'running',
    'paused_hitl',
    'completed',
    'failed'
);

CREATE TABLE IF NOT EXISTS public.sessions (
    id              UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    thread_id       TEXT            NOT NULL UNIQUE,    -- LangGraph / Redis key
    task_id         TEXT,                               -- Celery task ID
    doctor_id       UUID            NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    patient_id      UUID            REFERENCES public.patients(id) ON DELETE SET NULL,

    status          session_status  NOT NULL DEFAULT 'starting',
    current_stage   TEXT,           -- e.g. "hitl_2_exam_input", "crag_node"
    paused_at       TEXT,           -- HITL label if paused

    -- Timestamps
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE TRIGGER trigger_sessions_updated_at
    BEFORE UPDATE ON public.sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE INDEX idx_sessions_doctor_id  ON public.sessions(doctor_id);
CREATE INDEX idx_sessions_thread_id  ON public.sessions(thread_id);
CREATE INDEX idx_sessions_patient_id ON public.sessions(patient_id);


-- ─────────────────────────────────────────────
-- STAGE LOGS
-- Every node execution is logged here.
-- Gives full observability / debugging.
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.stage_logs (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id      UUID        NOT NULL REFERENCES public.sessions(id) ON DELETE CASCADE,
    doctor_id       UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

    stage_name      TEXT        NOT NULL,   -- e.g. "stage_1a", "rag_node", "crag_node"
    stage_input     JSONB,                  -- input passed to the node
    stage_output    JSONB,                  -- output returned by the node
    success         BOOLEAN     NOT NULL DEFAULT TRUE,
    error_message   TEXT,                   -- populated if success=false

    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    duration_ms     INTEGER                 -- computed on insert
);

CREATE INDEX idx_stage_logs_session_id ON public.stage_logs(session_id);
CREATE INDEX idx_stage_logs_doctor_id  ON public.stage_logs(doctor_id);


-- ─────────────────────────────────────────────
-- HITL LOGS
-- Every HITL pause/resume is logged here.
-- Captures what was shown and what the doctor decided.
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.hitl_logs (
    id                  UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id          UUID        NOT NULL REFERENCES public.sessions(id) ON DELETE CASCADE,
    doctor_id           UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

    hitl_number         TEXT        NOT NULL,   -- "hitl_1", "hitl_2", "hitl_3", "hitl_3b", "hitl_4"
    hitl_type           TEXT        NOT NULL,   -- "recommendation_approval", "exam_input", etc.
    displayed_data      JSONB,                  -- full interrupt payload shown to doctor
    doctor_response     JSONB,                  -- what the doctor submitted

    paused_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resumed_at          TIMESTAMPTZ
);

CREATE INDEX idx_hitl_logs_session_id ON public.hitl_logs(session_id);
CREATE INDEX idx_hitl_logs_doctor_id  ON public.hitl_logs(doctor_id);


-- ─────────────────────────────────────────────
-- CRAG ATTEMPTS
-- One row per CRAG loop attempt (up to 3).
-- Stores verdict, confidence, missing data, doctor response.
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.crag_attempts (
    id                  UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id          UUID        NOT NULL REFERENCES public.sessions(id) ON DELETE CASCADE,
    doctor_id           UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

    attempt_number      INTEGER     NOT NULL,
    verdict             TEXT        NOT NULL,   -- "confirmed", "uncertain", "incorrect"
    confidence_score    FLOAT       NOT NULL,
    retry_recommended   BOOLEAN     NOT NULL DEFAULT FALSE,

    primary_diagnosis   TEXT,
    final_diagnosis     TEXT,
    missing_data        JSONB,                  -- list of MissingDataItem dicts
    doctor_response     TEXT,                   -- doctor's answer to missing data

    supporting_evidence JSONB,
    against_evidence    JSONB,
    required_tests      JSONB,
    red_flags           JSONB,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_crag_attempts_session_id ON public.crag_attempts(session_id);


-- ─────────────────────────────────────────────
-- FINAL REPORTS
-- One row per completed pipeline run.
-- Written when HITL #4 is confirmed by the doctor.
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.final_reports (
    id                      UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id              UUID        NOT NULL REFERENCES public.sessions(id) ON DELETE CASCADE,
    patient_id              UUID        REFERENCES public.patients(id) ON DELETE SET NULL,
    doctor_id               UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

    -- CRAG final output
    verdict                 TEXT        NOT NULL,
    final_diagnosis         TEXT        NOT NULL,
    final_diagnosis_confidence FLOAT    NOT NULL,
    validated_primary_diagnosis TEXT,
    corrected_diagnosis     TEXT,
    clinical_reasoning_summary TEXT,

    -- Evidence
    supporting_evidence     JSONB,
    against_evidence        JSONB,
    required_tests          JSONB,
    red_flags               JSONB,

    -- Doctor confirmation
    doctor_confirmed        BOOLEAN     NOT NULL DEFAULT FALSE,
    doctor_final_note       TEXT,

    -- Attempt tracking
    total_crag_attempts     INTEGER     NOT NULL DEFAULT 1,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_final_reports_session_id  ON public.final_reports(session_id);
CREATE INDEX idx_final_reports_patient_id  ON public.final_reports(patient_id);
CREATE INDEX idx_final_reports_doctor_id   ON public.final_reports(doctor_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- ROW LEVEL SECURITY (RLS)
-- Every table is locked to the authenticated doctor.
-- Even direct API calls cannot cross doctor boundaries.
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE public.doctor_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.patients         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sessions         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.stage_logs       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hitl_logs        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.crag_attempts    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.final_reports    ENABLE ROW LEVEL SECURITY;


-- ── doctor_profiles ──
CREATE POLICY "doctor_profiles_own"
    ON public.doctor_profiles FOR ALL
    USING (id = auth.uid())
    WITH CHECK (id = auth.uid());

-- ── patients ──
CREATE POLICY "patients_own_doctor"
    ON public.patients FOR ALL
    USING (doctor_id = auth.uid())
    WITH CHECK (doctor_id = auth.uid());

-- ── sessions ──
CREATE POLICY "sessions_own_doctor"
    ON public.sessions FOR ALL
    USING (doctor_id = auth.uid())
    WITH CHECK (doctor_id = auth.uid());

-- ── stage_logs ──
CREATE POLICY "stage_logs_own_doctor"
    ON public.stage_logs FOR ALL
    USING (doctor_id = auth.uid())
    WITH CHECK (doctor_id = auth.uid());

-- ── hitl_logs ──
CREATE POLICY "hitl_logs_own_doctor"
    ON public.hitl_logs FOR ALL
    USING (doctor_id = auth.uid())
    WITH CHECK (doctor_id = auth.uid());

-- ── crag_attempts ──
CREATE POLICY "crag_attempts_own_doctor"
    ON public.crag_attempts FOR ALL
    USING (doctor_id = auth.uid())
    WITH CHECK (doctor_id = auth.uid());

-- ── final_reports ──
CREATE POLICY "final_reports_own_doctor"
    ON public.final_reports FOR ALL
    USING (doctor_id = auth.uid())
    WITH CHECK (doctor_id = auth.uid());


-- ─────────────────────────────────────────────────────────────────────────────
-- SERVICE ROLE BYPASS
-- Supabase service role key (used by backend) bypasses RLS.
-- This is the default Supabase behaviour — no extra config needed.
-- Your backend uses SUPABASE_SERVICE_KEY (not anon key) to write freely.
-- ─────────────────────────────────────────────────────────────────────────────

-- No explicit GRANT needed — service role inherits full access by default in Supabase.
-- Anon role has NO access (RLS blocks everything without auth.uid()).


-- ─────────────────────────────────────────────
-- AUTO-CREATE DOCTOR PROFILE ON SIGNUP
-- Trigger fires when a new user signs up via Supabase Auth.
-- Reads full_name and hospital from auth.users.raw_user_meta_data.
-- ─────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.handle_new_doctor()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.doctor_profiles (id, email, full_name, hospital)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'full_name', 'Unknown'),
        COALESCE(NEW.raw_user_meta_data->>'hospital', 'Unknown')
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_doctor();