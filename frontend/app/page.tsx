"use client";

import { useEffect, useRef, useState } from "react";

export default function Home() {
  const container = useRef<HTMLDivElement>(null);
  const [stats, setStats] = useState({ val1: 0, val2: 0, val3: 0 });

  /* ── Ping render backend to wake it up ── */
  useEffect(() => {
    fetch("https://blue-n2sh.onrender.com/").catch(() => {
      // Ignore errors (e.g. CORS), we just want to wake it up
    });
  }, []);

  /* ── Nav scroll behaviour ── */
  useEffect(() => {
    const handleScroll = () => {
      const nav = document.querySelector(".main-nav");
      if (nav) {
        if (window.scrollY > 50) {
          nav.classList.add("scrolled");
        } else {
          nav.classList.remove("scrolled");
        }
      }
    };
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  /* ── GSAP animations ── */
  useEffect(() => {
    let ctx: any;
    let fallbackTimeout: NodeJS.Timeout;

    const initGSAP = () => {
      const gsap = (window as any).gsap;
      const ScrollTrigger = (window as any).ScrollTrigger;

      if (!gsap || !ScrollTrigger) {
        fallbackTimeout = setTimeout(initGSAP, 100);
        return;
      }

      gsap.registerPlugin(ScrollTrigger);

      if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        ctx = gsap.context(() => {

          /* ── Hero reveal driven by video ── */
          const video = document.getElementById("heroVideo") as HTMLVideoElement;
          if (video) {
            let labelDone = false, blueDone = false, ruleDone = false, subDone = false, ctaDone = false, scrollDone = false;

            const triggerReveal = (pct: number) => {
              if (pct >= 0.50 && !labelDone) { labelDone = true; gsap.to(".hero-label", { opacity: 1, duration: 0.8, ease: "power2.out" }); }
              if (pct >= 0.65 && !blueDone) { blueDone = true; gsap.to(".hero-blue", { opacity: 1, clipPath: "inset(0 0% 0 0)", duration: 1.2, ease: "power3.out" }); }
              if (pct >= 0.78 && !ruleDone) { ruleDone = true; gsap.to(".hero-rule", { opacity: 1, duration: 0.8, ease: "power2.out" }); }
              if (pct >= 0.85 && !subDone) { subDone = true; gsap.to(".hero-subline", { opacity: 1, y: 0, duration: 0.8, ease: "power2.out" }); }
              if (pct >= 0.93 && !ctaDone) { ctaDone = true; gsap.set(".hero-cta-btn", { y: 20 }); gsap.to(".hero-cta-btn", { opacity: 1, y: 0, duration: 0.8, ease: "power2.out", stagger: 0.1 }); }
              if (pct >= 0.99 && !scrollDone) { scrollDone = true; gsap.to(".hero-scroll", { opacity: 1, duration: 1 }); }
            };

            const onTimeUpdate = () => {
              if (!video.duration) return;
              triggerReveal(video.currentTime / video.duration);
            };

            const onEnded = () => {
              video.pause();
              triggerReveal(1.0);
            };

            video.addEventListener("timeupdate", onTimeUpdate);
            video.addEventListener("ended", onEnded);

            const fallback = () => {
              if (!labelDone) {
                labelDone = blueDone = ruleDone = subDone = ctaDone = scrollDone = true;
                gsap.to(".hero-label", { opacity: 1, duration: 0.8, ease: "power2.out" });
                gsap.to(".hero-blue", { opacity: 1, clipPath: "inset(0 0% 0 0)", duration: 1.2, ease: "power3.out", delay: 0.2 });
                gsap.to(".hero-rule", { opacity: 1, duration: 0.8, ease: "power2.out", delay: 0.4 });
                gsap.to(".hero-subline", { opacity: 1, y: 0, duration: 0.8, ease: "power2.out", delay: 0.6 });
                gsap.set(".hero-cta-btn", { y: 20 });
                gsap.to(".hero-cta-btn", { opacity: 1, y: 0, duration: 0.8, ease: "power2.out", stagger: 0.1, delay: 0.8 });
                gsap.to(".hero-scroll", { opacity: 1, duration: 1, delay: 1.2 });
              }
            };
            video.addEventListener("error", fallback);
            setTimeout(() => { if (!labelDone) fallback(); }, 2000);
          }

          /* ── Scroll animations using .anim-reveal class ──
               Strategy: elements start with CSS class `anim-reveal` (opacity:0, translateY:30px).
               GSAP adds `.is-visible` class on scroll trigger, which CSS transitions to opacity:1.
               This is more robust than gsap.from() which can leave elements stuck at opacity:0.
          */
          const revealSections = [
            { trigger: ".problem-section", selector: ".problem-section .anim-reveal" },
            { trigger: ".product-section", selector: ".product-section .anim-reveal" },
            { trigger: ".usecase-section", selector: ".usecase-section .anim-reveal" },
            { trigger: ".how-section", selector: ".how-section .anim-reveal" },
            { trigger: ".trust-section", selector: ".trust-section .anim-reveal" },
            { trigger: ".cta-section", selector: ".cta-section .anim-reveal" },
          ];

          revealSections.forEach(({ trigger, selector }) => {
            ScrollTrigger.create({
              trigger,
              start: "top 82%",
              onEnter: () => {
                const els = document.querySelectorAll(selector);
                els.forEach((el, i) => {
                  setTimeout(() => {
                    (el as HTMLElement).style.transitionDelay = `${i * 0.1}s`;
                    el.classList.add("is-visible");
                  }, 20);
                });
              },
              once: true,
            });
          });

          // Stat counter animation
          ScrollTrigger.create({
            trigger: ".problem-stats",
            start: "top 85%",
            onEnter: () => {
              const targets = { v1: 0, v2: 0, v3: 0 };
              gsap.to(targets, {
                v1: 2, v2: 70, v3: 40,
                duration: 2.4, ease: "power2.out",
                onUpdate: () => setStats({
                  val1: Math.floor(targets.v1),
                  val2: Math.floor(targets.v2),
                  val3: Math.floor(targets.v3)
                })
              });
            },
            once: true
          });

        }, container);
      } else {
        // Reduced motion: show everything immediately
        setStats({ val1: 2, val2: 70, val3: 40 });
        document.querySelectorAll(".anim-reveal").forEach(el => {
          el.classList.add("is-visible");
        });
      }
    };

    // Fallback: if GSAP never loads, show everything after 4 seconds
    const safetyNet = setTimeout(() => {
      document.querySelectorAll(".anim-reveal").forEach(el => {
        el.classList.add("is-visible");
      });
      setStats(prev => prev.val1 === 0 ? { val1: 2, val2: 70, val3: 40 } : prev);
    }, 4000);

    initGSAP();

    return () => {
      clearTimeout(fallbackTimeout);
      clearTimeout(safetyNet);
      if (ctx) ctx.revert();
    };
  }, []);

  return (
    <main ref={container}>

      {/* ═══════════════════════════════════════════════════════
          NAVIGATION
          ═══════════════════════════════════════════════════════ */}
      <nav className="main-nav">
        <div className="nav-brand">BLUE</div>
        <a href="https://blue-n2sh.onrender.com/" className="nav-link">Explore BLUE &rarr;</a>
        <div className="hamburger">
          <span></span><span></span><span></span>
        </div>
      </nav>

      {/* ═══════════════════════════════════════════════════════
          HERO — Video (unchanged)
          ═══════════════════════════════════════════════════════ */}
      <section className="hero">
        <video id="heroVideo" autoPlay muted playsInline style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', zIndex: 0 }}>
          <source src="/video.mp4" type="video/mp4" />
        </video>

        <div className="hero-overlay-radial"></div>
        <div className="hero-overlay-gradient"></div>

        <div className="hero-content">
          <div className="hero-label">WATER QUALITY INDEXING SYSTEM</div>
          <h1 className="hero-blue">BLUE</h1>
          <div className="hero-rule"></div>
          <p className="hero-subline">Analyse water across every standard. Instantly.</p>

          <div className="hero-cta-container">
            <a href="https://blue-n2sh.onrender.com/" className="hero-cta-btn hero-cta-primary">Explore BLUE &rarr;</a>
            <a href="#how" className="hero-cta-btn hero-cta-ghost">How it works</a>
          </div>

          <div className="hero-scroll">
            <div style={{ width: '1px', height: '48px', background: 'var(--text-muted)', marginBottom: '8px' }}></div>
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', letterSpacing: '0.15em' }}>scroll</span>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════
          1. PROBLEM STATEMENT — "Why it matters"
          ═══════════════════════════════════════════════════════ */}
      <section className="section-wrapper problem-section" id="problem">
        {/* Animated water ripple SVG texture */}
        <svg className="ripple-bg" viewBox="0 0 1440 600" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <pattern id="ripplePattern" x="0" y="0" width="120" height="120" patternUnits="userSpaceOnUse">
              <circle cx="60" cy="60" r="1" fill="none" stroke="rgba(0,212,255,0.3)" strokeWidth="0.5">
                <animate attributeName="r" from="5" to="55" dur="4s" repeatCount="indefinite" />
                <animate attributeName="opacity" from="0.6" to="0" dur="4s" repeatCount="indefinite" />
              </circle>
              <circle cx="60" cy="60" r="1" fill="none" stroke="rgba(0,212,255,0.2)" strokeWidth="0.5">
                <animate attributeName="r" from="5" to="55" dur="4s" begin="1.5s" repeatCount="indefinite" />
                <animate attributeName="opacity" from="0.4" to="0" dur="4s" begin="1.5s" repeatCount="indefinite" />
              </circle>
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#ripplePattern)" />
        </svg>

        <div className="section-container" style={{ position: 'relative', zIndex: 1 }}>
          <div className="anim-reveal">
            <span className="section-label">Why it matters</span>
          </div>

          <h2 className="anim-reveal" style={{ marginTop: '24px', maxWidth: '600px' }}>
            Water isn&apos;t just a resource. <br />
            <span style={{ color: 'var(--accent)' }}>It&apos;s survival.</span>
          </h2>

          {/* 3 glowing stat numbers */}
          <div className="problem-stats">
            <div className="problem-stat-card anim-reveal">
              <div className="stat-number">{stats.val1}B+</div>
              <p className="stat-line-desc">people globally lack access to safely managed drinking water</p>
            </div>
            <div className="problem-stat-card anim-reveal">
              <div className="stat-number">{stats.val2}%</div>
              <p className="stat-line-desc">of diseases in the developing world are linked to unsafe water</p>
            </div>
            <div className="problem-stat-card anim-reveal">
              <div className="stat-number">{stats.val3}%</div>
              <p className="stat-line-desc">of global food production depends on irrigation water quality</p>
            </div>
          </div>

          {/* 3 context lines */}
          <div className="stat-context-lines anim-reveal">
            <div className="context-line">
              <span className="dot"></span>
              <span>Drinking water contamination kills more than all forms of violence — including war.</span>
            </div>
            <div className="context-line">
              <span className="dot"></span>
              <span>Crops irrigated with unsafe water carry heavy metals into the food chain.</span>
            </div>
            <div className="context-line">
              <span className="dot"></span>
              <span>Industrial effluent without quality monitoring poisons rivers irreversibly.</span>
            </div>
          </div>
        </div>
      </section>

      <hr className="section-divider" />

      {/* ═══════════════════════════════════════════════════════
          2. WHAT IS BLUE? — Product Intro
          ═══════════════════════════════════════════════════════ */}
      <section className="section-wrapper product-section" id="product">
        <div className="section-container text-center">
          <span className="section-label anim-reveal" style={{ justifyContent: 'center' }}>What is BLUE</span>

          <h2 className="product-hero-tagline anim-reveal" style={{ marginTop: '24px' }}>
            One engine. Every standard.<br />
            <span style={{ color: 'var(--accent)' }}>Total clarity.</span>
          </h2>

          <div className="grid-row grid-3">
            {/* Card 1 */}
            <div className="frost-card anim-reveal text-center">
              <svg className="capability-icon" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" style={{ margin: '0 auto 20px' }}>
                <path d="M12 2L2 7l10 5 10-5-10-5z" />
                <path d="M2 17l10 5 10-5" />
                <path d="M2 12l10 5 10-5" />
              </svg>
              <div className="capability-title">Multi-use WQI Analysis</div>
              <p className="capability-desc">Assess water quality across drinking, irrigation, and industrial use from a single input set.</p>
            </div>

            {/* Card 2 */}
            <div className="frost-card anim-reveal text-center">
              <svg className="capability-icon" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" style={{ margin: '0 auto 20px' }}>
                <circle cx="12" cy="12" r="10" />
                <path d="M12 6v6l4 2" />
              </svg>
              <div className="capability-title">Profile-Driven Scoring</div>
              <p className="capability-desc">Each use-case profile applies its own gates, thresholds, and weighted sub-indices automatically.</p>
            </div>

            {/* Card 3 */}
            <div className="frost-card anim-reveal text-center">
              <svg className="capability-icon" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" style={{ margin: '0 auto 20px' }}>
                <path d="M9 12l2 2 4-4" />
                <path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div className="capability-title">Standards-Compliant Engine</div>
              <p className="capability-desc">Built against BIS IS:10500, WHO 4th Edition, and FAO Ayers &amp; Westcot guidelines.</p>
            </div>
          </div>
        </div>
      </section>

      <hr className="section-divider" />

      {/* ═══════════════════════════════════════════════════════
          3. USE CASES — Who it's for
          ═══════════════════════════════════════════════════════ */}
      <section className="section-wrapper usecase-section" id="usecases">
        <div className="section-container">
          <span className="section-label anim-reveal">Who it&apos;s for</span>
          <h2 className="anim-reveal" style={{ marginTop: '24px', marginBottom: '48px' }}>
            Built for every context.
          </h2>

          <div className="grid-row grid-2x2">
            {/* Drinking Water */}
            <div className="frost-card anim-reveal">
              <svg className="usecase-icon" viewBox="0 0 24 24">
                <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z" />
              </svg>
              <h3 style={{ marginBottom: '4px' }}>Drinking Water</h3>
              <p className="usecase-framing">Safe for human consumption</p>
              <ul className="usecase-bullets">
                <li>BIS IS:10500 &amp; WHO compliance checks</li>
                <li>Hard gates on toxic contaminants</li>
                <li>Potability classification output</li>
              </ul>
            </div>

            {/* Agriculture */}
            <div className="frost-card anim-reveal">
              <svg className="usecase-icon" viewBox="0 0 24 24">
                <path d="M11 20A7 7 0 0 1 4 13V4a7 7 0 0 1 7 7 7 7 0 0 1 7-7v9a7 7 0 0 1-7 7z" />
              </svg>
              <h3 style={{ marginBottom: '4px' }}>Agriculture</h3>
              <p className="usecase-framing">Irrigation &amp; livestock readiness</p>
              <ul className="usecase-bullets">
                <li>FAO Ayers &amp; Westcot guidelines</li>
                <li>SAR and salinity hazard scoring</li>
                <li>Crop sensitivity categorisation</li>
              </ul>
            </div>

            {/* Industrial */}
            <div className="frost-card anim-reveal">
              <svg className="usecase-icon" viewBox="0 0 24 24">
                <path d="M2 20h20" />
                <path d="M5 20V8l5 4V4l4 4h4v12" />
                <path d="M9 20v-4h2v4" />
                <path d="M14 20v-2h2v2" />
              </svg>
              <h3 style={{ marginBottom: '4px' }}>Industrial</h3>
              <p className="usecase-framing">Process water &amp; effluent quality</p>
              <ul className="usecase-bullets">
                <li>Cooling and boiler feed-water limits</li>
                <li>Effluent discharge compliance</li>
                <li>Corrosion &amp; scaling risk flags</li>
              </ul>
            </div>

            {/* Aquaculture */}
            <div className="frost-card anim-reveal">
              <svg className="usecase-icon" viewBox="0 0 24 24">
                <path d="M2 16s3-4 6-4 5 6 8 6 6-6 6-6" />
                <path d="M2 10s3-4 6-4 5 6 8 6 6-6 6-6" />
              </svg>
              <h3 style={{ marginBottom: '4px' }}>Aquaculture</h3>
              <p className="usecase-framing">Optimal aquatic environments</p>
              <ul className="usecase-bullets">
                <li>DO, ammonia, and pH band checks</li>
                <li>Species-specific tolerance ranges</li>
                <li>Pond health scoring</li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      <hr className="section-divider" />

      {/* ═══════════════════════════════════════════════════════
          4. HOW IT WORKS — 3-step flow
          ═══════════════════════════════════════════════════════ */}
      <section className="section-wrapper how-section" id="how">
        <div className="section-container text-center">
          <span className="section-label anim-reveal" style={{ justifyContent: 'center' }}>How it works</span>
          <h2 className="anim-reveal" style={{ marginTop: '24px', marginBottom: '64px' }}>
            Three steps. Five seconds.
          </h2>

          <div className="stepper-wrapper">
            {/* Step 1 */}
            <div className="stepper-step anim-reveal">
              <div className="stepper-circle">
                <svg viewBox="0 0 24 24">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                  <polyline points="10 9 9 9 8 9" />
                </svg>
              </div>
              <div className="stepper-card">
                <div className="stepper-title">Input Parameters</div>
                <p className="stepper-desc">Enter your raw water readings — pH, TDS, nitrate, hardness, and more.</p>
              </div>
            </div>

            {/* Connector */}
            <div className="stepper-connector anim-reveal">
              <svg width="80" height="20" viewBox="0 0 80 20">
                <line className="connector-line" x1="0" y1="10" x2="80" y2="10" />
                <polygon points="74,5 80,10 74,15" fill="var(--accent)" opacity="0.7" />
              </svg>
            </div>

            {/* Step 2 */}
            <div className="stepper-step anim-reveal">
              <div className="stepper-circle">
                <svg viewBox="0 0 24 24">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
                  <line x1="12" y1="17" x2="12.01" y2="17" />
                </svg>
              </div>
              <div className="stepper-card">
                <div className="stepper-title">Engine Scores</div>
                <p className="stepper-desc">The engine routes through compliance gates, weighting, and multi-profile scoring.</p>
              </div>
            </div>

            {/* Connector */}
            <div className="stepper-connector anim-reveal">
              <svg width="80" height="20" viewBox="0 0 80 20">
                <line className="connector-line" x1="0" y1="10" x2="80" y2="10" />
                <polygon points="74,5 80,10 74,15" fill="var(--accent)" opacity="0.7" />
              </svg>
            </div>

            {/* Step 3 */}
            <div className="stepper-step anim-reveal">
              <div className="stepper-circle">
                <svg viewBox="0 0 24 24">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                  <polyline points="22 4 12 14.01 9 11.01" />
                </svg>
              </div>
              <div className="stepper-card">
                <div className="stepper-title">Actionable Result</div>
                <p className="stepper-desc">Get a clear WQI score with zone classification, flags, and next‑step guidance.</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <hr className="section-divider" />

      {/* ═══════════════════════════════════════════════════════
          5. TRUST & STANDARDS — Credibility
          ═══════════════════════════════════════════════════════ */}
      <section className="section-wrapper trust-section" id="trust">
        <div className="section-container text-center">
          <span className="section-label anim-reveal" style={{ justifyContent: 'center' }}>Trust &amp; Standards</span>
          <h2 className="anim-reveal" style={{ marginTop: '24px', marginBottom: '48px' }}>
            Built on global standards.
          </h2>

          {/* Glowing pill badges */}
          <div className="standards-pills anim-reveal">
            <span className="glow-pill">
              <strong>BIS</strong> IS:10500:2012
            </span>
            <span className="glow-pill">
              <strong>WHO</strong> 4th Edition
            </span>
            <span className="glow-pill">
              <strong>FAO</strong> Ayers &amp; Westcot
            </span>
          </div>

          {/* Terminal-style sample output */}
          <div className="terminal-card anim-reveal">
            <div className="terminal-header">
              <span className="terminal-dot r"></span>
              <span className="terminal-dot y"></span>
              <span className="terminal-dot g"></span>
              <span className="terminal-title">BLUE Engine — Sample Output</span>
            </div>
            <div className="terminal-body">
              <div className="terminal-row">
                <span className="term-label">Profile</span>
                <span className="term-value">BIS Drinking Water</span>
              </div>
              <div className="terminal-row">
                <span className="term-label">pH</span>
                <span className="term-value">7.2</span>
              </div>
              <div className="terminal-row">
                <span className="term-label">TDS</span>
                <span className="term-value">340 mg/L</span>
              </div>
              <div className="terminal-row">
                <span className="term-label">NO₃</span>
                <span className="term-value">28 mg/L</span>
              </div>
              <div className="terminal-row">
                <span className="term-label">Hardness</span>
                <span className="term-value">180 mg/L</span>
              </div>
              <div className="terminal-row">
                <span className="term-label">Turbidity</span>
                <span className="term-value">2.1 NTU</span>
              </div>
              <div className="terminal-row" style={{ borderBottom: 'none', paddingTop: '12px' }}>
                <span className="term-label">WQI Score</span>
                <span className="wqi-score-pill good">74.3 — Good</span>
              </div>
            </div>
            <div className="terminal-disclaimer">
              Sample output — illustrative only
            </div>
          </div>
        </div>
      </section>

      <hr className="section-divider" />

      {/* ═══════════════════════════════════════════════════════
          6. CTA — Redirect to BLUE
          ═══════════════════════════════════════════════════════ */}
      <section className="cta-section section-wrapper" id="cta">
        {/* Radial bloom */}
        <div className="cta-bloom"></div>

        <div className="section-container text-center" style={{ position: 'relative', zIndex: 2 }}>
          <h2 className="cta-headline anim-reveal">
            Your water. Analyzed.<br />
            <span style={{ color: 'var(--accent)' }}>Understood.</span>
          </h2>
          <a href="https://blue-n2sh.onrender.com/" className="cta-btn anim-reveal">
            Go to BLUE &rarr;
          </a>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════
          FOOTER
          ═══════════════════════════════════════════════════════ */}
      <footer className="site-footer">
        <div className="footer-brand">BLUE</div>
        <div className="footer-copy">&copy; 2026 Project BLUE</div>
      </footer>
    </main>
  );
}
