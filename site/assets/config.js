/* Site configuration for canlab.science / torwager.github.io/canlab.
   Giscus values come from https://giscus.app after enabling GitHub Discussions on torwager/canlab. */
window.CANLAB_CONFIG = {
  repo: "torwager/canlab",
  siteUrl: "https://torwager.github.io/canlab",
  giscus: { repoId: "R_kgDOUQb3QQ", category: "General", categoryId: "DIC_kwDOUQb3Qc4DFBRG", papersCategory: "General", papersCategoryId: "DIC_kwDOUQb3Qc4DFBRG" },
  // Community API (Cloudflare Worker, see worker/README.md): GitHub sign-in and synced "My list". Empty until deployed.
  communityApi: "",
  // Cloudflare Web Analytics token (cookie-free). Empty disables the beacon; see README "Analytics".
  cfAnalyticsToken: "",
  // PDFs mirrored from the old Dartmouth site: GitHub release assets (public). Original URLs are kept as fallback.
  pdfMirror: "https://github.com/torwager/canlab/releases/download/pdfs/"
};
