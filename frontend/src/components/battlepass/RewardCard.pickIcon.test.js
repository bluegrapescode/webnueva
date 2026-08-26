/**
 * The REAL RewardCard, mounted, for the cells the owner pointed at: level 50 on
 * both rows. The helper test next door proves the slug table; this proves the
 * card actually paints a dinosaur there instead of the crown badge, which is
 * the only thing a player can see.
 */
const React = require("react");
const ReactDOM = require("react-dom/client");
const { act } = require("react");
const { RewardCard } = require("./RewardCard");

global.IS_REACT_ACT_ENVIRONMENT = true;

function mount(cell, track = "regular") {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = ReactDOM.createRoot(host);
  act(() => {
    root.render(
      React.createElement(RewardCard, {
        cell,
        track,
        currentLevel: 100,
        claimed: false,
        viewerTier: "premium_plus",
        nameBySlug: { trex: "Tyrannosaurus", trike: "Triceratops" },
        busy: false,
        onClaim: () => {},
      })
    );
  });
  const el = host.querySelector(`[data-testid="bp-reward-${track}-${cell.level}"]`);
  const img = el.querySelector("img");
  const out = {
    text: el.textContent,
    imgSrc: img ? img.getAttribute("src") : null,
    svgCount: el.querySelectorAll("svg").length,
  };
  act(() => root.unmount());
  host.remove();
  return out;
}

beforeEach(() => { document.body.innerHTML = ""; });

test("the regular row's level-50 pick paints its band's dinosaur", () => {
  const r = mount({ level: 50, type: "dino", band: "mid" }, "regular");
  expect(r.imgSrc).toBe("/dinos/carno.png");
  expect(r.text).toContain("ELIGE DINO");
  expect(r.text).toContain("Medio");
});

test("the premium row's level-50 pick paints a dinosaur too", () => {
  const r = mount({ level: 50, type: "dino", band: "all" }, "premium");
  expect(r.imgSrc).toBe("/dinos/trike.png");
  expect(r.text).toContain("ELIGE DINO");
  expect(r.text).toContain("Todas + Ápex");
});

test("the fixed level-100 cell is untouched - still its own species", () => {
  const r = mount({ level: 100, type: "dino", band: "apex", slug: "trex" }, "premium");
  expect(r.imgSrc).toBe("/dinos/trex.png");
  expect(r.text).toContain("Tyrannosaurus");
});

test("cells that are not dinos keep their own picture", () => {
  expect(mount({ level: 49, type: "coins", amount: 16210 }).imgSrc).toBe("/coins/meat.png");
  expect(mount({ level: 20, type: "token", token: "diet" }).imgSrc).toBe("/tokens/diet.png");
  expect(mount({ level: 30, type: "amber", amount: 40 }).imgSrc).toBe("/coins/amber.png");
});

test("an empty cell paints nothing and says so", () => {
  const r = mount({ level: 35, type: "empty" });
  expect(r.imgSrc).toBeNull();
  expect(r.text).toContain("Sin recompensa");
});
