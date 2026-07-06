/* Saving a repo selection must re-interrogate the connection, so a freshly-added provider's
   repo count populates now rather than after the next poll cycle — the same fix as the
   auto-refresh on Connect. Regression for "count stays 0 until manual Refresh". */

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const setReposMutate = vi.hoisted(() => vi.fn());
const syncMutate = vi.hoisted(() => vi.fn());
// Stable result reference — the real react-query hook keeps the same object across renders,
// so returning a fresh literal each call would make the modal's `[data]` effect loop forever.
const reposResult = vi.hoisted(() => ({
  data: {
    watching_all: false,
    selected: ["alpha"],
    available: [
      { name: "alpha", private: false },
      { name: "beta", private: false },
    ],
  },
  isLoading: false,
  isError: false,
}));

vi.mock("../../src/lib/api", () => ({
  useConnectionRepos: () => reposResult,
  useSetConnectionRepos: () => ({ mutate: setReposMutate, isPending: false }),
  useSyncConnection: () => ({ mutate: syncMutate, isPending: false, variables: undefined }),
  // Unused by the picker but part of the module surface the component file imports.
  useAddConnection: () => ({ mutate: vi.fn(), isPending: false }),
  useProviders: () => ({ data: { connections: [], app_registrations: [] } }),
  useRemoveConnection: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("../../src/app/state", () => ({ useToast: () => ({ show: vi.fn() }) }));

import { RepoPickerModal } from "../../src/components/ConnectionModals";

beforeEach(() => {
  setReposMutate.mockReset();
  syncMutate.mockReset();
});

describe("RepoPickerModal — auto-refresh after save", () => {
  it("syncs the connection once the selection is saved", () => {
    // Make the save resolve so its onSuccess (which triggers the sync) runs.
    setReposMutate.mockImplementation((_repos, opts) => opts?.onSuccess?.());
    render(
      <RepoPickerModal connectionId="conn-9" connectionLabel="gh:org" onClose={vi.fn()} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /save selection/i }));

    expect(setReposMutate).toHaveBeenCalledTimes(1);
    expect(syncMutate).toHaveBeenCalledWith("conn-9");
  });

  it("does not sync when the save fails", () => {
    setReposMutate.mockImplementation((_repos, opts) =>
      opts?.onError?.(new Error("nope")),
    );
    render(
      <RepoPickerModal connectionId="conn-9" connectionLabel="gh:org" onClose={vi.fn()} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /save selection/i }));

    expect(syncMutate).not.toHaveBeenCalled();
  });
});
