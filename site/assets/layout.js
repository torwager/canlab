/* Shared header/footer, header scroll state, mobile nav, active link, scroll reveals, analytics beacon. */
(function () {
  const C = window.CANLAB_CONFIG || {};
  // Explore menu = the tiles on explore.html (one list for both)
  const EXPLORE = window.CANLAB_EXPLORE = [
    { title: "Neuromarker Gallery", url: "https://neuromarkers.io", img: "neuromarkers.jpg", blurb: "Browse, view and download published brain signatures (NPS, SIIPS, PINES and more)." },
    { title: "fMRI analysis code", url: "https://github.com/canlab", img: "code.jpg", blurb: "CANlab toolboxes on GitHub: CanlabCore, mediation, meta-analysis and more." },
    { title: "Open data", url: "https://github.com/canlab/CANlab_data_public", img: "data.jpg", blurb: "Shared behavioural and physiological datasets from published studies." },
    { title: "Task paradigms", url: "https://github.com/canlab/Paradigms_Public", img: "paradigms.jpg", blurb: "Experimental task code from published studies, ready to run." },
    { title: "Journal club", url: "journal-club.html", img: "journal-club.jpg", blurb: "Papers the lab is reading, searchable by topic and method." },
    { title: "My list", url: "mylist.html", img: "mylist.jpg", blurb: "Star papers into lists and export them to your reference manager." },
    { title: "Collaborator network", url: "network.html", img: "network.jpg", blurb: "An interactive map of the lab's co-authors." },
    { title: "Bibliometrics", url: "bibliometrics.html", img: "bibliometrics.jpg", blurb: "Publications, topics and methods over the years." },
    { title: "Science of Placebo", url: "https://scienceofplacebo.org", img: "placebo.jpg", blurb: "A research hub on placebo and nocebo effects." },
    { title: "Elements of fMRI tutorials", url: "https://torwager.github.io/elements-of-fmri-tutorials", img: "elements.jpg", blurb: "Hands-on tutorials that accompany the MIT Press book." },
    { title: "PBS shared resources", url: "https://dbic.github.io/PBS_resources/", img: "pbs.jpg", blurb: "Shared research resources for Dartmouth Psychological and Brain Sciences." },
    { title: "fMRI course (MIND)", url: "https://torwager.github.io/mindfmricourse", img: "mind-course.jpg", blurb: "Image acquisition and analysis with SPM and ICA." },
  ];
  const ext = u => /^https?:/.test(u) ? ' target="_blank" rel="noopener"' : "";
  const header = `<header class="site-header solid"><div class="wrap">
    <a class="brand" href="./"><span class="brand-mark" aria-hidden="true"><img src="assets/logo-mark.png" alt="" width="26" height="26"></span><span><b>CAN</b>lab</span></a>
    <button class="nav-toggle" aria-label="Menu" aria-expanded="false" aria-controls="nav"><span></span></button>
    <nav class="nav" id="nav" aria-label="Main">
      <a href="research.html">Research</a>
      <a href="people.html">People</a>
      <div class="menu"><a href="publications.html" class="menu-btn" aria-haspopup="true" aria-expanded="false">Publications ▾</a>
        <div class="menu-list"><a href="publications.html"><b>All publications</b></a><a href="mylist.html">My list</a></div></div>
      <a href="news.html">News</a>
      <a href="resources.html">Tools &amp; training</a>
      <div class="menu"><a href="explore.html" class="menu-btn" aria-haspopup="true" aria-expanded="false">Explore ▾</a>
        <div class="menu-list"><a href="explore.html"><b>All resources</b></a>${EXPLORE.map(e => `<a href="${e.url}"${ext(e.url)}>${e.title}</a>`).join("")}</div></div>
      <a href="join.html">Join</a>
    </nav></div></header>`;
  const footer = `<footer class="site-footer"><div class="wrap">
    <div><strong>Cognitive and Affective Neuroscience Lab</strong>Dartmouth College, Hanover NH. Directed by Tor Wager. We study the neurophysiology of pain, emotion, stress and empathy, and how they are shaped by beliefs, expectations and social context. <span id="foot-updated"></span></div>
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
