/* The Add-connection modal offers the one-click "Connect with GitHub" path: a link to the
   App-manifest start endpoint, carrying the chosen GitHub host. Guards #25's frontend entry. */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../src/lib/api", () => ({
  useAddConnection: () => ({ mutate: vi.fn(), isPending: false }),
  useProviders: () => ({ data: { connections: [] } }),
  useConnectionRepos: () => ({ data: null, isLoading: false, isError: false }),
  useSetConnectionRepos: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("../../src/app/state", () => ({ useToast: () => ({ show: vi.fn() }) }));

import { AddConnectionModal } from "../../src/components/ConnectionModals";

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
