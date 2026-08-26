import React, { useMemo } from "react";
import { motion } from "framer-motion";
import { Crown } from "lucide-react";
import { buildPrimeRoute, stationHint } from "@/lib/primeRoute";

/**
 * "Ruta hacia Prime" — the prime requirements drawn as a route the dinosaur
 * walks in one life, replacing the checklist that used to hang off the bottom
 * of the vitals card.
 *
 * Every station is derived by `buildPrimeRoute`, which is total: this component
 * has no branch that can throw on a malformed payload, and it renders nothing
 * at all when the mod has published no stations yet.
 *
 * The test ids of the old panel are kept on purpose (`prime-block`,
 * `prime-status-badge`, `prime-mig`, `prime-pat`, `prime-cond-<id>`) so the
 * surface stays addressable by everything that already probes it.
 */

const ACCENT = "#E0794C";   // ruta — deliberately NOT the site's jungle green
const CURRENT = "#F0C04A";  // the station in progress

function Station({ station, index }) {
  const above = index % 2 === 1;
  const state = station.met ? "on" : station.current ? "now" : "off";
  const dotStyle = station.met
    ? { background: ACCENT, borderColor: ACCENT }
    : station.current
      ? { background: "#0b0e13", borderColor: CURRENT, boxShadow: `0 0 0 5px rgba(240,192,74,0.16)` }
      : { background: "#0b0e13", borderColor: "#313a4a" };
  const numColor = station.met ? ACCENT : station.current ? CURRENT : "#4d5566";
  const textColor = station.met ? "#d5dae3" : station.current ? "#f4e3bb" : "#78808f";

  return (
    <li
      className="absolute flex flex-col items-center"
      style={{ left: station.left, width: 132, marginLeft: -66, top: 0 }}
      data-testid={`prime-station-${station.id}`}
      data-state={state}
    >
      {/* Marker sits on the line; the caption flips above/below so ten stations
          fit at 1280 px without their labels overlapping. */}
      <div className={`absolute ${above ? "bottom-full pb-3" : "top-full pt-3"} left-0 right-0 text-center`}>
        <span className="block font-display text-[10px] font-bold tabular-nums tracking-widest" style={{ color: numColor }}>
          {String(station.id).padStart(2, "0")}
        </span>
        <span className="block text-[11px] font-semibold leading-snug mt-1.5" style={{ color: textColor }}>
          {station.short}
        </span>
        {station.kind === "counter" && (
          <span className="block text-[11px] font-bold tabular-nums mt-1" style={{ color: numColor }}>
            {station.count} / {station.cap}
          </span>
        )}
      </div>
      <span className="block rounded-full border-2" style={{ width: 22, height: 22, ...dotStyle }} />
    </li>
  );
}

function Card({ overline, title, hint, hot, testid }) {
  return (
    <div
      className="border-l-[3px] px-4 py-3.5"
      style={{
        borderColor: hot ? CURRENT : "#2b3444",
        background: hot ? "rgba(240,192,74,0.07)" : "rgba(255,255,255,0.03)",
      }}
      data-testid={testid}
    >
      <p className="label-overline text-[10px] text-muted-foreground">{overline}</p>
      <p className="text-[15px] font-semibold mt-2 leading-snug">{title}</p>
      <p className="text-xs text-muted-foreground mt-1.5">{hint}</p>
    </div>
  );
}

