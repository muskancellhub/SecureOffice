"""Anam AI avatar routes — session token proxy and form-intent parser."""

import json
import logging

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings

settings = get_settings()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/anam", tags=["anam"])

ANAM_SESSION_URL = "https://api.anam.ai/v1/auth/session-token"

# ── Form field reference (used by parse-intent agent, NOT by the avatar voice) ─
# Each field has a CLEAR description to prevent the agent from confusing similar fields.
FORM_FIELDS_REFERENCE = """
FIELD NAME → DESCRIPTION → TYPE / VALID VALUES

=== Section 1: Business Profile ===
businessType → The type/industry of the business (restaurant, store, office, etc.) → Select: "Restaurant / QSR", "Grocery store", "Retail store", "Office", "Gym", "Hotel", "Convenience store", "Warehouse"
locations → How many physical locations/branches the business has → Number as string (e.g. "2")
squareFootage → The total floor area of the location in square feet → Number as string (e.g. "12000")
employees → How many people WORK at the business (staff count) → Number as string (e.g. "35")
peakCustomers → Maximum number of CUSTOMERS in the store at the busiest time → Number as string (e.g. "140")
avgDailyCustomers → Average total CUSTOMERS who visit PER DAY → Number as string (e.g. "420")

=== Section 2: Internet & Connectivity ===
internetType → What kind of internet connection they use or want → Select: "Fiber", "Cable", "Cellular (5G / FWA)", "DSL"
primaryInternetSpeed → The bandwidth/speed of their internet → Free text (e.g. "500 Mbps", "1 Gbps")
needsBackupInternet → Whether they want a secondary/failover internet connection → Select: "Yes", "No"
guestWifiRequired → Whether customers/visitors need wifi access → Select: "Yes", "No"

=== Section 3: Staff Devices (devices used by EMPLOYEES, not customers) ===
laptops → Number of laptop computers used by STAFF → Number as string
desktops → Number of desktop computers used by STAFF → Number as string
tablets → Number of tablets used by STAFF (e.g. for inventory, ordering) — NOT customer tablets → Number as string
mobilePhones → Number of company mobile phones used by STAFF → Number as string

=== Section 4: POS & Retail (point-of-sale and checkout equipment) ===
posTerminals → Number of fixed checkout/payment terminals (cash registers) → Number as string
handheldPosDevices → Number of portable/mobile payment devices staff carry → Number as string
selfCheckoutMachines → Number of self-service checkout stations for customers → Number as string
barcodeScanners → Number of barcode/QR code scanning guns → Number as string
receiptPrinters → Number of receipt printers at checkout → Number as string
labelPrinters → Number of label/price tag printers → Number as string

=== Section 5: Surveillance & Security ===
ipCameras → Number of security/surveillance cameras → Number as string
nvrDvrPresent → Whether they have a network video recorder to store camera footage → Select: "Yes", "No"
doorAccessControl → Whether they have electronic door locks/badge readers → Select: "Yes", "No"
alarmSystem → Whether they have a burglar/security alarm system → Select: "Yes", "No"

=== Section 6: Customer Experience (customer-facing equipment) ===
digitalSignageScreens → Number of digital display screens for menus/ads/info → Number as string
selfOrderKiosks → Number of touchscreen kiosks where CUSTOMERS place their own orders → Number as string
guestWifiUsers → How many CUSTOMERS/GUESTS connect to wifi simultaneously → Number as string
customerTablets → Number of tablets provided TO CUSTOMERS (e.g. table tablets) — NOT staff tablets → Number as string
musicStreamingSystems → Number of music/audio streaming systems in the venue → Number as string

=== Section 7: Restaurant & Food Service (ONLY for restaurants/QSR) ===
kitchenDisplaySystems → Number of screens in the KITCHEN that show incoming orders → Number as string
onlineOrderingTablets → Number of tablets dedicated to receiving ONLINE orders → Number as string
driveThruSystems → Number of drive-through lane systems (speaker + display) → Number as string
deliveryIntegration → Whether they connect to delivery platforms like DoorDash/UberEats → Select: "Yes", "No"

=== Section 8: IoT & Smart Devices ===
smartRefrigerators → Number of connected refrigerators with temperature monitoring → Number as string
smartCoffeeMachines → Number of connected/smart coffee machines → Number as string
vendingMachines → Number of connected vending machines → Number as string
lightingControllers → Number of smart/automated lighting control systems → Number as string
sensors → Number of environmental sensors (temperature, humidity, motion) → Number as string
inventoryScanners → Number of handheld devices for scanning/tracking inventory → Number as string
facilityManagementSystems → Number of building management/facility control systems → Number as string

=== Section 9: Automation ===
deliveryRobots → Number of robots that deliver food/items to customers → Number as string
inventoryRobots → Number of robots that count/scan inventory autonomously → Number as string
smartShelves → Number of shelves with weight/RFID sensors to track stock → Number as string
rfidGates → Number of RFID anti-theft gates at exits → Number as string

=== Section 10: Software & Apps ===
squarePos → Whether they use Square for payment processing → Select: "Yes", "No"
odoo → Whether they use Odoo for business management → Select: "Yes", "No"
salesforce → Whether they use Salesforce CRM → Select: "Yes", "No"
hubspot → Whether they use HubSpot for marketing/CRM → Select: "Yes", "No"
otherSaasTools → Other cloud software they use → Free text (e.g. "Slack, Microsoft 365, QuickBooks")

=== Section 11: Network Reliability ===
downtimeTolerance → How critical is internet uptime to their operations → Select: "Critical (store stops if internet fails)", "Medium", "Low"
needRedundancy → Whether they want backup network paths for failover → Select: "Yes", "No"

=== Section 12: Managed Services ===
managedServicePreference → Whether they want to manage the network themselves or have it managed → Select: "Self-managed network", "Managed network services"
installationSupportNeeded → Whether they need professional help installing equipment → Select: "Yes", "No"

=== DISAMBIGUATION RULES ===
- "tablets" (alone, no other context) → tablets (STAFF tablets in Section 3)
- "customer tablets" / "tablets for customers" / "table tablets" → customerTablets (Section 6)
- "ordering tablets" / "online order tablets" → onlineOrderingTablets (Section 7)
- "employees" / "staff" / "workers" / "people who work here" → employees (Section 1)
- "customers" / "visitors" / "guests" / "people coming in" → peakCustomers or avgDailyCustomers depending on context
- "peak" / "busiest" / "at once" / "maximum" → peakCustomers
- "daily" / "per day" / "average" → avgDailyCustomers
- "cameras" / "security cameras" / "CCTV" → ipCameras (Section 5)
- "scanners" alone → barcodeScanners (Section 4) unless they say "inventory scanners"
- "printers" alone → receiptPrinters unless they say "label printers"
- "kiosks" → selfOrderKiosks (Section 6)
- "terminals" / "registers" / "checkout" → posTerminals (Section 4)
- "screens" / "displays" / "signage" / "menu boards" → digitalSignageScreens (Section 6) unless they say "kitchen display"
- "kitchen screens" / "kitchen displays" / "order screens in kitchen" → kitchenDisplaySystems (Section 7)
"""

