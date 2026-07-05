/* The Add-connection modal offers the one-click "Connect with GitHub" path: a link to the
   App-manifest start endpoint, carrying the chosen GitHub host. Guards #25's frontend entry. */

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const addMutate = vi.hoisted(() => vi.fn());
const removeMutate = vi.hoisted(() => vi.fn());
// Mutable providers payload so a test can inject an existing App registration.
const providersData = vi.hoisted(
  () => ({ current: { connections: [], app_registrations: [] } }) as {
    current: { connections: unknown[]; app_registrations: unknown[] };
  },
);

vi.mock("../../src/lib/api", () => ({
  useAddConnection: () => ({ mutate: addMutate, isPending: false }),
  useProviders: () => ({ data: providersData.current }),
  useConnectionRepos: () => ({ data: null, isLoading: false, isError: false }),
  useSetConnectionRepos: () => ({ mutate: vi.fn(), isPending: false }),
  useRemoveConnection: () => ({ mutate: removeMutate, isPending: false }),
}));
vi.mock("../../src/app/state", () => ({ useToast: () => ({ show: vi.fn() }) }));

import { AddConnectionModal, RemoveConnectionModal } from "../../src/components/ConnectionModals";

beforeEach(() => {
  addMutate.mockClear();
  removeMutate.mockReset();
  providersData.current = { connections: [], app_registrations: [] };
});

function renderModal() {
  render(<AddConnectionModal onClose={vi.fn()} onAdded={vi.fn()} />);
}

const connectLink = () => screen.queryByRole("link", { name: /connect with github/i });

describe("AddConnectionModal — Connect with GitHub", () => {
  it("links to the App-manifest start endpoint with the default github.com host", () => {
    renderModal();
    expect(connectLink()).toHaveAttribute(
      "href",
      "/api/v1/providers/github/app/new?base_url=https%3A%2F%2Fgithub.com&writable=true",
    );
  });

  it("defaults the GitHub host field to github.com", () => {
    renderModal();
    expect(screen.getByPlaceholderText("https://github.com")).toHaveValue("https://github.com");
  });

  it("carries an enterprise host into the start URL", () => {
    renderModal();
    fireEvent.change(screen.getByPlaceholderText("https://github.com"), {
      target: { value: "https://ghe.example.com" },
    });
    expect(connectLink()?.getAttribute("href")).toContain(
      "base_url=https%3A%2F%2Fghe.example.com",
    );
  });

  it("hides the GitHub-only Connect path for a Gitea connection", () => {
    renderModal();
    // First combobox is the Provider selector.
    const provider = screen.getAllByRole("combobox")[0];
    fireEvent.change(provider, { target: { value: "gitea" } });
    expect(connectLink()).toBeNull();
  });
});

describe("AddConnectionModal — App reuse notice", () => {
  it("notes an already-registered App for the host (connecting reuses it), with no forget button", () => {
    providersData.current = {
      connections: [],
      app_registrations: [{ base_url: "https://github.com", slug: "hangar-hola", app_id: "123" }],
    };
    render(<AddConnectionModal onClose={vi.fn()} onAdded={vi.fn()} />);

    expect(screen.getByText(/already registered/i)).toBeInTheDocument();
    expect(screen.getByText(/hangar-hola/)).toBeInTheDocument();
    // The old App-wide "forget" affordance is gone — teardown happens via row Remove now.
    expect(screen.queryByRole("button", { name: /forget/i })).toBeNull();
  });

  it("shows no reuse notice when no App is registered for the host", () => {
    render(<AddConnectionModal onClose={vi.fn()} onAdded={vi.fn()} />);
    expect(screen.queryByText(/already registered/i)).toBeNull();
  });
});

describe("RemoveConnectionModal", () => {
  it("deletes the connection by id on confirm", () => {
    render(
      <RemoveConnectionModal connectionId="gh-org" connectionLabel="gh:org" onClose={vi.fn()} />,
    );
    // The confirm names the connection and spells out that audit is kept.
    expect(screen.getByText(/remove “gh:org”\?/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^remove$/i }));
    expect(removeMutate).toHaveBeenCalledWith("gh-org", expect.anything());
  });

  it("surfaces the delete-App deep link when the last org of an App is removed", () => {
    // The backend reports app_forgotten + a delete link on the final row's removal.
    removeMutate.mockImplementation((_id, opts) =>
      opts?.onSuccess?.({
        org: "org",
        removed: true,
        uninstalled: true,
        app_forgotten: true,
        delete_app_url: "https://github.com/settings/apps/hangar-hola/advanced",
      }),
    );
    render(
      <RemoveConnectionModal connectionId="gh-org" connectionLabel="gh:org" onClose={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /^remove$/i }));

    const link = screen.getByRole("link", { name: /delete the app on github/i });
    expect(link).toHaveAttribute(
      "href",
      "https://github.com/settings/apps/hangar-hola/advanced",
    );
  });

  it("closes immediately when there's no GitHub step left (non-last / non-App removal)", () => {
    const onClose = vi.fn();
    removeMutate.mockImplementation((_id, opts) =>
      opts?.onSuccess?.({ org: "org", removed: true, uninstalled: true, app_forgotten: false }),
    );
    render(
      <RemoveConnectionModal connectionId="gh-org" connectionLabel="gh:org" onClose={onClose} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /^remove$/i }));
    expect(onClose).toHaveBeenCalled();
    expect(screen.queryByText(/one step left on github/i)).toBeNull();
  });

  it("closes without deleting when cancelled", () => {
    const onClose = vi.fn();
    render(
      <RemoveConnectionModal connectionId="gh-org" connectionLabel="gh:org" onClose={onClose} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(removeMutate).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });
});

describe("AddConnectionModal — Gitea", () => {
  function selectGitea() {
    render(<AddConnectionModal onClose={vi.fn()} onAdded={vi.fn()} />);
    fireEvent.change(screen.getAllByRole("combobox")[0], { target: { value: "gitea" } });
  }

  it("shows a Gitea instance URL field, defaulted empty (no github.com inherited)", () => {
    selectGitea();
    expect(screen.getByPlaceholderText("https://gitea.example.com")).toHaveValue("");
  });

  it("blocks submit until a valid instance URL is entered, then sends it as base_url", () => {
    selectGitea();
    fireEvent.change(screen.getByPlaceholderText("gh:my-org"), { target: { value: "gitea:acme" } });

    const addBtn = screen.getByRole("button", { name: /add connection/i });
    // No instance URL yet → submit is gated.
    fireEvent.click(addBtn);
    expect(addMutate).not.toHaveBeenCalled();

    fireEvent.change(screen.getByPlaceholderText("https://gitea.example.com"), {
      target: { value: "https://gitea.example.com" },
    });
    fireEvent.click(addBtn);

    expect(addMutate).toHaveBeenCalledTimes(1);
    const body = addMutate.mock.calls[0][0];
    expect(body).toMatchObject({
      provider_type: "gitea",
      base_url: "https://gitea.example.com",
      owner: "acme",
    });
  });
});
