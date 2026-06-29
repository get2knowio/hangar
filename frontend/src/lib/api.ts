/* Typed API client + TanStack Query hooks. Response/request types are derived from the
   generated OpenAPI types (src/lib/api-types.ts — `npm run gen:api`), so the FE/BE
   contract stays in lockstep (Constitution VII — no hand-drifted types). */

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import type { paths } from "./api-types";

const BASE = "/api/v1";

type JSONResponse<P extends keyof paths, M extends keyof paths[P]> = paths[P][M] extends {
  responses: { 200: { content: { "application/json": infer R } } };
}
  ? R
  : never;

async function get<T>(path: string, params?: Record<string, string | boolean | undefined>): Promise<T> {
  const qs = params
    ? "?" +
      Object.entries(params)
        .filter(([, v]) => v !== undefined && v !== "")
        .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
        .join("&")
    : "";
  const res = await fetch(`${BASE}${path}${qs}`, {
    headers: { Accept: "application/json" },
    credentials: "include", // send the session cookie (OIDC mode) cross-proxy in dev
  });
  if (!res.ok) {
    const err = new Error(`GET ${path} → ${res.status}`) as Error & { status: number };
    err.status = res.status;
    throw err;
  }
  return res.json() as Promise<T>;
}

async function send<T>(method: string, path: string, body?: unknown): Promise<{ status: number; data: T }> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "include", // send the session cookie (OIDC mode)
  });
  const data = res.status === 204 ? (undefined as T) : ((await res.json().catch(() => undefined)) as T);
  // Surface server failures: a non-2xx must reject the mutation so onError (not
  // onSuccess) runs — otherwise a 4xx/5xx is silently rendered as a success toast.
  if (!res.ok) {
    const detail =
      data && typeof data === "object" && "detail" in (data as Record<string, unknown>)
        ? String((data as Record<string, unknown>).detail)
        : `${method} ${path} → ${res.status}`;
    const err = new Error(detail) as Error & { status: number; data: T };
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return { status: res.status, data };
}

// ---- Response type aliases (generated) ----
export type Overview = JSONResponse<"/fleet/overview", "get">;
export type Scorecard = JSONResponse<"/fleet/scorecard", "get">;
export type Catalog = JSONResponse<"/catalog", "get">;
export type Policy = JSONResponse<"/policy", "get">;
export type Providers = JSONResponse<"/providers", "get">;
export type ConnectionCard = NonNullable<Providers["connections"]>[number];
export type ConnectionRepos = JSONResponse<"/providers/{connection_id}/repos", "get">;
// The POST /providers request body — derived from the contract, never hand-written.
export type NewConnectionBody = NonNullable<
  paths["/providers"]["post"]["requestBody"]
>["content"]["application/json"];
export type AuditEntry = NonNullable<JSONResponse<"/providers/audit", "get">>[number];
export type RepoDetail = JSONResponse<"/repos/{connection_id}/{repo_id}", "get">;
// One check row from the repo-detail contract — derived, never hand-written (Constitution VII).
export type RepoCheck = NonNullable<
  NonNullable<RepoDetail["check_groups"]>[number]["checks"]
>[number];
export type Health = JSONResponse<"/health", "get">;
export type Me = JSONResponse<"/me", "get">;

// Derived from the generated contract — no hand-drifted types (Constitution VII).
type RemediatePath = paths["/repos/{connection_id}/{repo_id}/checks/{check_id}/remediate"]["post"];
export type RemediationKind = NonNullable<
  RemediatePath["requestBody"]
>["content"]["application/json"]["kind"];
type RemediateOk = RemediatePath["responses"][200]["content"]["application/json"];
export type RemediateResult = RemediateOk & { deep_link_url?: string };

type RemediateBatchPath = paths["/checks/{check_id}/remediate-batch"]["post"];
export type RemediateBatchResult = RemediateBatchPath["responses"][200]["content"]["application/json"];
export type BatchTarget = { connection_id: string; repo_id: string };

// ---- Auth (pre-login probe lives at /auth/info, NOT under /api/v1) ----
// Derived from the generated contract — /auth/info is documented in openapi.yaml.
export type AuthInfo = paths["/auth/info"]["get"]["responses"][200]["content"]["application/json"];

