import { useEffect, useState } from "react";

// Browsers cap live WebGL contexts (~8-16; the oldest context is silently lost
// beyond that, which would kill the MyDino live viewer or the preview modal).
// The vault grid can hold up to 10 always-animating cards, so card viewers draw
// from this shared budget: at most MAX_CARD_VIEWER_SLOTS concurrent contexts,
// FIFO by visibility. Cards without a slot render their flat image fallback and
// upgrade automatically when a slot frees (a card scrolling out of view, or
// unmounting, releases its slot).
const MAX_CARD_VIEWER_SLOTS = 6;

let activeSlots = 0;
const waitQueue = []; // FIFO of { grant } entries still waiting

function pumpQueue() {
  while (activeSlots < MAX_CARD_VIEWER_SLOTS && waitQueue.length > 0) {
    const waiter = waitQueue.shift();
    activeSlots += 1;
    waiter.grant();
  }
}

export function useViewerSlot(wanted) {
  const [granted, setGranted] = useState(false);

  useEffect(() => {
    if (!wanted) return undefined;
    let alive = true;
    let holding = false;
    const waiter = {
      grant: () => {
        if (alive) { holding = true; setGranted(true); }
        else { activeSlots -= 1; pumpQueue(); } // granted after teardown: hand it straight on
      },
    };
    waitQueue.push(waiter);
    pumpQueue();
    return () => {
      alive = false;
      if (holding) {
        activeSlots -= 1;
        setGranted(false);
        pumpQueue();
      } else {
        const idx = waitQueue.indexOf(waiter);
        if (idx >= 0) waitQueue.splice(idx, 1);
      }
    };
  }, [wanted]);

  return wanted && granted;
}

export default useViewerSlot;
