// Pitch deck for Secure AI Office
// Visual system:
//   Dominant: navy #0A1628 (dark slides, ~30% of deck for "sandwich" structure)
//   Surface:  #F7F8FB (light content slides)
//   Brand:    magenta #E1067D (sparing accent — primary CTA color, key stats, motif stripe)
//   Ink:      #152844 (heading), #4A5876 (body)
//   Lines:    #D8DDE6
//   Motif:    8pt magenta stripe at left edge of dark slides; magenta-filled chip icons on light slides

const pptxgen = require("pptxgenjs");
const pres = new pptxgen();

pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
pres.title = "Secure AI Office — Pitch Deck";
pres.author = "Sensitek";
pres.company = "Secure AI Office";

const NAVY    = "0A1628";
const NAVY_2  = "13213A";
const SURFACE = "F7F8FB";
const PAPER   = "FFFFFF";
const INK     = "152844";
const BODY    = "4A5876";
const MUTED   = "8A94A6";
const LINE    = "D8DDE6";
const MAGENTA = "E1067D";
const MAGENTA_DEEP = "C9056D";
const SUCCESS = "047857";

const W = 13.333;
const H = 7.5;

const FONT_HEAD = "Calibri";
const FONT_BODY = "Calibri";

// ---------- helpers ----------
function darkBackdrop(slide) {
  slide.background = { color: NAVY };
  // brand stripe on left edge
  slide.addShape("rect", { x: 0, y: 0, w: 0.18, h: H, fill: { color: MAGENTA }, line: { color: MAGENTA } });
  // subtle decorative diagonal accent (very low opacity)
  slide.addShape("rect", {
    x: W - 2.6, y: -0.6, w: 3.2, h: 1.6,
    rotate: -18,
    fill: { color: MAGENTA, transparency: 88 },
    line: { type: "none" },
  });
}

function lightBackdrop(slide) {
  slide.background = { color: SURFACE };
  // small magenta corner mark — repeat motif
  slide.addShape("rect", { x: 0, y: 0, w: 0.18, h: 0.6, fill: { color: MAGENTA }, line: { color: MAGENTA } });
}

function pageNumber(slide, n, total, onDark = false) {
  slide.addText(`${String(n).padStart(2, "0")} / ${String(total).padStart(2, "0")}`, {
    x: W - 1.4, y: H - 0.45, w: 1.0, h: 0.3,
    fontFace: FONT_BODY, fontSize: 9, bold: true,
    color: onDark ? "8FA0B8" : MUTED,
    align: "right",
  });
  slide.addText("SECURE AI OFFICE", {
    x: 0.5, y: H - 0.45, w: 4, h: 0.3,
    fontFace: FONT_HEAD, fontSize: 9, bold: true,
    color: onDark ? "8FA0B8" : MUTED,
    charSpacing: 4,
  });
}

function eyebrow(slide, text, x, y, color = MAGENTA) {
  slide.addText(text, {
    x, y, w: 5, h: 0.35,
    fontFace: FONT_HEAD, fontSize: 11, bold: true,
    color, charSpacing: 4,
  });
}

function sectionTitle(slide, text, x, y, color = INK, w = 11.5) {
  slide.addText(text, {
    x, y, w, h: 1.0,
    fontFace: FONT_HEAD, fontSize: 38, bold: true, color,
    margin: 0,
  });
}

function chipIcon(slide, x, y, label, size = 0.7) {
  slide.addShape("ellipse", {
    x, y, w: size, h: size,
    fill: { color: MAGENTA },
    line: { type: "none" },
  });
  slide.addText(label, {
    x, y, w: size, h: size,
    fontFace: FONT_HEAD, fontSize: 14, bold: true, color: "FFFFFF",
    align: "center", valign: "middle",
    margin: 0,
  });
}

const TOTAL = 15;
const SHOTS = "/Users/muskan/SecureOffice2/docs/pitch/shots";

// ============================================================
// SLIDE 1 — COVER (DARK)
// ============================================================
{
  const s = pres.addSlide();
  darkBackdrop(s);

  // Brand wordmark
  s.addText("SECURE AI OFFICE", {
    x: 0.7, y: 0.8, w: 9, h: 0.5,
    fontFace: FONT_HEAD, fontSize: 13, bold: true,
    color: MAGENTA, charSpacing: 8,
  });

  // Big headline
  s.addText("Plan, procure & operate", {
    x: 0.7, y: 2.3, w: 12, h: 1.2,
    fontFace: FONT_HEAD, fontSize: 64, bold: true, color: "FFFFFF",
    margin: 0,
  });
  s.addText("SMB networks — end to end.", {
    x: 0.7, y: 3.4, w: 12, h: 1.2,
    fontFace: FONT_HEAD, fontSize: 64, bold: true, color: MAGENTA,
    margin: 0,
  });

  // Sub
  s.addText(
    "An AI-native platform that turns business requirements into a working network — from sizing and BOM to topology, ordering, deployment and live monitoring.",
    {
      x: 0.7, y: 4.9, w: 9.5, h: 1.0,
      fontFace: FONT_BODY, fontSize: 16,
      color: "CADCFC", lineSpacingMultiple: 1.35,
    }
  );

  // Footer line
  s.addShape("line", {
    x: 0.7, y: 6.55, w: 11.9, h: 0,
    line: { color: "2A3A56", width: 1 },
  });
  s.addText("Pitch Deck • 2026", {
    x: 0.7, y: 6.7, w: 6, h: 0.4,
    fontFace: FONT_BODY, fontSize: 12, color: "8FA0B8", charSpacing: 3,
  });
  s.addText("Confidential", {
    x: W - 3, y: 6.7, w: 2.3, h: 0.4,
    fontFace: FONT_BODY, fontSize: 12, color: "8FA0B8", align: "right", charSpacing: 3,
  });
}

