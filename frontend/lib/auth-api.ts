import { API_BASE, safeFetch, toApiError } from "./api";

export type AuthConfig = {
  auth_mode: "dev" | "supabase";
  supabase_url: string | null;
  supabase_anon_key: string | null;
};

export type Me = {
  tenant_id: string;
  tenant_name: string;
  email: string;
  role: "admin" | "analyst" | "viewer";
  aal: "aal1" | "aal2";
  two_factor_required: boolean;
  /** Membership department key; null = unrestricted/executive view. */
  department: string | null;
  /** Agents this account can reach; null = all agents. */
  allowed_agents: string[] | null;
  /** Frontend section keys this account can see; null = all sections. */
  allowed_sections: string[] | null;
  /** Linked org-roster person, when the login maps to someone on the org chart. */
  person: { id: string; full_name: string; title: string; department_key: string } | null;
};

export async function getAuthConfig(): Promise<AuthConfig> {
  const res = await safeFetch(`${API_BASE}/auth/config`);
  if (!res.ok) throw await toApiError(res, "load the sign-in page");
  return res.json();
}

export async function getMe(token: string): Promise<Me> {
  const res = await safeFetch(`${API_BASE}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw await toApiError(res, "load your account");
  return res.json();
}
