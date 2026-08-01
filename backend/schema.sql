-- schema.sql
-- Run this in your Supabase SQL Editor to create the broker_connections table.

CREATE TABLE IF NOT EXISTS broker_connections (
    id SERIAL PRIMARY KEY,
    user_email VARCHAR(255) NOT NULL,
    broker_name VARCHAR(50) NOT NULL,
    access_token TEXT,
    refresh_token TEXT,
    api_key TEXT,
    api_secret TEXT,
    client_code VARCHAR(255),
    totp_key TEXT,
    expires_at VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_email, broker_name)
);

-- Enable Row Level Security (RLS) on broker_connections
ALTER TABLE broker_connections ENABLE ROW LEVEL SECURITY;

-- Create policies so users can only access their own broker credentials
CREATE POLICY "Allow select for owners" ON broker_connections
    FOR SELECT USING (auth.jwt() ->> 'email' = user_email);

CREATE POLICY "Allow insert for owners" ON broker_connections
    FOR INSERT WITH CHECK (auth.jwt() ->> 'email' = user_email);

CREATE POLICY "Allow update for owners" ON broker_connections
    FOR UPDATE USING (auth.jwt() ->> 'email' = user_email) WITH CHECK (auth.jwt() ->> 'email' = user_email);

CREATE POLICY "Allow delete for owners" ON broker_connections
    FOR DELETE USING (auth.jwt() ->> 'email' = user_email);