// ============================================================
// SLIDE 2 — THE PROBLEM (LIGHT)
// ============================================================
{
  const s = pres.addSlide();
  lightBackdrop(s);

  eyebrow(s, "THE PROBLEM", 0.7, 0.55);
  sectionTitle(s, "SMB networks are still", 0.7, 1.0);
  s.addText("planned in spreadsheets.", {
    x: 0.7, y: 1.7, w: 12, h: 0.9,
    fontFace: FONT_HEAD, fontSize: 38, bold: true, color: MAGENTA, margin: 0,
  });

  s.addText(
    "Most small and mid-sized businesses still rely on consultants, MSPs, or trial-and-error to design their office network. The result is slow procurement, mismatched gear, and operational blind spots after deployment.",
    {
      x: 0.7, y: 2.9, w: 11.9, h: 1.0,
      fontFace: FONT_BODY, fontSize: 14, color: BODY, lineSpacingMultiple: 1.4,
    }
  );

  // 3 stat cards
  const stats = [
    { num: "73%", label: "of SMBs delay network upgrades because they don't know what to buy" },
    { num: "6 wks", label: "average lead time from initial quote to a deployed, working network" },
    { num: "62%", label: "of SMB IT budgets get spent on hardware that's over- or under-sized" },
  ];
  const cardW = 3.85, cardH = 2.5, gap = 0.25;
  const startX = 0.7;
  stats.forEach((st, i) => {
    const x = startX + i * (cardW + gap);
    const y = 4.4;
    s.addShape("roundRect", {
      x, y, w: cardW, h: cardH,
      fill: { color: PAPER }, line: { color: LINE, width: 1 },
      rectRadius: 0.12,
    });
    s.addShape("rect", {
      x, y, w: cardW, h: 0.08,
      fill: { color: MAGENTA }, line: { type: "none" },
    });
    s.addText(st.num, {
      x: x + 0.3, y: y + 0.3, w: cardW - 0.6, h: 1.1,
      fontFace: FONT_HEAD, fontSize: 56, bold: true, color: INK, margin: 0,
    });
    s.addText(st.label, {
      x: x + 0.3, y: y + 1.5, w: cardW - 0.6, h: 1.0,
      fontFace: FONT_BODY, fontSize: 13, color: BODY, lineSpacingMultiple: 1.35, margin: 0,
    });
  });

  pageNumber(s, 2, TOTAL);
}

// ============================================================
// SLIDE 3 — THE SOLUTION (LIGHT)
// ============================================================
{
  const s = pres.addSlide();
  lightBackdrop(s);

  eyebrow(s, "THE SOLUTION", 0.7, 0.55);
  sectionTitle(s, "One platform. Four guided steps.", 0.7, 1.0);
  s.addText(
    "From a 5-minute business intake to a live network you can monitor — Secure AI Office automates every link in the chain.",
    {
      x: 0.7, y: 2.0, w: 11.9, h: 0.7,
      fontFace: FONT_BODY, fontSize: 15, color: BODY, lineSpacingMultiple: 1.35,
    }
  );

  // 4-step horizontal flow
  const steps = [
    { n: "01", t: "Business Intake", d: "Capture industry, headcount, sites, security needs in 5 minutes." },
    { n: "02", t: "AI Sizing", d: "Deterministic formulas + AI advisor recommend AP, switch & router counts." },
    { n: "03", t: "BOM + Diagram", d: "Auto-generated bill of materials and customer-friendly topology." },
    { n: "04", t: "Order & Monitor", d: "One-click cart, vendor fulfillment, and Zabbix-powered live monitoring." },
  ];
  const sw = 2.95, sh = 3.0;
  const sStartX = 0.7;
  const sY = 3.1;
  steps.forEach((st, i) => {
    const x = sStartX + i * (sw + 0.15);
    s.addShape("roundRect", {
      x, y: sY, w: sw, h: sh,
      fill: { color: PAPER }, line: { color: LINE, width: 1 },
      rectRadius: 0.12,
    });
    // step number badge
    s.addShape("ellipse", {
      x: x + 0.35, y: sY + 0.3, w: 0.85, h: 0.85,
      fill: { color: MAGENTA }, line: { type: "none" },
    });
    s.addText(st.n, {
      x: x + 0.35, y: sY + 0.3, w: 0.85, h: 0.85,
      fontFace: FONT_HEAD, fontSize: 16, bold: true, color: "FFFFFF",
      align: "center", valign: "middle", margin: 0,
    });
    s.addText(st.t, {
      x: x + 0.35, y: sY + 1.25, w: sw - 0.7, h: 0.5,
      fontFace: FONT_HEAD, fontSize: 18, bold: true, color: INK, margin: 0,
    });
    s.addText(st.d, {
      x: x + 0.35, y: sY + 1.78, w: sw - 0.7, h: 1.1,
      fontFace: FONT_BODY, fontSize: 12, color: BODY, lineSpacingMultiple: 1.4, margin: 0,
    });
  });

  pageNumber(s, 3, TOTAL);
}