async function authInfo(): Promise<AuthInfo> {
  const res = await fetch("/auth/info", {
    headers: { Accept: "application/json" },
    credentials: "include",
  });
  if (!res.ok) throw new Error(`GET /auth/info → ${res.status}`);
  return res.json() as Promise<AuthInfo>;
}

export const useAuthInfo = () =>
  useQuery({ queryKey: ["auth-info"], queryFn: authInfo, staleTime: 0 });

export async function logout(): Promise<void> {
  await fetch("/auth/logout", { method: "POST", credentials: "include" }).catch(() => undefined);
  window.location.href = "/";
}

// ---- Query hooks ----
export const useHealth = () => useQuery({ queryKey: ["health"], queryFn: () => get<Health>("/health") });
export const useMe = () => useQuery({ queryKey: ["me"], queryFn: () => get<Me>("/me") });

export const useOverview = (connection: string) =>
  useQuery({ queryKey: ["overview", connection], queryFn: () => get<Overview>("/fleet/overview", { connection }) });

export const useScorecard = (connection: string, failingOnly: boolean) =>
  useQuery({
    queryKey: ["scorecard", connection, failingOnly],
    queryFn: () => get<Scorecard>("/fleet/scorecard", { connection, failing_only: failingOnly }),
  });

export const useCatalog = () => useQuery({ queryKey: ["catalog"], queryFn: () => get<Catalog>("/catalog") });
export const useProviders = () => useQuery({ queryKey: ["providers"], queryFn: () => get<Providers>("/providers") });
export const useAudit = () =>
  useQuery({ queryKey: ["audit"], queryFn: () => get<AuditEntry[]>("/providers/audit") });
export const useRepoDetail = (connectionId: string | undefined, repoId: string | undefined) =>
  useQuery({
    queryKey: ["repo", connectionId, repoId],
    queryFn: () => get<RepoDetail>(`/repos/${connectionId}/${repoId}`),
    enabled: !!connectionId && !!repoId,
  });

// ---- Mutations ----
export function usePolicyPatch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: { check_id: string; enabled?: boolean; params?: Record<string, unknown> }) =>
      send<Policy>("PATCH", "/policy", patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["catalog"] });
      qc.invalidateQueries({ queryKey: ["scorecard"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
    },
  });
}

export function useRemediate(connectionId: string, repoId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: { checkId: string; kind: RemediationKind }) => {
      const { status, data } = await send<RemediateResult>(
        "POST",
        `/repos/${connectionId}/${repoId}/checks/${vars.checkId}/remediate`,
        { kind: vars.kind },
      );
      return { ...data, status } as RemediateResult & { status: number };
    },
    onSuccess: () => invalidateFleet(qc, connectionId, repoId),
  });
}

export function useRemediateBatch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: { checkId: string; targets: BatchTarget[] }) =>
      (await send<RemediateBatchResult>(
        "POST", `/checks/${vars.checkId}/remediate-batch`, { targets: vars.targets },
      )).data,
    onSuccess: () => {
      // A batch touches many repos and the fleet aggregates + audit; invalidate broadly.
      qc.invalidateQueries({ queryKey: ["repo"] });
      qc.invalidateQueries({ queryKey: ["scorecard"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
      qc.invalidateQueries({ queryKey: ["audit"] });
    },
  });
}

export function useMarkMerged(connectionId: string, repoId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (checkId: string) =>
      send<RemediateResult>("POST", `/repos/${connectionId}/${repoId}/checks/${checkId}/merge`),
    onSuccess: () => invalidateFleet(qc, connectionId, repoId),
  });
}

export function useAddConnection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: NewConnectionBody) => send<ConnectionCard>("POST", "/providers", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["providers"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
      qc.invalidateQueries({ queryKey: ["scorecard"] });
    },
  });
}

// Live list of repos a connection's credential can see, plus the current allowlist. Only
// fetched when a picker is open (enabled), since it makes a real provider call.
export const useConnectionRepos = (connectionId: string | undefined, enabled: boolean) =>
  useQuery({
    queryKey: ["connection-repos", connectionId],
    queryFn: () => get<ConnectionRepos>(`/providers/${connectionId}/repos`),
    enabled: !!connectionId && enabled,
  });

