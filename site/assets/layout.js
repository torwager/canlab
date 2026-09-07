/* Shared header/footer, header scroll state, mobile nav, active link, scroll reveals, analytics beacon. */
(function () {
  const C = window.CANLAB_CONFIG || {};
  const header = `<header class="site-header solid"><div class="wrap">
    <a class="brand" href="./"><span class="brand-mark" aria-hidden="true"><svg viewBox="0 0 32 32" fill="none"><circle cx="8" cy="10" r="3"/><circle cx="22" cy="7" r="3"/><circle cx="25" cy="21" r="3"/><circle cx="11" cy="24" r="3"/><circle cx="16" cy="15" r="3.4"/><path d="M10.6 11.8 13.6 13.6M19.2 8.4l-1.6 4.2M18.9 16.7l3.8 2.8M13.6 17.2l-1.4 4.2M11 10.5l9.4-3M13.5 23.2l9.1-2.6"/></svg></span><span><b>CAN</b>lab</span></a>
    <button class="nav-toggle" aria-label="Menu" aria-expanded="false" aria-controls="nav"><span></span></button>
    <nav class="nav" id="nav" aria-label="Main">
      <a href="research.html">Research</a>
      <a href="people.html">People</a>
      <a href="publications.html">Publications</a>
      <a href="news.html">News</a>
      <a href="resources.html">Tools &amp; training</a>
      <div class="menu"><a href="network.html" class="menu-btn" aria-haspopup="true" aria-expanded="false">Explore ▾</a>
        <div class="menu-list"><a href="network.html">Collaborator network</a><a href="bibliometrics.html">Bibliometrics</a></div></div>
      <a href="join.html">Join</a>
    </nav></div></header>`;
  const footer = `<footer class="site-footer"><div class="wrap">
    <div><strong>Cognitive and Affective Neuroscience Lab</strong>Dartmouth College, Hanover NH. Directed by Tor Wager. We study the neurophysiology of pain, emotion, stress and empathy, and how they are shaped by beliefs, expectations and social context. <span id="foot-updated"></span></div>
    <div><strong>Lab</strong><ul><li><a href="research.html">Research</a></li><li><a href="people.html">People</a></li><li><a href="publications.html">Publications</a></li><li><a href="news.html">News</a></li><li><a href="join.html">Join us / participate</a></li><li><a href="mylist.html">My list</a></li><li><a href="account.html">Sign in</a></li><li><a href="about.html">About this site</a></li><li><a href="feed.xml">RSS: new papers</a></li></ul></div>
    <div><strong>Resources</strong><ul><li><a href="resources.html">Tools &amp; training</a></li><li><a href="https://canlab.github.io" target="_blank" rel="noopener">canlab.github.io</a></li><li><a href="https://github.com/canlab" target="_blank" rel="noopener">CANlab on GitHub</a></li><li><a href="https://scienceofplacebo.org" target="_blank" rel="noopener">Science of Placebo</a></li><li><a href="https://github.com/${C.repo || "torwager/canlab"}" target="_blank" rel="noopener">This site's source &amp; data</a></li></ul></div>
    <div class="credit-row"><span class="credit">Designed by <a href="https://torwager.github.io" target="_blank" rel="noopener">Tor Wager</a> · Cognitive and Affective Neuroscience Lab · Dartmouth College</span></div>
  </div></footer>`;
  const h = document.getElementById("site-header"); if (h) h.outerHTML = header;
  const f = document.getElementById("site-footer"); if (f) f.outerHTML = footer;

  const hdr = document.querySelector(".site-header");
  const onScroll = () => hdr && hdr.classList.toggle("scrolled", window.scrollY > 8);
  window.addEventListener("scroll", onScroll, { passive: true }); onScroll();

  if (window.CL) CL.updateListBadge();
  // "My list" lives in the footer: mirror the star count there
  const here = (location.pathname.split("/").pop() || "index.html");
  document.querySelectorAll(".nav a").forEach(a => { if (a.getAttribute("href") === here) a.classList.add("active"); });
  if (here.startsWith("paper")) document.querySelectorAll('.nav a[href="publications.html"]').forEach(a => a.classList.add("active"));

  const toggle = document.querySelector(".nav-toggle"), nav = document.getElementById("nav");
  if (toggle && nav) {
    toggle.addEventListener("click", () => { const open = nav.classList.toggle("open"); toggle.setAttribute("aria-expanded", String(open)); });
    nav.addEventListener("click", e => { if (e.target.tagName === "A" && !e.target.classList.contains("menu-btn")) nav.classList.remove("open"); });
  }
  document.querySelectorAll(".menu-btn").forEach(b => b.addEventListener("click", e => { const m = b.parentElement; if (!m.classList.contains("open") && window.matchMedia("(hover: none)").matches) { e.preventDefault(); m.classList.add("open"); b.setAttribute("aria-expanded", "true"); } }));

  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const rvs = document.querySelectorAll(".rv");
  if (reduce || !("IntersectionObserver" in window)) { rvs.forEach(el => el.classList.add("in")); }
  else { const io = new IntersectionObserver(entries => { entries.forEach(en => { if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); } }); }, { threshold: 0.12 }); rvs.forEach(el => io.observe(el)); }

  // Cookie-free analytics (Cloudflare Web Analytics) once a token is configured
  if (C.cfAnalyticsToken) { const s = document.createElement("script"); s.defer = true; s.src = "https://static.cloudflareinsights.com/beacon.min.js"; s.setAttribute("data-cf-beacon", JSON.stringify({ token: C.cfAnalyticsToken })); document.head.appendChild(s); }
})();