// ============================================================
// SLIDE 4 — PRODUCT WALKTHROUGH (LIGHT, two-col)
// ============================================================
{
  const s = pres.addSlide();
  lightBackdrop(s);

  eyebrow(s, "PRODUCT", 0.7, 0.55);
  sectionTitle(s, "What the customer actually sees.", 0.7, 1.0, INK, 12);

  // Left column — narrative bullets
  const bullets = [
    { k: "Guided intake", v: "Smart forms with industry presets and conditional questions." },
    { k: "Live BOM table", v: "Vendor-linked SKUs with real prices and one-click add-to-cart." },
    { k: "Topology preview", v: "Drawio-rendered diagram so non-technical buyers can sign off." },
    { k: "Cart → quote → order", v: "Same workflow procurement teams already understand." },
    { k: "Post-deploy ops", v: "Zabbix dashboards stitched directly into the customer portal." },
  ];

  const leftX = 0.7, listY = 2.3;
  bullets.forEach((b, i) => {
    const y = listY + i * 0.78;
    chipIcon(s, leftX, y, String(i + 1), 0.55);
    s.addText(b.k, {
      x: leftX + 0.75, y: y, w: 4.5, h: 0.35,
      fontFace: FONT_HEAD, fontSize: 15, bold: true, color: INK, margin: 0,
    });
    s.addText(b.v, {
      x: leftX + 0.75, y: y + 0.32, w: 5, h: 0.45,
      fontFace: FONT_BODY, fontSize: 12, color: BODY, lineSpacingMultiple: 1.35, margin: 0,
    });
  });

  // Right column — mock product card
  const mx = 6.6, my = 2.3, mw = 6.0, mh = 4.6;
  s.addShape("roundRect", {
    x: mx, y: my, w: mw, h: mh,
    fill: { color: PAPER }, line: { color: LINE, width: 1 },
    rectRadius: 0.16,
  });
  // window chrome
  s.addShape("rect", {
    x: mx, y: my, w: mw, h: 0.45,
    fill: { color: NAVY }, line: { type: "none" },
  });
  ["E64C4C", "F1B940", "4DAA59"].forEach((c, i) => {
    s.addShape("ellipse", {
      x: mx + 0.18 + i * 0.28, y: my + 0.13, w: 0.18, h: 0.18,
      fill: { color: c }, line: { type: "none" },
    });
  });
  s.addText("secureaioffice.app/builder", {
    x: mx + 1.1, y: my + 0.06, w: mw - 1.5, h: 0.34,
    fontFace: FONT_BODY, fontSize: 11, color: "8FA0B8",
    align: "center", valign: "middle", margin: 0,
  });

  // mock content inside the window
  s.addText("Network Design Builder", {
    x: mx + 0.35, y: my + 0.65, w: mw - 0.7, h: 0.4,
    fontFace: FONT_HEAD, fontSize: 16, bold: true, color: INK, margin: 0,
  });
  s.addText("Auto-generated for Acme Dental — 2 sites, 24 staff", {
    x: mx + 0.35, y: my + 1.0, w: mw - 0.7, h: 0.3,
    fontFace: FONT_BODY, fontSize: 11, color: MUTED, margin: 0,
  });

  // 3 KPI cards inside mock
  const kpis = [
    { l: "ESTIMATED CAPEX", v: "$8,420" },
    { l: "AP COUNT", v: "6" },
    { l: "BOM LINES", v: "14" },
  ];
  kpis.forEach((k, i) => {
    const kx = mx + 0.35 + i * 1.85, ky = my + 1.5;
    s.addShape("roundRect", {
      x: kx, y: ky, w: 1.7, h: 0.95,
      fill: { color: SURFACE }, line: { color: LINE, width: 0.75 },
      rectRadius: 0.08,
    });
    s.addText(k.l, {
      x: kx + 0.15, y: ky + 0.1, w: 1.5, h: 0.3,
      fontFace: FONT_HEAD, fontSize: 8, bold: true, color: MUTED,
      charSpacing: 2, margin: 0,
    });
    s.addText(k.v, {
      x: kx + 0.15, y: ky + 0.38, w: 1.5, h: 0.5,
      fontFace: FONT_HEAD, fontSize: 20, bold: true, color: INK, margin: 0,
    });
  });

  // BOM rows (2 rows + "+ more" so the CTA fits cleanly)
  const rows = [
    { sku: "UAP-AC-PRO", q: "6", p: "$1,194" },
    { sku: "USW-24-POE", q: "1", p: "$679" },
  ];
  s.addText("Bill of Materials", {
    x: mx + 0.35, y: my + 2.7, w: mw - 0.7, h: 0.3,
    fontFace: FONT_HEAD, fontSize: 12, bold: true, color: INK, margin: 0,
  });
  rows.forEach((r, i) => {
    const ry = my + 3.05 + i * 0.38;
    s.addShape("rect", {
      x: mx + 0.35, y: ry + 0.34, w: mw - 0.7, h: 0.012,
      fill: { color: LINE }, line: { type: "none" },
    });
    s.addText(r.sku, {
      x: mx + 0.35, y: ry, w: 2.6, h: 0.32,
      fontFace: FONT_BODY, fontSize: 11, color: INK, margin: 0,
    });
    s.addText(`Qty ${r.q}`, {
      x: mx + 3.3, y: ry, w: 1.0, h: 0.32,
      fontFace: FONT_BODY, fontSize: 11, color: BODY, margin: 0,
    });
    s.addText(r.p, {
      x: mx + mw - 1.4, y: ry, w: 1.0, h: 0.32,
      fontFace: FONT_BODY, fontSize: 11, bold: true, color: INK,
      align: "right", margin: 0,
    });
  });
  // "+ N more" hint row
  s.addText("+ 12 more items", {
    x: mx + 0.35, y: my + 3.05 + 2 * 0.38 + 0.04, w: 3, h: 0.3,
    fontFace: FONT_BODY, fontSize: 10, italic: true, color: MUTED, margin: 0,
  });

  // CTA button — pinned bottom-right with margin
  s.addShape("roundRect", {
    x: mx + mw - 1.95, y: my + mh - 0.7, w: 1.6, h: 0.5,
    fill: { color: MAGENTA }, line: { type: "none" },
    rectRadius: 0.08,
  });
  s.addText("Add all to cart", {
    x: mx + mw - 1.95, y: my + mh - 0.7, w: 1.6, h: 0.5,
    fontFace: FONT_HEAD, fontSize: 11, bold: true, color: "FFFFFF",
    align: "center", valign: "middle", margin: 0,
  });

  pageNumber(s, 4, TOTAL);
}

// ============================================================
// SLIDE 5 — DESIGN SIDE (LIGHT, two real screenshots)
// ============================================================
{
  const s = pres.addSlide();
  lightBackdrop(s);

  eyebrow(s, "INSIDE THE PRODUCT — DESIGN", 0.7, 0.55);
  sectionTitle(s, "Customers go from blank page to BOM.", 0.7, 1.0);
  s.addText(
    "Marketing landing leads into an AI-assisted intake. Five minutes of answers becomes a sized network design.",
    {
      x: 0.7, y: 2.05, w: 11.9, h: 0.6,
      fontFace: FONT_BODY, fontSize: 14, color: BODY, lineSpacingMultiple: 1.4,
    }
  );

  // Two screenshots side by side, larger
  const designShots = [
    { file: "home.png",   label: "PUBLIC LANDING",   caption: "First impression and clear value proposition." },
    { file: "intake.png", label: "AI-GUIDED INTAKE", caption: "AI Assistant rides along with every form field." },
  ];
  const tw = 6.0, ty = 2.85, tgap = 0.2;
  designShots.forEach((shot, i) => {
    const x = 0.7 + i * (tw + tgap);
    s.addShape("roundRect", {
      x, y: ty, w: tw, h: 4.0,
      fill: { color: PAPER }, line: { color: LINE, width: 1 },
      rectRadius: 0.14,
    });
    // window chrome bar
    s.addShape("rect", {
      x: x + 0.22, y: ty + 0.22, w: tw - 0.44, h: 0.32,
      fill: { color: NAVY }, line: { type: "none" },
    });
    ["E64C4C", "F1B940", "4DAA59"].forEach((c, j) => {
      s.addShape("ellipse", {
        x: x + 0.32 + j * 0.22, y: ty + 0.29, w: 0.16, h: 0.16,
        fill: { color: c }, line: { type: "none" },
      });
    });
    s.addImage({
      path: `${SHOTS}/${shot.file}`,
      x: x + 0.22, y: ty + 0.54, w: tw - 0.44, h: 2.55,
      sizing: { type: "cover", w: tw - 0.44, h: 2.55 },
    });
    s.addShape("rect", {
      x: x + 0.22, y: ty + 3.13, w: tw - 0.44, h: 0.05,
      fill: { color: MAGENTA }, line: { type: "none" },
    });
    s.addText(shot.label, {
      x: x + 0.32, y: ty + 3.25, w: tw - 0.6, h: 0.35,
      fontFace: FONT_HEAD, fontSize: 11, bold: true, color: MAGENTA,
      charSpacing: 4, margin: 0,
    });
    s.addText(shot.caption, {
      x: x + 0.32, y: ty + 3.55, w: tw - 0.6, h: 0.4,
      fontFace: FONT_BODY, fontSize: 12, color: BODY,
      lineSpacingMultiple: 1.35, margin: 0,
    });
  });

  pageNumber(s, 5, TOTAL);
}

