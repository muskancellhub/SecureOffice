# SecureOffice2 Frontend

## Run

```bash
cd frontend
npm install
npm run dev
```

## Notes
- Access token stays in memory (`AuthContext`).
- Refresh token uses `httpOnly` cookie from backend.
- App auto-refreshes access token via `/auth/refresh`.

## SMB Network Calculator V1

Implemented in `src/calculator` as framework-agnostic TypeScript pure functions.

### Included in V1
- Indoor Wi-Fi AP estimation (coverage + capacity, takes max)
- Switch count estimation
- Rough CapEx estimation (hardware/license/cabling/labor/switch/UPS/markup/tax)
- Deterministic lookups and RF-lite indoor model
- Input validation and normalization
- Unit tests (`vitest`)

### Intentionally not included in V1
- Outdoor AP formulas
- DAS logic or DAS comparisons
- OpEx/TCO/DCF modeling
- Checkout, Stripe, XML/Draw.io generation, RAG, analytics, order routing/mailbox

### How to call
```ts
import { calculateNetworkEstimate } from './src/calculator';

const result = calculateNetworkEstimate(inputPayload);
```

### Sample input
```ts
const sampleInput = {
  businessType: 'QSR',
  environmentType: 'office',
  totalFloorAreaSqft: 12000,
  obstructionType: 'standard',
  wifiStandard: 'wifi6',
  totalUsers: 80,
  devicesPerUser: 1.5,
  throughputPerUserMbps: 4,
  redundancyEnabled: true,
  switchPorts: 24,
  upsRequired: true,
  pricing: {
    indoorAPPrice: 850,
    licensePrice: 120,
    cablingCostPerDrop: 180,
    laborHoursPerAP: 2,
    laborRate: 95,
    switchPrice: 1100,
    upsPrice: 450,
    markupPct: 15,
    taxPct: 8.25
  }
};
```

### Sample output (excerpt)
```ts
{
  counts: {
    coverageAPs: 2,
    capacityAPs: 2,
    indoorAPs: 2,
    indoorAPsFinal: 3,
    switchCount: 1
  },
  summary: {
    recommendedIndoorAPs: 3,
    recommendedSwitches: 1,
    estimatedCapEx: 6933.95
  }
}
```

## Retrieval-Ready Configuration Pipeline V1

Implemented in `src/suggestions` as framework-agnostic TypeScript modules.

### Developer Note (Current Flow)
- Existing deterministic calculator remains in `src/calculator`.
- New post-calculator pipeline lives in `src/suggestions` and plugs in after calculator output.
- Current flow:
  - calculator result + business context
  - retrieval-driven product suggestion
  - deterministic BOM generation
  - topology JSON generation
  - draw.io XML serialization
  - preview payload
  - mailbox handoff payload object (no SMTP send in V1)
- Assumption in V1: formulas/counts are deterministic inputs; retrieval and product ranking are modular and swappable.

### Included in V1
- Retrieval abstraction and local retriever:
  - `ProductRetriever`
  - `LocalInMemoryProductRetriever`
- Product suggestion/ranking:
  - `suggestAccessPoint`
  - `suggestSwitch`
  - `suggestGateway`
  - `suggestCellularBackup`
  - `suggestProducts`
- BOM generation:
  - `buildBomItems`
  - `calculateBomTotals`
- Topology + draw.io:
  - `generateTopologyFromBom`
  - `topologyToDrawioXml`
- Preview + mailbox payload assembly:
  - `buildPreviewPayload`
  - `buildMailboxOrderPayload`
- End-to-end orchestration:
  - `generateConfigurationPreviewAndOrderPayload`
- Usage sample:
  - `src/suggestions/exampleUsage.ts`
- Tests:
  - `src/suggestions/__tests__/suggestedBom.test.ts`

### Architecture note
- Formula/calculator arithmetic is deterministic and remains separate in `src/calculator`.
- Catalog retrieval and product ranking are isolated in `src/suggestions/retriever.ts` and `src/suggestions/suggestionEngine.ts`.
- Topology is generated before draw.io XML to keep rendering targets modular.
- V1 intentionally excludes real embeddings/vector DB infrastructure, SMTP sending, checkout/Stripe, and production workflow orchestration.

## Demo Design Workflow (Current)

Implemented lightweight demo flow pages on top of existing calculator/BOM/topology APIs:

- `src/pages/NetworkDesignBuilderPage.tsx`
  - reads calculator snapshot from local storage
  - generates BOM + topology/draw.io artifacts
  - captures lightweight lead data
  - saves draft or submits design
- `src/pages/DesignHistoryPage.tsx`
  - lists saved + submitted designs
  - shows status and summary metrics
- `src/pages/DesignDetailPage.tsx`
  - reopens saved design snapshots
  - shows customer-facing status detail, timeline, milestone cards, updates feed
  - includes install assistance placeholder (`self-install` / `remote_assistance` / `onsite_visit`)
  - supports submit from draft/reviewed and status tracking after submit
- `src/pages/AdminDesignSubmissionsPage.tsx`
  - lightweight ops/admin queue for manual status progression
  - supports posting internal/customer updates, milestone edits, install-plan edits
  - shows optional decomposition buckets mapped from BOM for demo operations flow

Routes added in `src/router/AppRouter.tsx`:
- `/shop/designs`
- `/shop/designs/new`
- `/shop/designs/:designId`
- `/shop/admin/design-submissions`

API methods added in `src/api/commerceApi.ts`:
- `generateNetworkBom`, `generateNetworkTopology`
- `saveNetworkDesign`, `submitNetworkDesign`
- `listNetworkDesigns`, `getNetworkDesign`
- `listOpsNetworkSubmissions`, `updateNetworkDesignStatus`
- `updateNetworkDesignMilestones`, `addNetworkDesignUpdate`, `updateNetworkDesignInstallAssistance`
