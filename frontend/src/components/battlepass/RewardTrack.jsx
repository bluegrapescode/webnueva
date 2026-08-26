import React, { useCallback, useEffect, useRef } from "react";
import { ChevronLeft, ChevronRight, Crown } from "lucide-react";
import { useSound } from "@/context/SoundContext";
import { RewardCard, GOLD } from "@/components/battlepass/RewardCard";

const PAGE_CARDS = 5;

// The caption gets its OWN LINE above its row, never a side rail: a rail
// shares vertical space with the cards, so scrolled cards slide underneath it
// and the label prints over the art (the owner hit this twice, two designs).
// A sticky span on an otherwise-empty line has nothing to collide with.
function RowCaption({ title, tone, chip, testid }) {
  return (
    <div className="flex" data-testid={testid}>
      <div className="pointer-events-none sticky left-0 z-30 inline-flex items-center gap-2 rounded-md bg-[#0b0b0e]/95 py-0.5 pl-1 pr-3">
        <span className="label-overline text-[8px] text-white/35 sm:text-[9px]">Fila</span>
        <span
          className="font-display text-[14px] font-extrabold leading-none tracking-tight sm:text-[16px]"
          style={{ color: tone }}
        >
          {title}
        </span>
        {chip}
      </div>
    </div>
  );
}

/**
 * Both rows live in ONE horizontal scroller so the regular cell and the premium
 * cell for a level always sit in the same column. Each row's caption is a full
 * line ABOVE the row whose content sticks to the left edge while scrolling.
 */
export function RewardTrack({ regularCells, premiumCells, claimed, level, viewerTier, nameBySlug, busyKey, onClaim, apexNames }) {
  const { play } = useSound();
  const scrollerRef = useRef(null);
  const freeRowRef = useRef(null);
  const centeredRef = useRef(false);

  const strideOf = useCallback(() => {
    const row = freeRowRef.current;
    if (!row) return 118;
    const cards = row.querySelectorAll("[data-level]");
    if (cards.length > 1) return cards[1].offsetLeft - cards[0].offsetLeft;
    return 118;
  }, []);

  const scrollToLevel = useCallback((lvl, behavior) => {
    const sc = scrollerRef.current;
    const row = freeRowRef.current;
    if (!sc || !row) return;
    const card = row.querySelector(`[data-level="${lvl}"]`);
    if (!card) return;
    sc.scrollTo({ left: Math.max(0, card.offsetLeft - 12), behavior });
  }, []);

  // Land on the player's current level instead of level 1 — that is where the
  // claimable cells are. Once only: re-centring after every status refresh would
  // yank the track out from under someone browsing level 90.
  useEffect(() => {
    if (centeredRef.current) return;
    if (!regularCells.length && !premiumCells.length) return;
    centeredRef.current = true;
    scrollToLevel(Math.max(1, level), "auto");
  }, [regularCells.length, premiumCells.length, level, scrollToLevel]);

  const page = (dir) => {
    play("click");
    const sc = scrollerRef.current;
    if (!sc) return;
    sc.scrollBy({ left: dir * strideOf() * PAGE_CARDS, behavior: "smooth" });
  };

  // NOTE: no `claimed` here — the map must never ride the spread, or it
  // overwrites the per-cell boolean and every card renders "reclamado".
  const rowProps = (track) => ({
    currentLevel: level,
    viewerTier,
    nameBySlug,
    onClaim,
    track,
  });

  return (
    <div className="relative" data-testid="bp-track">
      <button
        type="button"
        onClick={() => page(-1)}
        aria-label="Ver niveles anteriores"
        data-testid="bp-track-prev"
        className="absolute -left-2 top-1/2 z-40 hidden -translate-y-1/2 items-center justify-center rounded-full border border-white/12 bg-[#101014]/95 p-2 text-foreground/80 transition-all hover:border-gold/50 hover:text-foreground sm:inline-flex"
      >
        <ChevronLeft size={18} />
      </button>
      <button
        type="button"
        onClick={() => page(1)}
        aria-label="Ver niveles siguientes"
        data-testid="bp-track-next"
        className="absolute -right-2 top-1/2 z-40 hidden -translate-y-1/2 items-center justify-center rounded-full border border-white/12 bg-[#101014]/95 p-2 text-foreground/80 transition-all hover:border-gold/50 hover:text-foreground sm:inline-flex"
      >
        <ChevronRight size={18} />
      </button>

      <div
        ref={scrollerRef}
        className="relative snap-x overflow-x-auto overflow-y-hidden rounded-2xl border border-white/8 bg-[#0b0b0e] px-2 py-4 sm:px-3"
        data-testid="bp-track-scroller"
      >
        <div className="flex w-max flex-col gap-2">
          <RowCaption
            tone="rgba(255,255,255,0.88)"
            testid="bp-row-regular-label"
            title="Regular"
            chip={(
              <span className="inline-flex w-fit items-center rounded border border-white/12 bg-white/[0.03] px-1 py-[2px] text-[8px] font-bold tracking-wide text-white/45 sm:px-1.5">
                SIN ÁPEX
              </span>
            )}
          />
          <div className="flex items-stretch gap-2" ref={freeRowRef} data-testid="bp-row-regular">
            {regularCells.map((c) => (
              <RewardCard
                key={`regular-${c.level}`}
                cell={c}
                claimed={!!claimed[`regular:${c.level}`]}
                busy={busyKey === `regular:${c.level}`}
                {...rowProps("regular")}
              />
            ))}
          </div>

          <RowCaption
            tone={GOLD}
            testid="bp-row-premium-label"
            title="Premium"
            chip={(
              <span
                className="inline-flex w-fit items-center gap-0.5 rounded border px-1 py-[2px] text-[8px] font-bold tracking-wide sm:px-1.5"
                style={{ color: GOLD, borderColor: `${GOLD}55`, background: `${GOLD}12` }}
              >
                <Crown size={8} /> CON ÁPEX
              </span>
            )}
          />
          <div className="flex items-stretch gap-2" data-testid="bp-row-premium">
            {premiumCells.map((c) => (
              <RewardCard
                key={`premium-${c.level}`}
                cell={c}
                claimed={!!claimed[`premium:${c.level}`]}
                busy={busyKey === `premium:${c.level}`}
                {...rowProps("premium")}
              />
            ))}
          </div>
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 px-1">
        <p className="text-[11px] text-muted-foreground sm:hidden" data-testid="bp-track-scrollhint">
          Desliza la fila para ver los 100 niveles.
        </p>
        {Array.isArray(apexNames) && apexNames.length > 0 && (
          <p className="inline-flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground" data-testid="bp-apex-legend">
            <Crown size={12} style={{ color: GOLD }} />
            <span>
              Ápex — {apexNames.join(", ")}: solo se eligen en la fila{" "}
              <span className="font-bold" style={{ color: GOLD }}>Premium</span>.
            </span>
          </p>
        )}
        {viewerTier === "regular" && (
          <p className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground" data-testid="bp-premium-note">
            <Crown size={12} style={{ color: GOLD }} />
            La fila Premium se desbloquea con el Pase Premium+.
          </p>
        )}
      </div>
    </div>
  );
}

export default RewardTrack;
