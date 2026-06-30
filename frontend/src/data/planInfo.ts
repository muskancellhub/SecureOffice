/** Carousel slide content for the public home-page plan info modals.
 * Keyed by the seeded bundle SKU. Static (this is a pre-auth page). */

export interface PlanSlide {
  title: string;
  subtitle?: string;
  bullets?: string[];
  sections?: { heading: string; items: string[] }[];
  table?: { columns: string[]; rows: string[][] };
}

const POTS_SLIDES: PlanSlide[] = [
  {
    title: 'POTS-in-a-Box™',
    subtitle: 'Modernizing critical communications infrastructure',
    bullets: [
      'Managed life-safety & emergency communications',
      'Powered exclusively by T-Mobile 5G & T-Priority',
      'Transforms legacy analog into a cloud-managed service — not a telecom replacement',
    ],
  },
  {
    title: 'Why organizations need a new approach',
    subtitle: 'Copper is being retired — the regulated systems on it are not',
    bullets: [
      'Carriers phase out POTS, T1 and dial lines',
      'Discontinuance surcharges keep escalating',
      'Fire, elevator and healthcare codes remain unchanged',
      'No central health or status visibility',
      'Growing outage risk on regulated systems',
    ],
  },
  {
    title: 'What is POTS-in-a-Box™?',
    subtitle: 'Five integrated capabilities, delivered as one managed service',
    bullets: [
      'Connectivity — T-Mobile 5G + T-Priority support',
      'Power Protection — integrated battery backup',
      'Analog Communications — multi-port life-safety support',
      'Cloud Management — monitoring, provisioning & diagnostics',
      'Managed Services — 24×7 monitoring, incident & lifecycle',
    ],
  },
  {
    title: 'Supported critical applications',
    subtitle: 'Regulated analog you cannot afford to lose',
    sections: [
      { heading: 'Life Safety', items: ['Fire alarm communications', 'Elevator emergency phones', 'Area-of-refuge phones', 'Emergency call stations'] },
      { heading: 'Security', items: ['Alarm panels', 'Access control systems', 'Gate entry systems'] },
      { heading: 'Healthcare', items: ['Nurse call systems', 'Medical alert systems', 'Fax communications'] },
      { heading: 'Facilities', items: ['Building management systems', 'Intercom systems', 'Environmental monitoring'] },
    ],
  },
  {
    title: 'Cloud Command Center',
    subtitle: 'One pane of glass for every regulated endpoint',
    sections: [
      { heading: 'Monitor', items: ['Device status & availability', 'Battery health', 'Signal strength', 'Alarm conditions'] },
      { heading: 'Control', items: ['Device provisioning', 'Firmware updates', 'Policy administration'] },
      { heading: 'Analyze', items: ['Historical performance', 'Compliance reports', 'SLA reporting', 'Asset lifecycle'] },
    ],
  },
  {
    title: 'Compliance, resiliency & T-Priority',
    subtitle: 'A continuous critical communications path',
    bullets: [
      'Business continuity with failover and battery backup',
      'Proactive 24×7 NOC incident management',
      'Audit-ready compliance evidence, generated automatically',
      'T-Priority network-level resiliency on T-Mobile 5G',
    ],
  },
  {
    title: 'Why CellhubMS POTS-in-a-Box™',
    subtitle: 'An executive-grade critical communications platform',
    bullets: [
      'Critical communications infrastructure — not a telecom replacement',
      'Nationwide T-Mobile 5G connectivity with T-Priority support',
      'Cloud monitoring & visibility — every endpoint, every site',
      '24×7 CellhubMS managed services own the incident lifecycle',
      'Compliance & lifecycle management built in by design',
    ],
  },
];

const MULTILINE_SLIDES: PlanSlide[] = [
  {
    title: 'MultiLine',
    subtitle: 'Enterprise mobile identity & secure business communications',
    bullets: [
      'A dedicated business number on your own phone (BYOD)',
      'Voice, SMS/MMS, WhatsApp & Microsoft Teams',
      'Compliance capture, analytics and central administration',
    ],
  },
  {
    title: 'Core MultiLine services',
    table: {
      columns: ['Service', 'Description', 'Typical Use Case'],
      rows: [
        ['Business Voice', 'Dedicated business number', 'Sales, support, executives'],
        ['Business SMS', 'Secure business texting', 'Customer communication'],
        ['MMS', 'Images and attachments', 'Field service, healthcare'],
        ['Voicemail', 'Separate business voicemail', 'BYOD deployments'],
        ['Call Recording', 'Compliance recording', 'Finance, healthcare'],
        ['SMS Archiving', 'Regulatory compliance', 'Banking, insurance'],
        ['WhatsApp Integration', 'Business WhatsApp with capture', 'International customer engagement'],
        ['Microsoft Teams Integration', 'Mobile identity within Teams', 'Hybrid workforce'],
        ['CRM Integration', 'Logging into CRM systems', 'Salesforce, customer support'],
        ['Analytics', 'Call, SMS, usage reporting', 'Operations management'],
        ['Administration Portal', 'User and number management', 'Enterprise IT'],
      ],
    },
  },
  {
    title: 'BYOD — Bring Your Own Device',
    bullets: [
      'Personal phone remains private',
      'Business receives its own number',
      'No second handset required',
      'No physical SIM swap',
    ],
    sections: [
      { heading: 'Ideal for', items: ['Sales teams', 'Executives', 'Healthcare workers', 'Retail managers'] },
    ],
  },
  {
    title: 'Secure Communications',
    subtitle: 'Enterprise security and audit capabilities across every channel',
    bullets: ['Voice', 'SMS', 'MMS', 'WhatsApp', 'Microsoft Teams messaging'],
  },
  {
    title: 'Compliance',
    subtitle: 'Built for regulated industries — SEC, FINRA, HIPAA, GDPR',
    sections: [
      { heading: 'Features include', items: ['Automatic recording', 'Message capture', 'Audit trail', 'eDiscovery', 'Archiving integration'] },
    ],
  },
];

const SMB_SLIDES: PlanSlide[] = [
  {
    title: 'SMB Office Bundle',
    subtitle: 'A complete small-office stack in one bundle',
    bullets: [
      'Network, Wi-Fi, AI and security — ready to deploy',
      'One bundle, one price',
    ],
  },
  {
    title: "What's included",
    bullets: [
      'SMB network device (managed gateway)',
      'Wi-Fi Access Point (AP) device',
      'AI edge device',
      'Security AI — small office offer',
    ],
  },
  {
    title: 'Why the SMB bundle',
    bullets: [
      'Everything a small office needs, pre-integrated',
      'Managed and monitored as one service',
      'Scales as your office grows',
    ],
  },
];

export const PLAN_SLIDES: Record<string, PlanSlide[]> = {
  'DISC-POTS-IN-A-BOX': POTS_SLIDES,
  'DISC-MOBILITY': MULTILINE_SLIDES,
  'DISC-SMB': SMB_SLIDES,
};