// ============================================================
// SLIDE 6 — OPS SIDE (LIGHT, dashboard + managed services)
// ============================================================
{
  const s = pres.addSlide();
  lightBackdrop(s);

  eyebrow(s, "INSIDE THE PRODUCT — OPERATE", 0.7, 0.55);
  sectionTitle(s, "After the sale, the platform earns its keep.", 0.7, 1.0);
  s.addText(
    "A live customer dashboard tracks orders and recurring spend. Managed services flow into the same cart so every device can become a subscription.",
    {
      x: 0.7, y: 2.05, w: 11.9, h: 0.7,
      fontFace: FONT_BODY, fontSize: 14, color: BODY, lineSpacingMultiple: 1.4,
    }
  );

  const opsShots = [
    {
      file: "dashboard.png",
      label: "CUSTOMER DASHBOARD",
      caption: "Recurring revenue, orders, active subs and recent designs at a glance."
    },
    {
      file: "managed.png",
      label: "MANAGED SERVICES + CART",
      caption: "Per-device managed pricing rolls into the same checkout flow."
    },
  ];
  const tw = 6.0, ty = 2.95, tgap = 0.2;
  opsShots.forEach((shot, i) => {
    const x = 0.7 + i * (tw + tgap);
    s.addShape("roundRect", {
      x, y: ty, w: tw, h: 3.85,
      fill: { color: PAPER }, line: { color: LINE, width: 1 },
      rectRadius: 0.14,
    });
    s.addShape("rect", {
      x: x + 0.22, y: ty + 0.22, w: tw - 0.44, h: 0.32,
      fill: { color: NAVY }, line: { type: "none" },
    });
    ["E64C4C", "F1B940", "4DAA59"].forEach((c, j) => {
      s.addShape("ellipse", {
        x: x + 0.32 + j * 0.22, y: ty + 0.29, w: 0.16, h: 0.16,
        fill: { color: c }, line: { type: "none" },
      });
    });
    s.addImage({
      path: `${SHOTS}/${shot.file}`,
      x: x + 0.22, y: ty + 0.54, w: tw - 0.44, h: 2.45,
      sizing: { type: "cover", w: tw - 0.44, h: 2.45 },
    });
    s.addShape("rect", {
      x: x + 0.22, y: ty + 3.03, w: tw - 0.44, h: 0.05,
      fill: { color: MAGENTA }, line: { type: "none" },
    });
    s.addText(shot.label, {
      x: x + 0.32, y: ty + 3.15, w: tw - 0.6, h: 0.35,
      fontFace: FONT_HEAD, fontSize: 11, bold: true, color: MAGENTA,
      charSpacing: 4, margin: 0,
    });
    s.addText(shot.caption, {
      x: x + 0.32, y: ty + 3.45, w: tw - 0.6, h: 0.4,
      fontFace: FONT_BODY, fontSize: 12, color: BODY,
      lineSpacingMultiple: 1.35, margin: 0,
    });
  });

  pageNumber(s, 6, TOTAL);
}

// ============================================================
// SLIDE 7 — CAPABILITIES (LIGHT, 2x3 grid)
// ============================================================
{
  const s = pres.addSlide();
  lightBackdrop(s);

  eyebrow(s, "CAPABILITIES", 0.7, 0.55);
  sectionTitle(s, "Six pillars, one workflow.", 0.7, 1.0);

  const features = [
    { i: "B", t: "Business Intake", d: "Industry templates, conditional logic and security profiles built in." },
    { i: "S", t: "Deterministic Sizing", d: "Formulas (not vibes) translate headcount + sq ft into AP/switch counts." },
    { i: "C", t: "BOM Generator", d: "Catalog-linked SKUs from real vendors with live pricing." },
    { i: "T", t: "Topology Diagrams", d: "Drawio export so customers can review and approve visually." },
    { i: "M", t: "Vendor Marketplace", d: "Multi-vendor catalog (CellHub) — sell, fulfill, manage commissions." },
    { i: "Z", t: "Live Monitoring", d: "Zabbix-powered health dashboards stitched into the customer portal." },
  ];

  const cols = 3, rows = 2;
  const gx = 0.7, gy = 2.15, gw = 4.0, gh = 2.1, gap = 0.18;
  features.forEach((f, idx) => {
    const c = idx % cols, r = Math.floor(idx / cols);
    const x = gx + c * (gw + gap);
    const y = gy + r * (gh + gap);
    s.addShape("roundRect", {
      x, y, w: gw, h: gh,
      fill: { color: PAPER }, line: { color: LINE, width: 1 },
      rectRadius: 0.12,
    });
    chipIcon(s, x + 0.35, y + 0.3, f.i, 0.7);
    s.addText(f.t, {
      x: x + 0.35, y: y + 1.1, w: gw - 0.7, h: 0.4,
      fontFace: FONT_HEAD, fontSize: 16, bold: true, color: INK, margin: 0,
    });
    s.addText(f.d, {
      x: x + 0.35, y: y + 1.5, w: gw - 0.7, h: 0.55,
      fontFace: FONT_BODY, fontSize: 11.5, color: BODY, lineSpacingMultiple: 1.35, margin: 0,
    });
  });

  pageNumber(s, 7, TOTAL);
}