export function PrimeRoute({ meState }) {
  // Recomputed on the 3 s poll: ten items, no I/O, no allocation beyond the
  // returned arrays. Memoised on the two slices it actually reads so an
  // unrelated field moving does not rebuild the route.
  const route = useMemo(() => buildPrimeRoute(meState), [meState]);

  if (!route.total) return null;

  const last = route.total - 1;
  // A 132 px caption centred on the marker needs 66 px of room on each side, so
  // the stations are laid out inside a track inset by INSET px. Positions are
  // calc() rather than raw percentages: at a percentage the first and last
  // captions hang off the panel and get clipped.
  const INSET = 68;
  const at = (i) => (last === 0 ? "50%" : `calc(${INSET}px + (100% - ${INSET * 2}px) * ${(i / last).toFixed(6)})`);
  const positioned = route.stations.map((s, i) => ({
    ...s,
    current: route.current ? s.id === route.current.id : false,
    left: at(i),
  }));
  // The fill is the FRACTION completed, not "up to the furthest station
  // reached". The requirements are not sequential, so a line drawn as far as
  // the last met station would run straight through pending ones and read as
  // if they were done.
  const fillPct = route.total > 0 ? (route.doneCount / route.total) * 100 : 0;

  return (
    <motion.section
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.08 }}
      className="relative mt-4 border p-5 sm:p-7 overflow-hidden"
      style={{ background: "#0b0e13", borderColor: "rgba(224,121,76,0.22)", borderRadius: 2 }}
      data-testid="prime-block"
    >
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <p className="label-overline text-[10px] inline-flex items-center gap-1.5" style={{ color: ACCENT }}>
            <Crown size={12} /> Ruta hacia Prime
          </p>
          <h3 className="font-display font-extrabold text-2xl sm:text-3xl tracking-tight mt-2">
            {route.total} etapas en una sola vida
          </h3>
          <p className="text-sm text-muted-foreground mt-2">
            {route.isPrime
              ? "Tu dinosaurio ya es Prime. La ruta se mantiene mientras siga vivo."
              : `Tu dinosaurio ha superado ${route.doneCount} de ${route.total}.`}
          </p>
        </div>
        <span
          className="text-[11px] font-bold tracking-[0.2em] px-4 py-2.5 rounded-full border"
          style={
            route.isPrime
              ? { color: CURRENT, borderColor: "rgba(240,192,74,0.45)", background: "rgba(240,192,74,0.1)" }
              : { color: ACCENT, borderColor: "rgba(224,121,76,0.4)", background: "rgba(224,121,76,0.09)" }
          }
          data-testid="prime-status-badge"
        >
          {route.isPrime ? "PRIME ACTIVO" : `${route.doneCount} DE ${route.total} SUPERADAS`}
        </span>
      </div>

      {/* The route itself. Horizontal on desktop; the whole track scrolls
          sideways on a phone rather than crushing ten captions together, with a
          hint so the stations off-screen are not simply missed. */}
      <p className="text-[11px] text-muted-foreground mt-6 lg:hidden" data-testid="prime-route-scrollhint">
        Desliza la ruta para ver todas las etapas.
      </p>
      <div className="mt-4 lg:mt-10 overflow-x-auto overflow-y-hidden">
        <div className="relative" style={{ height: 176, minWidth: 940 }} data-testid="prime-route-track">
          <div className="absolute" style={{ left: INSET, right: INSET, top: 88, height: 2, background: "#252c39" }} />
          <div
            className="absolute"
            style={{ left: INSET, top: 88, height: 2, width: `calc((100% - ${INSET * 2}px) * ${(fillPct / 100).toFixed(4)})`, background: ACCENT }}
            data-testid="prime-route-fill"
          />
          <ul className="absolute left-0 right-0 list-none m-0 p-0" style={{ top: 88 }}>
            {positioned.map((s, i) => (
              <Station key={s.id} station={s} index={i} />
            ))}
          </ul>
        </div>
      </div>

      {/* The two counter stations keep their old ids so anything that watched
          "mig 2/2" still finds it, now as part of the route summary. */}
      <div className="sr-only">
        {positioned
          .filter((s) => s.kind === "counter")
          .map((s) => (
            <span key={s.id} data-testid={s.id === 5 ? "prime-mig" : "prime-pat"}>
              {s.label}: {s.count} / {s.cap}
            </span>
          ))}
        {positioned
          .filter((s) => s.kind !== "counter")
          .map((s) => (
            <span key={s.id} data-testid={`prime-cond-${s.id}`}>
              {s.label}: {s.met ? "Cumplido" : "Pendiente"}
            </span>
          ))}
      </div>

      <div className="grid sm:grid-cols-3 gap-3 mt-8">
        <Card
          hot
          overline="En curso ahora"
          title={route.current ? route.current.label : "Ruta completa"}
          hint={route.current ? stationHint(route.current) : "No queda ninguna etapa pendiente"}
          testid="prime-card-current"
        />
        <Card
          overline="Lo más cercano"
          title={route.next ? route.next.label : "Nada más pendiente"}
          hint={route.next ? stationHint(route.next) : "Esta es la última etapa"}
          testid="prime-card-next"
        />
        <Card
          overline="Si mueres"
          title="La ruta empieza de cero"
          hint="El avance no se hereda a la siguiente vida"
          testid="prime-card-death"
        />
      </div>
    </motion.section>
  );
}
