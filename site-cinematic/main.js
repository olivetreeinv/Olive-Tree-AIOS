/* Olive Tree Investments · scroll choreography */
gsap.registerPlugin(ScrollTrigger);

const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
const finePointer = matchMedia("(pointer: fine)").matches;

/* ---------- gold cursor: dot + trailing ring ---------- */
if (finePointer && !reduced) {
  document.body.classList.add("cursor-on");
  const dot = document.querySelector(".cursor-dot");
  const ring = document.querySelector(".cursor-ring");
  let mx = innerWidth / 2, my = innerHeight / 2, rx = mx, ry = my;
  addEventListener("pointermove", e => { mx = e.clientX; my = e.clientY; }, { passive: true });
  gsap.ticker.add(() => {
    rx += (mx - rx) * 0.16;
    ry += (my - ry) * 0.16;
    dot.style.transform = `translate(${mx - 4}px, ${my - 4}px)`;
    ring.style.transform = `translate(${rx - 17}px, ${ry - 17}px)`;
  });
  document.querySelectorAll("a").forEach(el => {
    el.addEventListener("pointerenter", () => document.body.classList.add("cursor-hover"));
    el.addEventListener("pointerleave", () => document.body.classList.remove("cursor-hover"));
  });
}

/* ---------- hero: scroll-scrubbed ink bloom ---------- */
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
    /* title recedes as ink takes over */
    gsap.to(".hero-content", {
      opacity: 0,
      scale: 0.94,
      ease: "none",
      scrollTrigger: {
        trigger: ".hero",
        start: "60% bottom",
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

/* ---------- manifesto line types itself ---------- */
{
  const holder = document.querySelector(".hero-manifesto");
  const target = holder.querySelector(".typed");
  const [plain, gold] = holder.dataset.line.split("|"); // gold segment = 3rd gold use
  if (reduced) {
    target.innerHTML = `${plain}<span class="gold-phrase">${gold}</span>`;
  } else {
    const spans = [];
    for (const ch of plain) spans.push({ ch, gold: false });
    for (const ch of gold) spans.push({ ch, gold: true });
    let i = 0;
    const goldSpan = document.createElement("span");
    goldSpan.className = "gold-phrase";
    const tick = () => {
      if (i >= spans.length) return;
      const s = spans[i++];
      if (s.gold) {
        if (!goldSpan.parentNode) target.appendChild(goldSpan);
        goldSpan.textContent += s.ch;
      } else {
        target.append(s.ch);
      }
      setTimeout(tick, 42 + Math.random() * 40);
    };
    setTimeout(tick, 900);
  }
}

/* ---------- kinetic manifesto: one word per scroll step ---------- */
if (!reduced) {
  const words = gsap.utils.toArray(".kinetic-word");
  const tl = gsap.timeline({
    scrollTrigger: {
      trigger: ".kinetic",
      start: "top top",
      end: "bottom bottom",
      scrub: 0.3,
    },
  });
  words.forEach((w, i) => {
    tl.fromTo(w,
      { opacity: 0, scale: 3.2, rotation: i % 2 ? 2 : -2 },
      { opacity: 1, scale: 1, rotation: 0, duration: 0.5, ease: "power4.in" }, i * 2)
      .to(w, { opacity: 1, duration: 1 }, i * 2 + 0.5); /* hold */
    if (i < words.length - 1) {
      tl.to(w, { opacity: 0, scale: 0.85, duration: 0.4 }, i * 2 + 1.6);
    }
  });
}

/* ---------- work grid: hover video reveals (clip 2 crops) ---------- */
document.querySelectorAll(".work-card").forEach(card => {
  const video = card.querySelector("video");
  video.style.objectPosition = card.dataset.crop;
  card.addEventListener("pointerenter", () => { video.play().catch(() => {}); });
  card.addEventListener("pointerleave", () => { video.pause(); });
});

/* ---------- gentle reveals for section headings ---------- */
if (!reduced) {
  gsap.utils.toArray(".work-heading, .services-left h2, .team-content h2, .footer-title").forEach(el => {
    gsap.from(el, {
      y: 60,
      opacity: 0,
      duration: 0.9,
      ease: "power3.out",
      scrollTrigger: { trigger: el, start: "top 85%", once: true },
    });
  });
}
