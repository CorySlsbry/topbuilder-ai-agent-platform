"use client";

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

// This app is a fully client-side SPA, so a plain browser client is correct
// (no @supabase/ssr). One instance per (url, anonKey) pair.
let cache: { key: string; client: SupabaseClient } | null = null;

export function getSupabase(url: string, anonKey: string): SupabaseClient {
  const key = `${url}|${anonKey}`;
  if (cache?.key !== key) cache = { key, client: createClient(url, anonKey) };
  return cache.client;
}

/** The client from the most recent getSupabase() call — null before real auth has been configured. */
export function activeSupabase(): SupabaseClient | null {
  return cache?.client ?? null;
}