// ============================================================
// SLIDE 8 — AI AT THE CORE (DARK)
// ============================================================
{
  const s = pres.addSlide();
  darkBackdrop(s);

  s.addText("AI AT THE CORE", {
    x: 0.7, y: 0.7, w: 8, h: 0.4,
    fontFace: FONT_HEAD, fontSize: 12, bold: true, color: MAGENTA, charSpacing: 6,
  });
  s.addText("Not a chatbot bolted on.", {
    x: 0.7, y: 1.3, w: 12, h: 0.95,
    fontFace: FONT_HEAD, fontSize: 42, bold: true, color: "FFFFFF", margin: 0,
  });
  s.addText("AI runs the whole pipeline.", {
    x: 0.7, y: 2.2, w: 12, h: 0.95,
    fontFace: FONT_HEAD, fontSize: 42, bold: true, color: MAGENTA, margin: 0,
  });

  s.addText(
    "Every step from intake to operations is enriched by purpose-built AI: a live consultant avatar, a contextual chatbot, automatic topology synthesis, and intelligent catalog matching against thousands of SKUs.",
    {
      x: 0.7, y: 3.4, w: 11.9, h: 1.0,
      fontFace: FONT_BODY, fontSize: 15, color: "CADCFC", lineSpacingMultiple: 1.4,
    }
  );

  const cards = [
    { t: "Anam Avatar", d: "Live AI consultant walks customers through intake and trade-offs." },
    { t: "Contextual Chatbot", d: "Answers product, pricing and topology questions in-page." },
    { t: "Topology Synthesis", d: "AI assembles a Drawio diagram from raw BOM data." },
    { t: "Catalog Matching", d: "Embeddings map fuzzy requirements to real vendor SKUs." },
  ];
  const cw = 2.95, ch = 2.3;
  cards.forEach((c, i) => {
    const x = 0.7 + i * (cw + 0.15);
    const y = 4.7;
    s.addShape("roundRect", {
      x, y, w: cw, h: ch,
      fill: { color: NAVY_2 }, line: { color: "2A3A56", width: 1 },
      rectRadius: 0.12,
    });
    s.addShape("rect", {
      x, y, w: cw, h: 0.07,
      fill: { color: MAGENTA }, line: { type: "none" },
    });
    s.addText(c.t, {
      x: x + 0.3, y: y + 0.35, w: cw - 0.6, h: 0.5,
      fontFace: FONT_HEAD, fontSize: 17, bold: true, color: "FFFFFF", margin: 0,
    });
    s.addText(c.d, {
      x: x + 0.3, y: y + 0.95, w: cw - 0.6, h: 1.2,
      fontFace: FONT_BODY, fontSize: 12, color: "CADCFC", lineSpacingMultiple: 1.4, margin: 0,
    });
  });

  pageNumber(s, 8, TOTAL, true);
}

// ============================================================
// SLIDE 9 — AI DESIGN FLOW (LIGHT, customer journey with AI)
// ============================================================
{
  const s = pres.addSlide();
  lightBackdrop(s);

  eyebrow(s, "AI DESIGN FLOW", 0.7, 0.55);
  sectionTitle(s, "Customers design with AI, not against it.", 0.7, 1.0);
  s.addText(
    "An AI Assistant rides along through every step — interpreting answers, suggesting hardware, generating diagrams, and explaining trade-offs in plain English.",
    {
      x: 0.7, y: 2.0, w: 11.9, h: 0.7,
      fontFace: FONT_BODY, fontSize: 14, color: BODY, lineSpacingMultiple: 1.4,
    }
  );

  // Left: Real screenshot of intake with AI Assistant
  const sx = 0.7, sy = 2.85, swPx = 5.6, shPx = 3.55;
  s.addShape("roundRect", {
    x: sx, y: sy, w: swPx, h: shPx,
    fill: { color: PAPER }, line: { color: LINE, width: 1 },
    rectRadius: 0.12,
  });
  // window chrome
  s.addShape("rect", {
    x: sx + 0.18, y: sy + 0.18, w: swPx - 0.36, h: 0.32,
    fill: { color: NAVY }, line: { type: "none" },
  });
  ["E64C4C", "F1B940", "4DAA59"].forEach((c, j) => {
    s.addShape("ellipse", {
      x: sx + 0.27 + j * 0.22, y: sy + 0.25, w: 0.16, h: 0.16,
      fill: { color: c }, line: { type: "none" },
    });
  });
  s.addImage({
    path: `${SHOTS}/intake.png`,
    x: sx + 0.18, y: sy + 0.5, w: swPx - 0.36, h: shPx - 0.7,
    sizing: { type: "cover", w: swPx - 0.36, h: shPx - 0.7 },
  });
  // small caption pin
  s.addText("Live AI Assistant in production today", {
    x: sx, y: sy + shPx + 0.1, w: swPx, h: 0.3,
    fontFace: FONT_BODY, fontSize: 11, italic: true, color: MUTED,
    align: "center", margin: 0,
  });

  // Right: 4-step AI flow with chips
  const flow = [
    {
      n: "1",
      t: "Answer in plain English",
      d: "Customer types or speaks their requirements. AI fills the structured form behind the scenes.",
    },
    {
      n: "2",
      t: "AI sizes the network",
      d: "Recommends AP, switch, router and security counts based on industry, headcount, square footage.",
    },
    {
      n: "3",
      t: "AI builds the topology",
      d: "Generates a Drawio network diagram from the BOM — placement, links, labels, all auto-laid-out.",
    },
    {
      n: "4",
      t: "AI explains and adjusts",
      d: "Customer can ask 'why this AP model?' or 'what if I add a second site?' and AI revises live.",
    },
  ];
  const flowX = 6.55, flowY = 2.85;
  const stepH = 0.95, stepGap = 0.05;
  flow.forEach((f, i) => {
    const y = flowY + i * (stepH + stepGap);
    // step number chip
    s.addShape("ellipse", {
      x: flowX, y: y + 0.1, w: 0.65, h: 0.65,
      fill: { color: MAGENTA }, line: { type: "none" },
    });
    s.addText(f.n, {
      x: flowX, y: y + 0.1, w: 0.65, h: 0.65,
      fontFace: FONT_HEAD, fontSize: 18, bold: true, color: "FFFFFF",
      align: "center", valign: "middle", margin: 0,
    });
    // connector line down (except last)
    if (i < flow.length - 1) {
      s.addShape("line", {
        x: flowX + 0.325, y: y + 0.75, w: 0, h: stepH + stepGap - 0.65,
        line: { color: LINE, width: 1.5, dashType: "dash" },
      });
    }
    // text block
    s.addText(f.t, {
      x: flowX + 0.85, y: y + 0.05, w: 5.7, h: 0.4,
      fontFace: FONT_HEAD, fontSize: 14, bold: true, color: INK, margin: 0,
    });
    s.addText(f.d, {
      x: flowX + 0.85, y: y + 0.45, w: 5.7, h: 0.55,
      fontFace: FONT_BODY, fontSize: 11.5, color: BODY,
      lineSpacingMultiple: 1.35, margin: 0,
    });
  });

  pageNumber(s, 9, TOTAL);
}

