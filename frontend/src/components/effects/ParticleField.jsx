import React, { useRef, useEffect } from "react";

// Floating ember / mist particle canvas. Lightweight, no deps.
export function ParticleField({ density = 60, color = "124, 168, 66" }) {
  const ref = useRef(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    let raf;
    let w, h;
    let particles = [];

    const resize = () => {
      w = canvas.width = canvas.offsetWidth * window.devicePixelRatio;
      h = canvas.height = canvas.offsetHeight * window.devicePixelRatio;
    };
    resize();

    const init = () => {
      particles = Array.from({ length: density }).map(() => ({
        x: Math.random() * w,
        y: Math.random() * h,
        r: Math.random() * 1.8 + 0.4,
        vy: -(Math.random() * 0.3 + 0.05) * window.devicePixelRatio,
        vx: (Math.random() - 0.5) * 0.2,
        a: Math.random() * 0.5 + 0.1,
        tw: Math.random() * Math.PI * 2,
      }));
    };
    init();

    const draw = () => {
      ctx.clearRect(0, 0, w, h);
      for (const p of particles) {
        p.y += p.vy;
        p.x += p.vx;
        p.tw += 0.02;
        if (p.y < -5) { p.y = h + 5; p.x = Math.random() * w; }
        const alpha = p.a * (0.6 + 0.4 * Math.sin(p.tw));
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${color},${alpha})`;
        ctx.shadowBlur = 8;
        ctx.shadowColor = `rgba(${color},${alpha})`;
        ctx.fill();
      }
      raf = requestAnimationFrame(draw);
    };
    draw();

    window.addEventListener("resize", resize);
    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", resize); };
  }, [density, color]);

  return <canvas ref={ref} className="absolute inset-0 w-full h-full pointer-events-none" />;
}
