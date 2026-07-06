/* Landing back on /providers after "Connect with GitHub" (?connected=<id>) must immediately
   interrogate the just-added connection, so its repo count populates now instead of reading
   "0 repos" until the background poller's next cycle. Regression for the reported bug where
   the count stayed zero until the operator manually hit Refresh on the connection. */

import { render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const syncMutate = vi.hoisted(() => vi.fn());
const refetch = vi.hoisted(() => vi.fn());

vi.mock("../../src/lib/api", () => ({
  useProviders: () => ({
    data: { access: { mode: "disabled" }, connections: [], app_registrations: [] },
    isLoading: false,
    isError: false,
    refetch,
  }),
  useAudit: () => ({ data: [] }),
  useSyncConnection: () => ({ mutate: syncMutate, isPending: false, variables: undefined }),
  // Only pulled in via the modal components' module import (they aren't rendered here).
  useAddConnection: () => ({ mutate: vi.fn(), isPending: false }),
  useConnectionRepos: () => ({ data: null, isLoading: false, isError: false }),
  useSetConnectionRepos: () => ({ mutate: vi.fn(), isPending: false }),
  useRemoveConnection: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("../../src/app/state", () => ({ useToast: () => ({ show: vi.fn() }) }));

import { Providers } from "../../src/screens/Providers";

beforeEach(() => {
  syncMutate.mockClear();
  refetch.mockClear();
});

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Providers />
    </MemoryRouter>,
  );
}

describe("Providers — auto-refresh after connect", () => {
  it("interrogates the new connection on ?connected so its repo count populates", async () => {
    renderAt("/providers?connected=conn-123");
    await waitFor(() =>
      expect(syncMutate).toHaveBeenCalledWith("conn-123", expect.anything()),
    );
  });

  it("does not auto-sync on a normal load (no ?connected)", async () => {
    renderAt("/providers");
    await new Promise((r) => setTimeout(r, 0)); // let the effect run
    expect(syncMutate).not.toHaveBeenCalled();
  });

  it("does not auto-sync when the connect flow failed (?connect_error)", async () => {
    renderAt("/providers?connect_error=state_mismatch");
    await new Promise((r) => setTimeout(r, 0));
    expect(syncMutate).not.toHaveBeenCalled();
  });
});
