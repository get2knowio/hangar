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
  const res = await fetch(`${BASE}${path}${qs}`, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

async function send<T>(method: string, path: string, body?: unknown): Promise<{ status: number; data: T }> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = res.status === 204 ? (undefined as T) : ((await res.json()) as T);
  return { status: res.status, data };
}

// ---- Response type aliases (generated) ----
export type Overview = JSONResponse<"/fleet/overview", "get">;
export type Scorecard = JSONResponse<"/fleet/scorecard", "get">;
export type Catalog = JSONResponse<"/catalog", "get">;
export type Policy = JSONResponse<"/policy", "get">;
export type Providers = JSONResponse<"/providers", "get">;
export type AuditEntry = NonNullable<JSONResponse<"/providers/audit", "get">>[number];
export type RepoDetail = JSONResponse<"/repos/{repo_id}", "get">;
export type Health = JSONResponse<"/health", "get">;
export type Me = JSONResponse<"/me", "get">;

export type RemediationKind = "report" | "deep_link" | "settings_patch" | "config_pr";
export interface RemediateResult {
  state: string;
  pr_url: string | null;
  idempotent_hit: boolean;
  deep_link_url?: string;
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
export const useRepoDetail = (repoId: string | undefined) =>
  useQuery({
    queryKey: ["repo", repoId],
    queryFn: () => get<RepoDetail>(`/repos/${repoId}`),
    enabled: !!repoId,
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

export function useRemediate(repoId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: { checkId: string; kind: RemediationKind }) => {
      const { status, data } = await send<RemediateResult>(
        "POST",
        `/repos/${repoId}/checks/${vars.checkId}/remediate`,
        { kind: vars.kind },
      );
      return { ...data, status } as RemediateResult & { status: number };
    },
    onSuccess: () => invalidateFleet(qc, repoId),
  });
}

export function useMarkMerged(repoId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (checkId: string) =>
      send<RemediateResult>("POST", `/repos/${repoId}/checks/${checkId}/merge`),
    onSuccess: () => invalidateFleet(qc, repoId),
  });
}

export function useAddConnection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { provider_type: string; label: string; scope: string; credential?: string }) =>
      send("POST", "/providers", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["providers"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
      qc.invalidateQueries({ queryKey: ["scorecard"] });
    },
  });
}

function invalidateFleet(qc: ReturnType<typeof useQueryClient>, repoId: string) {
  qc.invalidateQueries({ queryKey: ["repo", repoId] });
  qc.invalidateQueries({ queryKey: ["scorecard"] });
  qc.invalidateQueries({ queryKey: ["overview"] });
  qc.invalidateQueries({ queryKey: ["audit"] });
  qc.invalidateQueries({ queryKey: ["providers"] });
}
