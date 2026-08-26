/**
 * The gifted-membership notice, mounted. A server-gifted free membership stays the
 * member's ACTIVE membership on Patreon, so Patreon bills them $0 at checkout and a
 * "purchase" never lands. The notice exists to say that out loud, only to the people
 * it is true for — every other membership state must render nothing.
 */
const React = require("react");
const ReactDOM = require("react-dom/client");
const { act } = require("react");

jest.mock("@/lib/api", () => ({
  api: {},
  externalRedirect: jest.fn(),
}));

const { GiftedMembershipNotice } = require("./PatreonTiers");
const { externalRedirect } = require("@/lib/api");

global.IS_REACT_ACT_ENVIRONMENT = true;

function mount(user) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = ReactDOM.createRoot(host);
  act(() => {
    root.render(React.createElement(GiftedMembershipNotice, { user }));
  });
  return { host, root };
}

function cleanup({ host, root }) {
  act(() => root.unmount());
  host.remove();
}

const gifted = { patreon: { linked: true, patron_status: "gifted_no_charge", tier_name: "🩷 Sub Adult" } };

afterEach(() => {
  jest.restoreAllMocks();
  externalRedirect.mockClear();
});

test("a gifted member sees the notice: the gift, the $0, and the way out", () => {
  const m = mount(gifted);
  const card = m.host.querySelector('[data-testid="patreon-gifted-notice"]');
  expect(card).not.toBeNull();
  expect(card.textContent).toContain("membresía de regalo");
  expect(card.textContent).toContain("$0");
  expect(card.textContent).toContain("cancela la membresía de regalo");
  expect(m.host.querySelector('[data-testid="patreon-gifted-open-memberships"]')).not.toBeNull();
  cleanup(m);
});

test.each([
  ["active paying patron", { patreon: { linked: true, patron_status: "active_patron", tier_name: "🔥Apex" } }],
  ["former patron", { patreon: { linked: true, patron_status: "former_patron" } }],
  ["linked, never a member", { patreon: { linked: true, patron_status: null } }],
  ["unlinked with stale gifted status", { patreon: { linked: false, patron_status: "gifted_no_charge" } }],
  ["no patreon block at all", {}],
  ["signed out", null],
  ["undefined user", undefined],
])("renders nothing for %s", (_label, user) => {
  const m = mount(user);
  expect(m.host.querySelector('[data-testid="patreon-gifted-notice"]')).toBeNull();
  cleanup(m);
});

test("the button opens Patreon memberships in a new tab and severs opener", () => {
  const fakeWin = { opener: "site" };
  const openSpy = jest.spyOn(window, "open").mockReturnValue(fakeWin);
  const m = mount(gifted);
  act(() => {
    m.host.querySelector('[data-testid="patreon-gifted-open-memberships"]').click();
  });
  expect(openSpy).toHaveBeenCalledWith("https://www.patreon.com/settings/memberships", "_blank");
  expect(fakeWin.opener).toBeNull();
  expect(externalRedirect).not.toHaveBeenCalled();
  cleanup(m);
});

test("a blocked popup falls back to a top-level navigation", () => {
  jest.spyOn(window, "open").mockReturnValue(null);
  const m = mount(gifted);
  act(() => {
    m.host.querySelector('[data-testid="patreon-gifted-open-memberships"]').click();
  });
  expect(externalRedirect).toHaveBeenCalledWith("https://www.patreon.com/settings/memberships");
  cleanup(m);
});