// ============================================================
// SLIDE 10 — MARKET (LIGHT, big stat slide)
// ============================================================
{
  const s = pres.addSlide();
  lightBackdrop(s);

  eyebrow(s, "MARKET", 0.7, 0.55);
  sectionTitle(s, "Built for the long tail.", 0.7, 1.0);

  // Big stat on the left
  s.addText("33.2M", {
    x: 0.7, y: 2.4, w: 6, h: 2.1,
    fontFace: FONT_HEAD, fontSize: 140, bold: true, color: MAGENTA, margin: 0,
  });
  s.addText("U.S. small businesses", {
    x: 0.7, y: 4.55, w: 6, h: 0.5,
    fontFace: FONT_HEAD, fontSize: 22, bold: true, color: INK, margin: 0,
  });
  s.addText(
    "Each one needs a network. Almost none of them have a dedicated network engineer.",
    {
      x: 0.7, y: 5.05, w: 6.0, h: 1.4,
      fontFace: FONT_BODY, fontSize: 13, color: BODY, lineSpacingMultiple: 1.4, margin: 0,
    }
  );

  // Right side — segment breakdown bars
  const segs = [
    { l: "Professional services (1–50)", v: 0.38, n: "12.6M" },
    { l: "Retail & hospitality", v: 0.22, n: "7.3M" },
    { l: "Healthcare & wellness", v: 0.14, n: "4.6M" },
    { l: "Trades & manufacturing", v: 0.18, n: "5.9M" },
    { l: "Other", v: 0.08, n: "2.8M" },
  ];

  s.addText("Wedge: under-served office segments", {
    x: 7.3, y: 2.4, w: 5.5, h: 0.4,
    fontFace: FONT_HEAD, fontSize: 14, bold: true, color: INK, margin: 0,
  });
  s.addText("Where a deterministic builder + AI consultant beats hiring an MSP.", {
    x: 7.3, y: 2.75, w: 5.5, h: 0.4,
    fontFace: FONT_BODY, fontSize: 11, color: BODY, margin: 0,
  });

  const barX = 7.3, barTop = 3.4, barFullW = 5.3, barH = 0.3, barGap = 0.55;
  segs.forEach((seg, i) => {
    const y = barTop + i * barGap;
    s.addText(seg.l, {
      x: barX, y, w: 4.0, h: 0.28,
      fontFace: FONT_BODY, fontSize: 12, color: INK, margin: 0,
    });
    s.addText(seg.n, {
      x: barX + 4.0, y, w: 1.3, h: 0.28,
      fontFace: FONT_HEAD, fontSize: 12, bold: true, color: MAGENTA,
      align: "right", margin: 0,
    });
    // bar track
    s.addShape("roundRect", {
      x: barX, y: y + 0.3, w: barFullW, h: barH,
      fill: { color: "E3E7EE" }, line: { type: "none" },
      rectRadius: 0.04,
    });
    // bar fill
    s.addShape("roundRect", {
      x: barX, y: y + 0.3, w: barFullW * seg.v, h: barH,
      fill: { color: MAGENTA }, line: { type: "none" },
      rectRadius: 0.04,
    });
  });

  pageNumber(s, 10, TOTAL);
}

// ============================================================
// SLIDE 11 — BUSINESS MODEL (LIGHT, 3 plan columns)
// ============================================================
{
  const s = pres.addSlide();
  lightBackdrop(s);

  eyebrow(s, "BUSINESS MODEL", 0.7, 0.55);
  sectionTitle(s, "Three ways we make money.", 0.7, 1.0);

  s.addText(
    "A SaaS subscription gets businesses planning. A marketplace fee captures procurement. Managed services lock in long-term recurring revenue.",
    {
      x: 0.7, y: 2.0, w: 11.9, h: 0.7,
      fontFace: FONT_BODY, fontSize: 15, color: BODY, lineSpacingMultiple: 1.4,
    }
  );

  const plans = [
    {
      tag: "STARTER",
      price: "Free",
      sub: "Self-serve",
      bullets: ["Business intake", "BOM preview", "Single design", "Community support"],
      featured: false,
    },
    {
      tag: "PRO",
      price: "$79",
      sub: "per office, per month",
      bullets: ["Unlimited designs & sites", "Vendor checkout & quotes", "Live topology export", "Email + chat support"],
      featured: true,
    },
    {
      tag: "ENTERPRISE",
      price: "Custom",
      sub: "Annual contract",
      bullets: ["Multi-tenant org accounts", "Managed services included", "Dedicated CSM + SLA", "On-prem Zabbix integration"],
      featured: false,
    },
  ];

  const pw = 4.0, ph = 4.0, pgap = 0.18, pStartX = 0.7, py = 2.95;
  plans.forEach((p, i) => {
    const x = pStartX + i * (pw + pgap);
    const featured = p.featured;
    s.addShape("roundRect", {
      x, y: py, w: pw, h: ph,
      fill: { color: featured ? NAVY : PAPER },
      line: { color: featured ? NAVY : LINE, width: featured ? 0 : 1 },
      rectRadius: 0.14,
    });
    if (featured) {
      // featured ribbon
      s.addShape("roundRect", {
        x: x + pw - 1.5, y: py - 0.2, w: 1.4, h: 0.4,
        fill: { color: MAGENTA }, line: { type: "none" },
        rectRadius: 0.06,
      });
      s.addText("MOST POPULAR", {
        x: x + pw - 1.5, y: py - 0.2, w: 1.4, h: 0.4,
        fontFace: FONT_HEAD, fontSize: 9, bold: true, color: "FFFFFF",
        align: "center", valign: "middle", charSpacing: 3, margin: 0,
      });
    }
    const labelColor = featured ? MAGENTA : MAGENTA;
    s.addText(p.tag, {
      x: x + 0.35, y: py + 0.3, w: pw - 0.7, h: 0.35,
      fontFace: FONT_HEAD, fontSize: 11, bold: true, color: labelColor,
      charSpacing: 4, margin: 0,
    });
    s.addText(p.price, {
      x: x + 0.35, y: py + 0.65, w: pw - 0.7, h: 1.0,
      fontFace: FONT_HEAD, fontSize: 44, bold: true,
      color: featured ? "FFFFFF" : INK, margin: 0,
    });
    s.addText(p.sub, {
      x: x + 0.35, y: py + 1.65, w: pw - 0.7, h: 0.3,
      fontFace: FONT_BODY, fontSize: 11,
      color: featured ? "CADCFC" : MUTED, margin: 0,
    });
    // divider
    s.addShape("line", {
      x: x + 0.35, y: py + 2.05, w: pw - 0.7, h: 0,
      line: { color: featured ? "2A3A56" : LINE, width: 1 },
    });
    p.bullets.forEach((b, bi) => {
      const by = py + 2.2 + bi * 0.36;
      s.addText("•", {
        x: x + 0.35, y: by, w: 0.2, h: 0.3,
        fontFace: FONT_HEAD, fontSize: 14, bold: true,
        color: MAGENTA, margin: 0,
      });
      s.addText(b, {
        x: x + 0.6, y: by, w: pw - 0.95, h: 0.3,
        fontFace: FONT_BODY, fontSize: 12,
        color: featured ? "FFFFFF" : INK, margin: 0,
      });
    });
  });

  pageNumber(s, 11, TOTAL);
}