export function useSetConnectionRepos(connectionId: string) {
  const qc = useQueryClient();
  return useMutation({
    // null ⇒ watch all; a list scopes the connection's fleet to exactly those repos.
    mutationFn: (repos: string[] | null) =>
      send<ConnectionCard>("PUT", `/providers/${connectionId}/repos`, { repos }),
    onSuccess: () => {
      // Changes the connection's repo set → the cards, the fleet aggregates, and the picker.
      qc.invalidateQueries({ queryKey: ["providers"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
      qc.invalidateQueries({ queryKey: ["scorecard"] });
      qc.invalidateQueries({ queryKey: ["connection-repos", connectionId] });
    },
  });
}

// Manual refresh: trigger an immediate re-interrogation (the backend runs it in the
// background, the same path as the scheduled poll, and returns 202 at once). Instead of
// guessing with a fixed timer — too short for a real provider, wastefully long for the demo
// — we poll the connection's machine-readable `last_sync_at` and resolve the moment a newer
// snapshot lands (Constitution VII: a structured field, never a parsed display string),
// keeping the mutation `pending` (so the button shows "Refreshing…") until then or the cap.
const REFRESH_POLL_INTERVAL_MS = 800;
const REFRESH_POLL_TRIES = 18; // ~14s ceiling — then refresh anyway so the UI never hangs

type ConnList = NonNullable<Providers["connections"]>;

function syncedAtOf(conns: ConnList | undefined, connectionId: string): string | null {
  return conns?.find((c) => c.id === connectionId)?.last_sync_at ?? null;
}

// A sync "landed" when the timestamp exists and is newer than the one captured before the
// trigger (ISO-8601 UTC sorts chronologically; any change means a fresh poll committed).
function advanced(before: string | null, after: string | null | undefined): boolean {
  return !!after && (!before || after > before);
}

async function pollProvidersUntil(done: (conns: ConnList) => boolean): Promise<void> {
  for (let i = 0; i < REFRESH_POLL_TRIES; i++) {
    await new Promise((r) => setTimeout(r, REFRESH_POLL_INTERVAL_MS));
    try {
      const fresh = await get<Providers>("/providers");
      if (done(fresh.connections ?? [])) return;
    } catch {
      return; // a failing poll: stop waiting and let invalidation surface the error state
    }
  }
}

function invalidateAfterSync(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ["providers"] });
  qc.invalidateQueries({ queryKey: ["overview"] });
  qc.invalidateQueries({ queryKey: ["scorecard"] });
  qc.invalidateQueries({ queryKey: ["repo"] });
  qc.invalidateQueries({ queryKey: ["audit"] });
}

export function useSyncConnection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (connectionId: string) => {
      const before = syncedAtOf(qc.getQueryData<Providers>(["providers"])?.connections, connectionId);
      await send("POST", `/providers/${connectionId}/sync`);
      await pollProvidersUntil((conns) => advanced(before, syncedAtOf(conns, connectionId)));
    },
    onSuccess: () => invalidateAfterSync(qc),
  });
}

export function useSyncFleet() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const cached = qc.getQueryData<Providers>(["providers"])?.connections ?? [];
      const before = new Map(cached.map((c) => [c.id, c.last_sync_at ?? null]));
      await send("POST", "/providers/sync");
      // Resolve once every connection that existed before the trigger has a newer snapshot
      // (or the cap is hit). A connection in backoff won't advance, so the cap bounds the
      // wait either way.
      await pollProvidersUntil((conns) =>
        conns.every((c) => advanced(before.get(c.id) ?? null, c.last_sync_at)),
      );
    },
    onSuccess: () => invalidateAfterSync(qc),
  });
}

function invalidateFleet(qc: ReturnType<typeof useQueryClient>, connectionId: string, repoId: string) {
  // A remediation changes this repo, the fleet aggregates (overview/scorecard), and the
  // audit log. It does NOT change the provider cards (repo counts / sync time), so those
  // are not invalidated.
  qc.invalidateQueries({ queryKey: ["repo", connectionId, repoId] });
  qc.invalidateQueries({ queryKey: ["scorecard"] });
  qc.invalidateQueries({ queryKey: ["overview"] });
  qc.invalidateQueries({ queryKey: ["audit"] });
}