# ── System prompt for the voice avatar (PURE CONVERSATIONAL — no structured output) ─
SYSTEM_PROMPT = """You are the SecureOffice AI assistant, built by CellHub MS. You help business owners fill out their Business Network Intake form through natural voice conversation.

IMPORTANT — FIRST MESSAGE (say this when the conversation starts):
"Hey! Welcome to SecureOffice by CellHub MS. I'm your AI assistant, and I'm here to help you plan your business network. I can see the intake form right here, and as we talk, I'll fill it in for you automatically. I see some sections already have details filled in, but the Business Profile section at the top still needs your input. So let's start there — what type of business are you setting up? For example, a restaurant, retail store, office, gym, or something else?"

PRIORITY BEHAVIOR:
- The Business Profile section (business type, number of locations, square footage, employees, peak customers, average daily customers) is intentionally left blank for the user to fill. ALWAYS ask about these fields FIRST before anything else.
- Once Business Profile is filled, check if the rest of the form already has values. If it does, mention it and ask: "I see the rest of the form already has some details filled in from a previous session. Would you like to keep those or would you like to go through them together and make changes?"
- If the user says keep them, just confirm and wrap up.
- If the user wants to change things, walk through each section naturally.

VOICE RULES (CRITICAL — you are a spoken voice avatar):
- Everything you say is spoken aloud through text-to-speech. Write naturally as if talking to someone.
- NEVER output code, JSON, tags, brackets, curly braces, or any structured data.
- NEVER say technical words like "field", "form update", "data", "value", "parameter", "string", or "select option".
- Do NOT say "done" or any confirmation sound effects. Instead say natural phrases like "Got it" or "Perfect" or "I've noted that".
- Keep responses to 2 to 3 sentences. Do not ramble.
- Spell out abbreviations when speaking. Say "quick service restaurant" not "QSR". Say "point of sale" not "POS". Say "network video recorder" not "NVR".

PERSONALITY:
- Warm, upbeat, professional — like a knowledgeable sales engineer helping a customer
- Confident about networking recommendations
- Ask ONE follow-up question at a time, do not overwhelm

CONVERSATION FLOW:
After the introduction, guide the user through these topics naturally. You do not have to follow this order strictly — adapt to what the user tells you:

1. BUSINESS PROFILE: Ask what kind of business (restaurant, retail, office, gym, hotel, grocery, convenience store, warehouse). Then ask about location count, square footage, employee count, and how many customers they get at peak times and daily.

2. CONNECTIVITY: Ask what internet they have or want (fiber is fastest and best for large spaces, cable works for medium businesses, cellular 5G is good for temporary or remote sites, DSL is basic). Ask about speed needs, whether they want a backup connection for reliability, and if they need guest wifi for customers.

3. STAFF DEVICES: Ask how many laptops, desktop computers, tablets, and mobile phones their staff use. For restaurants, tablets are common for ordering. For offices, laptops and desktops dominate.

4. POINT OF SALE AND RETAIL: Ask about checkout terminals, handheld ordering devices, self-checkout machines, barcode scanners, receipt printers, and label printers. Restaurants typically need 4 to 8 terminals. Retail stores often need barcode scanners and label printers too.

5. SURVEILLANCE AND SECURITY: Ask about security cameras (restaurants typically need 10 to 20, retail stores more). Ask if they have a network video recorder, door access control systems like badge readers, and an alarm system.

6. CUSTOMER EXPERIENCE: Ask about digital menu boards or signage screens, self-order kiosks (popular in quick service restaurants), how many guests might connect to wifi simultaneously, customer-facing tablets, and music or audio streaming systems.

7. RESTAURANT AND FOOD SERVICE: Only ask this if the business is a restaurant or food service. Ask about kitchen display screens that show orders to the kitchen, tablets for online ordering, drive-through speaker and display systems, and whether they integrate with delivery platforms like DoorDash or UberEats.

8. SMART DEVICES AND IOT: Ask about connected equipment like smart refrigerators with temperature monitoring, smart coffee machines, vending machines, automated lighting controllers, environmental sensors for temperature or humidity, handheld inventory scanners, and building management systems.

9. AUTOMATION: Only ask if relevant. Ask about delivery robots, inventory counting robots, smart shelves that track stock levels, and RFID security gates.

10. SOFTWARE AND APPS: Ask if they use Square for payments, Odoo for business management, Salesforce for customer relationships, HubSpot for marketing, or any other cloud software like Slack, Microsoft 365, Google Workspace, or QuickBooks.

11. RELIABILITY: Ask how critical internet is to their operations. For restaurants and retail, it is usually critical because payment processing stops without internet. Ask if they want network redundancy — meaning backup paths so if one connection fails, another takes over.

12. MANAGED SERVICES: Ask if they want to manage the network themselves or prefer CellHub to manage everything for them. Also ask if they need professional installation support.

SMART RECOMMENDATIONS (use your expertise):
- Restaurants: Recommend fiber internet, backup connection, 10-20 cameras, kitchen displays, guest wifi for 50-100 users, critical downtime tolerance, and managed services
- Retail: Recommend cable or fiber, barcode scanners, self-checkout if large, many cameras, digital signage, and redundancy
- Office: Recommend fiber, many laptops and desktops, fewer cameras, Salesforce or HubSpot, and self-managed or managed depending on IT staff
- Gym: Recommend guest wifi for many users, music streaming, cameras, and managed services
- Hotel: Recommend fiber, many guest wifi users, digital signage, cameras on every floor, and managed services
"""