// ============================================================
// SLIDE 12 — TRACTION & ROADMAP (LIGHT, timeline)
// ============================================================
{
  const s = pres.addSlide();
  lightBackdrop(s);

  eyebrow(s, "TRACTION & ROADMAP", 0.7, 0.55);
  sectionTitle(s, "Shipping fast, with a clear path.", 0.7, 1.0);

  // Top row of three KPIs
  const kpis = [
    { v: "v1.0", l: "Shipped Q1 2026 — full intake → BOM → diagram → cart" },
    { v: "120+", l: "Pilot offices currently designed in the system" },
    { v: "9", l: "Vendors active in the marketplace catalog" },
  ];
  kpis.forEach((k, i) => {
    const x = 0.7 + i * 4.05;
    s.addShape("roundRect", {
      x, y: 2.1, w: 3.85, h: 1.2,
      fill: { color: PAPER }, line: { color: LINE, width: 1 },
      rectRadius: 0.1,
    });
    s.addShape("rect", {
      x, y: 2.1, w: 0.08, h: 1.2,
      fill: { color: MAGENTA }, line: { type: "none" },
    });
    s.addText(k.v, {
      x: x + 0.3, y: 2.18, w: 3.4, h: 0.55,
      fontFace: FONT_HEAD, fontSize: 28, bold: true, color: INK, margin: 0,
    });
    s.addText(k.l, {
      x: x + 0.3, y: 2.7, w: 3.4, h: 0.55,
      fontFace: FONT_BODY, fontSize: 11, color: BODY, lineSpacingMultiple: 1.3, margin: 0,
    });
  });

  // Timeline
  s.addText("12-month roadmap", {
    x: 0.7, y: 3.7, w: 8, h: 0.4,
    fontFace: FONT_HEAD, fontSize: 16, bold: true, color: INK, margin: 0,
  });

  const tlY = 4.6;
  // Track line — inset so first/last labels stay on slide
  const tlStart = 1.95, tlEnd = 11.4;
  s.addShape("line", {
    x: tlStart, y: tlY + 0.2, w: tlEnd - tlStart, h: 0,
    line: { color: LINE, width: 2 },
  });

  const milestones = [
    { q: "Q2 '26", t: "Vendor onboarding flow", d: "Self-serve vendor portal + commission engine" },
    { q: "Q3 '26", t: "Live ops monitoring", d: "Zabbix integration generally available" },
    { q: "Q4 '26", t: "Multi-tenant orgs", d: "MSPs manage multiple customers from one console" },
    { q: "Q1 '27", t: "AI deployment runbook", d: "Auto-generate install scripts and configs from BOM" },
  ];
  const stepW = (tlEnd - tlStart) / (milestones.length - 1);
  milestones.forEach((m, i) => {
    const cx = tlStart + i * stepW;
    // dot
    s.addShape("ellipse", {
      x: cx - 0.18, y: tlY + 0.02, w: 0.36, h: 0.36,
      fill: { color: MAGENTA }, line: { color: "FFFFFF", width: 3 },
    });
    // quarter label above
    s.addText(m.q, {
      x: cx - 0.85, y: tlY - 0.5, w: 1.7, h: 0.3,
      fontFace: FONT_HEAD, fontSize: 11, bold: true, color: MAGENTA,
      align: "center", charSpacing: 2, margin: 0,
    });
    // title + desc below
    s.addText(m.t, {
      x: cx - 1.45, y: tlY + 0.55, w: 2.9, h: 0.5,
      fontFace: FONT_HEAD, fontSize: 13, bold: true, color: INK,
      align: "center", margin: 0,
    });
    s.addText(m.d, {
      x: cx - 1.45, y: tlY + 1.05, w: 2.9, h: 0.9,
      fontFace: FONT_BODY, fontSize: 10, color: BODY,
      align: "center", lineSpacingMultiple: 1.35, margin: 0,
    });
  });

  pageNumber(s, 12, TOTAL);
}

// ============================================================
// SLIDE 13 — COMPETITIVE LANDSCAPE (LIGHT, 2x2)
// ============================================================
{
  const s = pres.addSlide();
  lightBackdrop(s);

  eyebrow(s, "WHY WE WIN", 0.7, 0.55);
  sectionTitle(s, "Faster than an MSP, smarter than DIY.", 0.7, 1.0, INK, 12.5);

  const compares = [
    {
      h: "vs. Traditional MSP",
      d: "We deliver a finished BOM in minutes, not weeks. Customers stay in control instead of waiting for an account manager.",
    },
    {
      h: "vs. DIY (spreadsheets + reseller)",
      d: "Deterministic sizing prevents over-/under-buying. Customers don't need to learn networking jargon.",
    },
    {
      h: "vs. Vendor configurators",
      d: "We're vendor-agnostic. Best-fit hardware from a multi-vendor catalog, not whatever the rep is selling.",
    },
    {
      h: "vs. Generic AI chatbots",
      d: "We close the loop — AI doesn't just suggest, it generates a real BOM, real diagram and a real order.",
    },
  ];
  const cw = 6.05, ch = 2.05, cgap = 0.2;
  compares.forEach((c, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = 0.7 + col * (cw + cgap), y = 2.15 + row * (ch + cgap);
    s.addShape("roundRect", {
      x, y, w: cw, h: ch,
      fill: { color: PAPER }, line: { color: LINE, width: 1 },
      rectRadius: 0.12,
    });
    s.addShape("rect", {
      x, y, w: 0.1, h: ch,
      fill: { color: MAGENTA }, line: { type: "none" },
    });
    s.addText(c.h, {
      x: x + 0.45, y: y + 0.25, w: cw - 0.7, h: 0.5,
      fontFace: FONT_HEAD, fontSize: 16, bold: true, color: INK, margin: 0,
    });
    s.addText(c.d, {
      x: x + 0.45, y: y + 0.8, w: cw - 0.7, h: 1.15,
      fontFace: FONT_BODY, fontSize: 12.5, color: BODY, lineSpacingMultiple: 1.4, margin: 0,
    });
  });

  pageNumber(s, 13, TOTAL);
}

