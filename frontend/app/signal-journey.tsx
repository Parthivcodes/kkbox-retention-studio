"use client";

import { useEffect, useState } from "react";
import { ArrowUpRight, AudioLines, CreditCard, Radar } from "lucide-react";

const steps = [
  { number: "01", label: "LISTENING", title: "The rhythm changes.", description: "A member who listened throughout the month now visits only occasionally. The signal is a change in behaviour, not a judgment about the person.", icon: AudioLines },
  { number: "02", label: "RENEWAL", title: "The next decision approaches.", description: "Payment and renewal history add context. The system uses only records available before the prediction cutoff.", icon: CreditCard },
  { number: "03", label: "REVIEW", title: "A human sees the whole picture.", description: "A risk score, its supporting signals, and a clear uncertainty note give the team a place to start its review.", icon: Radar },
];

export default function SignalJourney() {
  const [active, setActive] = useState(0);
  useEffect(() => {
    const cards = document.querySelectorAll<HTMLElement>(".journey-step");
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting).sort((a,b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (visible) setActive(Number((visible.target as HTMLElement).dataset.step || 0));
    }, { threshold: [0.25, 0.5, 0.75], rootMargin: "-18% 0px -18% 0px" });
    cards.forEach((card) => observer.observe(card));
    return () => observer.disconnect();
  }, []);
  return <section className="journey" id="journey">
    <div className="journey-heading"><span className="section-kicker">THE SIGNAL JOURNEY / 03 SCENES</span><h2>See the story <em>unfold.</em></h2><p>Scroll through the path from a change in listening to a decision worth reviewing.</p></div>
    <div className="journey-layout">
      <div className="journey-visual" aria-label={`Scene ${active + 1}: ${steps[active].label}`}>
        <div className="journey-orbit orbit-one"/><div className="journey-orbit orbit-two"/><div className="journey-orbit orbit-three"/>
        <div className="journey-core"><div className="journey-core-icon">{active === 0 ? <AudioLines size={34}/> : active === 1 ? <CreditCard size={34}/> : <Radar size={34}/>}</div><span>MEMBER SIGNAL</span><strong>{steps[active].label}</strong></div>
        <div className={`journey-node node-one ${active === 0 ? "active" : ""}`}>01 <span>activity</span></div>
        <div className={`journey-node node-two ${active === 1 ? "active" : ""}`}>02 <span>renewal</span></div>
        <div className={`journey-node node-three ${active === 2 ? "active" : ""}`}>03 <span>review</span></div>
        <div className="journey-visual-bottom"><span>INSIGHT SEQUENCE</span><span>0{active + 1} / 03</span></div>
      </div>
      <div className="journey-steps">{steps.map((step, index) => <article className={`journey-step ${index === active ? "current" : ""}`} data-step={index} key={step.number}><div className="journey-step-kicker"><span>{step.number} / {step.label}</span><step.icon size={18}/></div><h3>{step.title}</h3><p>{step.description}</p><div className="journey-step-foot"><span>{index === active ? "IN FOCUS" : "SCROLL TO EXPLORE"}</span><ArrowUpRight size={16}/></div></article>)}</div>
    </div>
  </section>;
}