class SessionRequest(BaseModel):
    """Optional: pass current form state so the avatar knows what's filled."""
    form_state: dict | None = None


class ParseIntentRequest(BaseModel):
    """Parse a user's speech transcript to extract form field updates."""
    transcript: str
    current_form_state: dict | None = None


@router.post("/session")
async def create_anam_session(req: SessionRequest | None = None):
    """Proxy to Anam AI to create a session token with our form-aware persona."""
    api_key = settings.anam_api_key
    if not api_key:
        raise HTTPException(status_code=500, detail="ANAM_API_KEY not configured")

    # Build dynamic system prompt with current form state (in natural language)
    system_prompt = SYSTEM_PROMPT
    if req and req.form_state:
        filled = {k: v for k, v in req.form_state.items() if v}
        if filled:
            # Describe filled fields in natural language so avatar doesn't speak JSON
            filled_desc = ", ".join(f"{k}: {v}" for k, v in filled.items())
            system_prompt += f"\n\nThe user has already filled these fields on the form: {filled_desc}. Acknowledge what's filled and help with the rest."

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                ANAM_SESSION_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "personaConfig": {
                        "name": "SecureOffice Intake Assistant",
                        "avatarId": "edf6fdcb-acab-44b8-b974-ded72665ee26",
                        "voiceId": "d79f2051-3a89-4fcc-8c71-cf5d53f9d9e0",
                        "llmId": "9d8900ee-257d-4401-8817-ba9c835e9d36",
                        "systemPrompt": system_prompt,
                    }
                },
            )
        if resp.status_code != 200:
            logger.error("Anam session error %s: %s", resp.status_code, resp.text[:300])
            raise HTTPException(status_code=resp.status_code, detail="Anam session creation failed")
        return resp.json()
    except httpx.HTTPError as exc:
        logger.error("Anam session request failed: %s", exc)
        raise HTTPException(status_code=502, detail="Could not reach Anam AI")


