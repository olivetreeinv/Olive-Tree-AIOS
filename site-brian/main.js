/* Brian Norton · scroll choreography */
gsap.registerPlugin(ScrollTrigger);

const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

/* ---------- hero name: letter-by-letter track-in ---------- */
document.querySelectorAll(".hero-name .line").forEach((line, li) => {
  const word = line.dataset.word;
  for (const ch of word) {
    const s = document.createElement("span");
    s.className = "char";
    s.textContent = ch;
    line.appendChild(s);
  }
  if (!reduced) {
    gsap.from(line.querySelectorAll(".char"), {
      yPercent: 60,
      opacity: 0,
      duration: 0.9,
      ease: "power4.out",
      stagger: 0.045,
      delay: 0.25 + li * 0.28,
    });
  }
});

/* ---------- hero: scroll-scrubbed orbit ---------- */
const heroVideo = document.querySelector(".hero-video");
if (!reduced) {
  const wireScrub = () => {
    const dur = heroVideo.duration || 8;
    gsap.to(heroVideo, {
      currentTime: Math.max(dur - 0.05, 0.1),
      ease: "none",
      scrollTrigger: {
        trigger: ".hero",
        start: "top top",
        end: "bottom bottom",
        scrub: 0.4,
      },
    });
    gsap.to(".hero-content", {
      opacity: 0,
      y: -40,
      ease: "none",
      scrollTrigger: {
        trigger: ".hero",
        start: "55% bottom",
        end: "bottom bottom",
        scrub: true,
      },
    });
  };
  if (heroVideo.readyState >= 1) wireScrub();
  else heroVideo.addEventListener("loadedmetadata", wireScrub, { once: true });
} else {
  heroVideo.loop = true;
  heroVideo.autoplay = true;
  heroVideo.play().catch(() => {});
}

/* ---------- background loops: play only while on screen ---------- */
document.querySelectorAll(".pillars-video, .terms-video").forEach(v => {
  new IntersectionObserver(entries => {
    entries.forEach(e => (e.isIntersecting ? v.play().catch(() => {}) : v.pause()));
  }, { threshold: 0.1 }).observe(v);
});

/* ---------- counters ---------- */
const fmt = {
  int: n => String(Math.round(n)),
  pct: n => Math.round(n) + "%",
  x: n => n.toFixed(2) + "x",
  k: n => "$" + Math.round(n) + "K",
};
document.querySelectorAll(".num-val").forEach(el => {
  const target = parseFloat(el.dataset.count);
  const f = fmt[el.dataset.fmt];
  if (reduced) { el.textContent = f(target); return; }
  const obj = { v: 0 };
  gsap.to(obj, {
    v: target,
    duration: 1.6,
    ease: "power2.out",
    onUpdate: () => (el.textContent = f(obj.v)),
    scrollTrigger: { trigger: el, start: "top 85%", once: true },
  });
});

/* ---------- pillars: pinned, one at a time ---------- */
if (!reduced) {
  const pillars = gsap.utils.toArray(".pillar");
  const tl = gsap.timeline({
    scrollTrigger: {
      trigger: ".pillars",
      start: "top top",
      end: "bottom bottom",
      scrub: 0.3,
    },
  });
  /* each pillar owns an equal third: in (20%), hold (60%), out (20%) */
  pillars.forEach((p, i) => {
    tl.fromTo(p, { opacity: 0, y: 80 }, { opacity: 1, y: 0, duration: 0.2, ease: "none" }, i);
    if (i < pillars.length - 1) {
      tl.to(p, { opacity: 0, y: -80, duration: 0.2, ease: "none" }, i + 0.8);
    } else {
      tl.to(p, { opacity: 1, duration: 0.2, ease: "none" }, i + 0.8); // hold last to end
    }
  });
}

/* ---------- terms cards: reveal stagger ---------- */
if (!reduced) {
  gsap.from(".tcard", {
    opacity: 0,
    y: 40,
    duration: 0.7,
    ease: "power3.out",
    stagger: 0.12,
    scrollTrigger: { trigger: ".terms-cards", start: "top 80%", once: true },
  });
}

/* ---------- finale head reveal ---------- */
if (!reduced) {
  gsap.from(".finale-head span", {
    opacity: 0,
    y: 60,
    duration: 0.9,
    ease: "power4.out",
    stagger: 0.15,
    scrollTrigger: { trigger: ".finale", start: "top 70%", once: true },
  });
}