// ============================================================
// SLIDE 14 — TEAM (LIGHT)
// ============================================================
{
  const s = pres.addSlide();
  lightBackdrop(s);

  eyebrow(s, "THE TEAM", 0.7, 0.55);
  sectionTitle(s, "Operators who have shipped this before.", 0.7, 1.0, INK, 12.5);

  const team = [
    { i: "M",  n: "Muskan",    r: "AI Engineer & Co-Founder",   d: "Leads the AI pipeline — intake, sizing, topology synthesis. Previously AI engineer at Sensitek." },
    { i: "S",  n: "Co-founder", r: "Engineering",                d: "Full-stack platform, vendor marketplace and Zabbix monitoring integration." },
    { i: "P",  n: "Advisor",    r: "Product & GTM",              d: "Two-time SMB SaaS founder. Brings playbook for vendor onboarding and channel sales." },
  ];

  const tw = 4.0, th = 4.0, tgap = 0.2;
  team.forEach((p, i) => {
    const x = 0.7 + i * (tw + tgap);
    const y = 2.4;
    s.addShape("roundRect", {
      x, y, w: tw, h: th,
      fill: { color: PAPER }, line: { color: LINE, width: 1 },
      rectRadius: 0.14,
    });
    // big avatar circle
    s.addShape("ellipse", {
      x: x + tw / 2 - 0.85, y: y + 0.45, w: 1.7, h: 1.7,
      fill: { color: MAGENTA }, line: { type: "none" },
    });
    s.addText(p.i, {
      x: x + tw / 2 - 0.85, y: y + 0.45, w: 1.7, h: 1.7,
      fontFace: FONT_HEAD, fontSize: 50, bold: true, color: "FFFFFF",
      align: "center", valign: "middle", margin: 0,
    });
    s.addText(p.n, {
      x: x + 0.3, y: y + 2.3, w: tw - 0.6, h: 0.45,
      fontFace: FONT_HEAD, fontSize: 20, bold: true, color: INK,
      align: "center", margin: 0,
    });
    s.addText(p.r, {
      x: x + 0.3, y: y + 2.75, w: tw - 0.6, h: 0.35,
      fontFace: FONT_HEAD, fontSize: 12, bold: true, color: MAGENTA,
      align: "center", charSpacing: 2, margin: 0,
    });
    s.addText(p.d, {
      x: x + 0.3, y: y + 3.15, w: tw - 0.6, h: 0.85,
      fontFace: FONT_BODY, fontSize: 11, color: BODY,
      align: "center", lineSpacingMultiple: 1.4, margin: 0,
    });
  });

  pageNumber(s, 14, TOTAL);
}

// ============================================================
// SLIDE 15 — ASK / CLOSING (DARK)
// ============================================================
{
  const s = pres.addSlide();
  darkBackdrop(s);

  s.addText("THE ASK", {
    x: 0.7, y: 0.8, w: 8, h: 0.4,
    fontFace: FONT_HEAD, fontSize: 12, bold: true, color: MAGENTA, charSpacing: 6,
  });

  s.addText("Let's secure", {
    x: 0.7, y: 1.6, w: 12, h: 1.2,
    fontFace: FONT_HEAD, fontSize: 72, bold: true, color: "FFFFFF", margin: 0,
  });
  s.addText("10,000 offices together.", {
    x: 0.7, y: 2.7, w: 12, h: 1.2,
    fontFace: FONT_HEAD, fontSize: 72, bold: true, color: MAGENTA, margin: 0,
  });

  s.addText(
    "Raising a $3M seed to scale vendor onboarding, ship multi-tenant orgs, and reach 1,000 paying offices by year end.",
    {
      x: 0.7, y: 4.2, w: 11.9, h: 0.8,
      fontFace: FONT_BODY, fontSize: 16, color: "CADCFC", lineSpacingMultiple: 1.4,
    }
  );

  // Use of funds chips
  const uses = [
    { p: "45%", l: "Engineering & AI" },
    { p: "30%", l: "GTM & Vendor Ops" },
    { p: "15%", l: "Customer Success" },
    { p: "10%", l: "Reserves" },
  ];
  uses.forEach((u, i) => {
    const x = 0.7 + i * 3.05;
    const y = 5.3;
    s.addShape("roundRect", {
      x, y, w: 2.85, h: 1.0,
      fill: { color: NAVY_2 }, line: { color: "2A3A56", width: 1 },
      rectRadius: 0.1,
    });
    s.addText(u.p, {
      x: x + 0.25, y: y + 0.1, w: 2.4, h: 0.5,
      fontFace: FONT_HEAD, fontSize: 22, bold: true, color: MAGENTA, margin: 0,
    });
    s.addText(u.l, {
      x: x + 0.25, y: y + 0.55, w: 2.4, h: 0.4,
      fontFace: FONT_BODY, fontSize: 12, color: "CADCFC", margin: 0,
    });
  });

  // contact line
  s.addShape("line", {
    x: 0.7, y: 6.7, w: 11.9, h: 0,
    line: { color: "2A3A56", width: 1 },
  });
  s.addText("hello@secureaioffice.com", {
    x: 0.7, y: 6.85, w: 6, h: 0.4,
    fontFace: FONT_HEAD, fontSize: 13, bold: true, color: "FFFFFF", margin: 0,
  });
  s.addText("secureaioffice.com", {
    x: W - 4.7, y: 6.85, w: 4, h: 0.4,
    fontFace: FONT_HEAD, fontSize: 13, bold: true, color: MAGENTA,
    align: "right", margin: 0,
  });
}

// ---------- write ----------
pres.writeFile({ fileName: "/Users/muskan/SecureOffice2/docs/pitch/SecureAIOffice-Pitch.pptx" })
  .then((f) => console.log("Wrote:", f));
