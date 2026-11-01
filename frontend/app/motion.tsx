"use client";

import { useEffect } from "react";

/** Lightweight scroll choreography; no animation service or paid runtime. */
export default function MotionSystem() {
  useEffect(() => {
    const root = document.documentElement;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (reduceMotion.matches) return;

    const groups = [
      ".section", ".metric", ".feature-card", ".segment-row", ".journey-heading",
      ".journey-visual", ".journey-step", ".queue-panel", ".workflow", ".workflow-step",
    ];
    const elements = groups.flatMap((selector) => Array.from(document.querySelectorAll<HTMLElement>(selector)));
    elements.forEach((element) => {
      element.dataset.reveal = "";
      if (element.matches(".metric, .segment-row, .workflow-step, .journey-step")) {
        const index = Array.from(element.parentElement?.children || []).indexOf(element);
        element.style.setProperty("--reveal-delay", `${Math.min(index, 5) * 85}ms`);
      }
    });

    root.classList.add("motion-ready");
    const revealObserver = new IntersectionObserver((entries, observer) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.1, rootMargin: "0px 0px -5% 0px" });
    elements.forEach((element) => revealObserver.observe(element));

    let frame = 0;
    const updateScroll = () => {
      frame = 0;
      const max = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
      const hero = document.querySelector<HTMLElement>(".hero");
      const heroProgress = Math.min(1, Math.max(0, window.scrollY / Math.max(1, hero?.offsetHeight || 1)));
      root.style.setProperty("--page-progress", `${(window.scrollY / max) * 100}%`);
      root.style.setProperty("--hero-lift", `${Math.round(heroProgress * -44)}px`);
      root.style.setProperty("--visual-lift", `${Math.round(heroProgress * 78)}px`);
      root.style.setProperty("--ribbon-lift", `${Math.round(heroProgress * -125)}px`);
      root.style.setProperty("--hero-progress", `${heroProgress}`);
    };
    const scheduleScroll = () => { if (!frame) frame = requestAnimationFrame(updateScroll); };
    updateScroll();
    window.addEventListener("scroll", scheduleScroll, { passive: true });
    window.addEventListener("resize", scheduleScroll);

    const pointerMove = (event: PointerEvent) => {
      const card = (event.target as HTMLElement).closest<HTMLElement>(".feature-card, .metric, .risk-graph, .journey-visual, .workflow");
      if (!card) return;
      const rect = card.getBoundingClientRect();
      card.style.setProperty("--pointer-x", `${event.clientX - rect.left}px`);
      card.style.setProperty("--pointer-y", `${event.clientY - rect.top}px`);
    };
    document.addEventListener("pointermove", pointerMove, { passive: true });

    return () => {
      revealObserver.disconnect();
      if (frame) cancelAnimationFrame(frame);
      window.removeEventListener("scroll", scheduleScroll);
      window.removeEventListener("resize", scheduleScroll);
      document.removeEventListener("pointermove", pointerMove);
      root.classList.remove("motion-ready");
    };
  }, []);
  return <div className="scroll-progress" aria-hidden="true" />;
}