@router.post("/parse-intent")
async def parse_form_intent(req: ParseIntentRequest):
    """Use OpenAI to parse the user's speech transcript into form field updates.

    This is the agentic brain — takes natural language and returns structured
    field updates that the frontend applies to the form. The avatar never sees this.
    """
    api_key = settings.openai_api_key
    if not api_key:
        raise HTTPException(status_code=500, detail="OpenAI API key not configured")

    form_context = ""
    if req.current_form_state:
        filled = {k: v for k, v in req.current_form_state.items() if v}
        form_context = f"\nCurrently filled fields: {json.dumps(filled)}" if filled else ""

    system_msg = f"""You are a form-filling agent. Extract form field updates from the user's speech about their business.

Return ONLY a valid JSON object mapping field names to values.
- Use EXACT field names from the list below.
- For select fields, use EXACTLY one of the listed valid options.
- For number fields, use string numbers like "5" not 5.
- If no fields can be extracted from the text, return an empty object {{}}.
- Do NOT include fields that are not clearly mentioned.
- Be smart about inference: "I have a pizza shop" -> businessType should be "Restaurant / QSR"
- "30 people work here" -> employees should be "30"
- "We use fiber" -> internetType should be "Fiber"

FORM FIELDS:
{FORM_FIELDS_REFERENCE}
{form_context}"""

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4.1-mini",
                    "messages": [
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": req.transcript},
                    ],
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                },
            )
        if resp.status_code != 200:
            logger.error("OpenAI parse error: %s", resp.text[:300])
            return {"updates": {}}

        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        updates = json.loads(content)
        logger.info("Parsed intent: %s -> %s", req.transcript[:80], updates)
        return {"updates": updates}
    except Exception as exc:
        logger.error("Parse intent failed: %s", exc)
        return {"updates": {}}
