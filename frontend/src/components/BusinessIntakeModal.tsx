import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  Lock,
  MessageSquare,
  Send,
  Sparkles,
  Unlock,
  Video,
  X,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import {
  EnvironmentType,
  NetworkCalculatorInput,
  ObstructionType,
  WifiStandard,
  calculateNetworkEstimate,
} from '../calculator';
import { intakeChat, IntakeChatMessage } from '../api/intakeChatApi';
import { AnamAvatar, AnamAvatarHandle } from './AnamAvatar';

/* ------------------------------------------------------------------ */
/* Shared types & constants (mirrors BusinessIntakePage)               */
/* ------------------------------------------------------------------ */

interface IntakeFormData {
  businessType: string;
  locations: string;
  squareFootage: string;
  employees: string;
  peakCustomers: string;
  avgDailyCustomers: string;
  internetType: string;
  primaryInternetSpeed: string;
  needsBackupInternet: string;
  guestWifiRequired: string;
  laptops: string;
  desktops: string;
  tablets: string;
  mobilePhones: string;
  posTerminals: string;
  handheldPosDevices: string;
  selfCheckoutMachines: string;
  barcodeScanners: string;
  receiptPrinters: string;
  labelPrinters: string;
  ipCameras: string;
  nvrDvrPresent: string;
  doorAccessControl: string;
  alarmSystem: string;
  digitalSignageScreens: string;
  selfOrderKiosks: string;
  guestWifiUsers: string;
  customerTablets: string;
  musicStreamingSystems: string;
  kitchenDisplaySystems: string;
  onlineOrderingTablets: string;
  driveThruSystems: string;
  deliveryIntegration: string;
  smartRefrigerators: string;
  smartCoffeeMachines: string;
  vendingMachines: string;
  lightingControllers: string;
  sensors: string;
  inventoryScanners: string;
  facilityManagementSystems: string;
  deliveryRobots: string;
  inventoryRobots: string;
  smartShelves: string;
  rfidGates: string;
  squarePos: string;
  odoo: string;
  salesforce: string;
  hubspot: string;
  otherSaasTools: string;
  downtimeTolerance: string;
  needRedundancy: string;
  managedServicePreference: string;
  installationSupportNeeded: string;
}

const INTAKE_STORAGE_KEY = 'secureOfficeBusinessIntake';
const CALCULATOR_RESULT_STORAGE_KEY = 'secureOfficeNetworkEstimateV1';
const CALCULATOR_INPUT_STORAGE_KEY = 'secureOfficeNetworkEstimateInputV1';

const BUSINESS_TYPE_OPTIONS = [
  'Restaurant / QSR',
  'Grocery store',
  'Retail store',
  'Office',
  'Gym',
  'Hotel',
  'Convenience store',
  'Warehouse',
];

const INTERNET_TYPE_OPTIONS = ['Fiber', 'Cable', 'Cellular (5G / FWA)', 'DSL'];
const YES_NO_OPTIONS = ['Yes', 'No'];
const DOWNTIME_OPTIONS = ['Critical (store stops if internet fails)', 'Medium', 'Low'];
const MANAGED_OPTIONS = ['Self-managed network', 'Managed network services'];

const DEFAULT_PRICING: NetworkCalculatorInput['pricing'] = {
  indoorAPPrice: 850,
  licensePrice: 120,
  cablingCostPerDrop: 180,
  laborHoursPerAP: 2,
  laborRate: 95,
  switchPrice: 1100,
  upsPrice: 450,
  markupPct: 15,
  taxPct: 8.25,
};

const asNonNegative = (value: string, fallback = 0): number => {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) return fallback;
  return parsed;
};

const inferEnvironmentType = (businessType: string): EnvironmentType => {
  if (businessType === 'Warehouse') return 'warehouse';
  return 'office';
};

const inferObstructionType = (businessType: string): ObstructionType => {
  if (businessType === 'Warehouse') return 'open';
  return 'standard';
};

const inferWifiStandard = (internetType: string): WifiStandard => {
  if (internetType === 'Fiber') return 'wifi6e';
  if (internetType === 'Cellular (5G / FWA)') return 'wifi6';
  return 'wifi6';
};

const createDummyIntakeData = (): IntakeFormData => ({
  businessType: '',
  locations: '',
  squareFootage: '',
  employees: '',
  peakCustomers: '',
  avgDailyCustomers: '',
  internetType: 'Fiber',
  primaryInternetSpeed: '1 Gbps',
  needsBackupInternet: 'Yes',
  guestWifiRequired: 'Yes',
  laptops: '8',
  desktops: '6',
  tablets: '10',
  mobilePhones: '20',
  posTerminals: '6',
  handheldPosDevices: '4',
  selfCheckoutMachines: '2',
  barcodeScanners: '8',
  receiptPrinters: '6',
  labelPrinters: '2',
  ipCameras: '18',
  nvrDvrPresent: 'Yes',
  doorAccessControl: 'Yes',
  alarmSystem: 'Yes',
  digitalSignageScreens: '5',
  selfOrderKiosks: '3',
  guestWifiUsers: '90',
  customerTablets: '0',
  musicStreamingSystems: '1',
  kitchenDisplaySystems: '3',
  onlineOrderingTablets: '2',
  driveThruSystems: '1',
  deliveryIntegration: 'Yes',
  smartRefrigerators: '2',
  smartCoffeeMachines: '1',
  vendingMachines: '0',
  lightingControllers: '1',
  sensors: '10',
  inventoryScanners: '4',
  facilityManagementSystems: '1',
  deliveryRobots: '0',
  inventoryRobots: '0',
  smartShelves: '0',
  rfidGates: '0',
  squarePos: 'Yes',
  odoo: 'No',
  salesforce: 'No',
  hubspot: 'Yes',
  otherSaasTools: 'Slack, Microsoft 365',
  downtimeTolerance: 'Critical (store stops if internet fails)',
  needRedundancy: 'Yes',
  managedServicePreference: 'Managed network services',
  installationSupportNeeded: 'Yes',
});

/* ------------------------------------------------------------------ */
/* Advanced section definitions (sections 2-12)                        */
/* ------------------------------------------------------------------ */

interface FieldDef {
  key: keyof IntakeFormData;
  label: string;
  type: 'number' | 'select' | 'text';
  options?: string[];
}

interface SectionDef {
  title: string;
  fields: FieldDef[];
}

const ADVANCED_SECTIONS: SectionDef[] = [
  {
    title: 'Connectivity Requirements',
    fields: [
      { key: 'internetType', label: 'Internet type', type: 'select', options: INTERNET_TYPE_OPTIONS },
      { key: 'primaryInternetSpeed', label: 'Primary speed', type: 'text' },
      { key: 'needsBackupInternet', label: 'Backup internet', type: 'select', options: YES_NO_OPTIONS },
      { key: 'guestWifiRequired', label: 'Guest Wi-Fi required?', type: 'select', options: YES_NO_OPTIONS },
    ],
  },
  {
    title: 'Staff Devices',
    fields: [
      { key: 'laptops', label: 'Laptops', type: 'number' },
      { key: 'desktops', label: 'Desktop computers', type: 'number' },
      { key: 'tablets', label: 'Tablets', type: 'number' },
      { key: 'mobilePhones', label: 'Mobile phones', type: 'number' },
    ],
  },
  {
    title: 'POS & Retail Systems',
    fields: [
      { key: 'posTerminals', label: 'POS terminals', type: 'number' },
      { key: 'handheldPosDevices', label: 'Handheld POS devices', type: 'number' },
      { key: 'selfCheckoutMachines', label: 'Self-checkout machines', type: 'number' },
      { key: 'barcodeScanners', label: 'Barcode scanners', type: 'number' },
      { key: 'receiptPrinters', label: 'Receipt printers', type: 'number' },
      { key: 'labelPrinters', label: 'Label printers', type: 'number' },
    ],
  },
  {
    title: 'Surveillance & Security',
    fields: [
      { key: 'ipCameras', label: 'IP cameras', type: 'number' },
      { key: 'nvrDvrPresent', label: 'NVR / DVR present', type: 'select', options: YES_NO_OPTIONS },
      { key: 'doorAccessControl', label: 'Door access control', type: 'select', options: YES_NO_OPTIONS },
      { key: 'alarmSystem', label: 'Alarm system', type: 'select', options: YES_NO_OPTIONS },
    ],
  },
  {
    title: 'Customer Experience',
    fields: [
      { key: 'digitalSignageScreens', label: 'Digital signage screens', type: 'number' },
      { key: 'selfOrderKiosks', label: 'Self-order kiosks', type: 'number' },
      { key: 'guestWifiUsers', label: 'Guest Wi-Fi users', type: 'number' },
      { key: 'customerTablets', label: 'Customer tablets', type: 'number' },
      { key: 'musicStreamingSystems', label: 'Music / audio systems', type: 'number' },
    ],
  },
  {
    title: 'Restaurant / QSR Systems',
    fields: [
      { key: 'kitchenDisplaySystems', label: 'Kitchen display systems', type: 'number' },
      { key: 'onlineOrderingTablets', label: 'Online ordering tablets', type: 'number' },
      { key: 'driveThruSystems', label: 'Drive-thru systems', type: 'number' },
      { key: 'deliveryIntegration', label: 'Delivery integration', type: 'select', options: YES_NO_OPTIONS },
    ],
  },
  {
    title: 'IoT & Smart Devices',
    fields: [
      { key: 'smartRefrigerators', label: 'Smart refrigerators', type: 'number' },
      { key: 'smartCoffeeMachines', label: 'Smart coffee machines', type: 'number' },
      { key: 'vendingMachines', label: 'Vending machines', type: 'number' },
      { key: 'lightingControllers', label: 'Lighting controllers', type: 'number' },
      { key: 'sensors', label: 'Sensors', type: 'number' },
      { key: 'inventoryScanners', label: 'Inventory scanners', type: 'number' },
      { key: 'facilityManagementSystems', label: 'Facility management', type: 'number' },
    ],
  },
  {
    title: 'Advanced Automation',
    fields: [
      { key: 'deliveryRobots', label: 'Delivery robots', type: 'number' },
      { key: 'inventoryRobots', label: 'Inventory robots', type: 'number' },
      { key: 'smartShelves', label: 'Smart shelves', type: 'number' },
      { key: 'rfidGates', label: 'RFID gates', type: 'number' },
    ],
  },
  {
    title: 'Applications / SaaS',
    fields: [
      { key: 'squarePos', label: 'Square POS', type: 'select', options: YES_NO_OPTIONS },
      { key: 'odoo', label: 'Odoo', type: 'select', options: YES_NO_OPTIONS },
      { key: 'salesforce', label: 'Salesforce', type: 'select', options: YES_NO_OPTIONS },
      { key: 'hubspot', label: 'HubSpot', type: 'select', options: YES_NO_OPTIONS },
      { key: 'otherSaasTools', label: 'Other SaaS tools', type: 'text' },
    ],
  },
  {
    title: 'Network Reliability',
    fields: [
      { key: 'downtimeTolerance', label: 'Downtime tolerance', type: 'select', options: DOWNTIME_OPTIONS },
      { key: 'needRedundancy', label: 'Need redundancy?', type: 'select', options: YES_NO_OPTIONS },
    ],
  },
  {
    title: 'Managed Services',
    fields: [
      { key: 'managedServicePreference', label: 'Network ownership', type: 'select', options: MANAGED_OPTIONS },
      { key: 'installationSupportNeeded', label: 'Installation support', type: 'select', options: YES_NO_OPTIONS },
    ],
  },
];

/* ------------------------------------------------------------------ */
/* Typewriter component                                                */
/* ------------------------------------------------------------------ */

const TypewriterText = ({ text, speed = 14, onTick }: { text: string; speed?: number; onTick?: () => void }) => {
  const [displayed, setDisplayed] = useState('');
  const [done, setDone] = useState(false);

  useEffect(() => {
    setDisplayed('');
    setDone(false);
    let i = 0;
    const timer = setInterval(() => {
      i++;
      setDisplayed(text.slice(0, i));
      onTick?.();
      if (i >= text.length) {
        clearInterval(timer);
        setDone(true);
      }
    }, speed);
    return () => clearInterval(timer);
  }, [text, speed]);

  const content = done ? text : displayed;
  return (
    <>
      {content.split('\n').map((line, idx) => (
        <p key={idx}>{line || '\u00A0'}</p>
      ))}
    </>
  );
};

/* ------------------------------------------------------------------ */
/* Welcome message                                                     */
/* ------------------------------------------------------------------ */

const WELCOME_MESSAGE: IntakeChatMessage = {
  role: 'assistant',
  content: `Hi! I'm your Secure AI Office assistant.\n\nTell me about your business and I'll design a complete network solution — hardware bill of materials, topology diagram, quotes, and lifecycle tracking.\n\nWhat type of business are you planning for, and how many locations and employees do you have?`,
};

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

type IntakeMode = 'select' | 'chat' | 'avatar';

interface Props {
  open: boolean;
  onClose: () => void;
}

export const BusinessIntakeModal = ({ open, onClose }: Props) => {
  const navigate = useNavigate();
  const { user } = useAuth();

  const [intakeData, setIntakeData] = useState<IntakeFormData>(() => {
    try {
      const saved = localStorage.getItem(INTAKE_STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        return { ...createDummyIntakeData(), ...parsed };
      }
    } catch {
      /* ignore */
    }
    return createDummyIntakeData();
  });

  const [messages, setMessages] = useState<IntakeChatMessage[]>([WELCOME_MESSAGE]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [advancedUnlocked, setAdvancedUnlocked] = useState(false);
  const [advancedStep, setAdvancedStep] = useState(0);
  const [highlightedFields, setHighlightedFields] = useState<Record<string, boolean>>({});
  const [mode, setMode] = useState<IntakeMode>('select');

  const messagesRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const avatarRef = useRef<AnamAvatarHandle>(null);
  const prevMsgCountRef = useRef(1); // starts at 1 because of welcome message

  /* --- lock body scroll when modal is open --- */
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  /* --- focus the chat input whenever mode switches to chat --- */
  useEffect(() => {
    if (open && mode === 'chat' && inputRef.current) {
      const timer = setTimeout(() => inputRef.current?.focus(), 300);
      return () => clearTimeout(timer);
    }
  }, [open, mode]);

  /* --- auto-scroll chat to bottom --- */
  const scrollChatToBottom = useCallback(() => {
    if (messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
    }
  }, []);

  useEffect(() => {
    scrollChatToBottom();
  }, [messages, chatLoading, scrollChatToBottom]);

  /* --- escape key closes modal --- */
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open]);

  /* --- field update helpers --- */
  const updateIntakeField = useCallback(
    <K extends keyof IntakeFormData>(key: K, value: IntakeFormData[K]) => {
      setIntakeData((prev) => ({ ...prev, [key]: value }));
    },
    [],
  );

  const highlightField = useCallback((key: string) => {
    setHighlightedFields((prev) => ({ ...prev, [key]: true }));
    setTimeout(() => {
      setHighlightedFields((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
    }, 3500);
  }, []);

  /* --- handle avatar form updates (same pattern as BusinessIntakePage) --- */
  const handleAvatarFormUpdate = useCallback(
    (updates: Record<string, string>) => {
      Object.entries(updates).forEach(([key, value]) => {
        if (key in intakeData) {
          updateIntakeField(key as keyof IntakeFormData, value as string);
          highlightField(key);
        }
      });
    },
    [intakeData, updateIntakeField, highlightField],
  );

  /* --- send chat message --- */
  const sendMessage = async (e: FormEvent) => {
    e.preventDefault();
    const text = chatInput.trim();
    if (!text || chatLoading) return;

    const nextMessages: IntakeChatMessage[] = [
      ...messages,
      { role: 'user', content: text },
    ];
    setMessages(nextMessages);
    prevMsgCountRef.current = nextMessages.length;
    setChatInput('');
    setChatLoading(true);

    try {
      const currentFields = {
        businessType: intakeData.businessType,
        locations: intakeData.locations,
        squareFootage: intakeData.squareFootage,
        employees: intakeData.employees,
        peakCustomers: intakeData.peakCustomers,
        avgDailyCustomers: intakeData.avgDailyCustomers,
      };
      const res = await intakeChat({
        message: text,
        history: nextMessages,
        current_fields: currentFields,
      });

      setMessages((prev) => {
        prevMsgCountRef.current = prev.length + 1;
        return [...prev, { role: 'assistant', content: res.answer }];
      });

      if (res.extracted && typeof res.extracted === 'object') {
        Object.entries(res.extracted).forEach(([key, value]) => {
          if (!(key in intakeData)) return;
          updateIntakeField(key as keyof IntakeFormData, String(value));
          highlightField(key);
        });
      }
    } catch (err) {
      setMessages((prev) => {
        prevMsgCountRef.current = prev.length + 1;
        return [
          ...prev,
          {
            role: 'assistant',
            content:
              "Sorry, I couldn't reach the AI right now. You can still fill out the form on the right manually.",
          },
        ];
      });
    } finally {
      setChatLoading(false);
    }
  };

  /* --- close handler (disconnect avatar if active) --- */
  const handleClose = useCallback(() => {
    if (mode === 'avatar') {
      avatarRef.current?.disconnect();
    }
    onClose();
  }, [mode, onClose]);

  /* --- submit the intake form --- */
  const handleSubmit = () => {
    localStorage.setItem(INTAKE_STORAGE_KEY, JSON.stringify(intakeData));

    const employees = asNonNegative(intakeData.employees, 15);
    const peakCustomers = asNonNegative(intakeData.peakCustomers, 30);
    const guestWifiUsers = asNonNegative(intakeData.guestWifiUsers, 0);
    const totalUsers = Math.max(
      1,
      employees + Math.max(guestWifiUsers, peakCustomers * 0.35),
    );

    const calculatorInput: NetworkCalculatorInput = {
      businessType: intakeData.businessType || 'Office',
      environmentType: inferEnvironmentType(intakeData.businessType),
      totalFloorAreaSqft: Math.max(1, asNonNegative(intakeData.squareFootage, 12000)),
      obstructionType: inferObstructionType(intakeData.businessType),
      wifiStandard: inferWifiStandard(intakeData.internetType),
      totalUsers,
      devicesPerUser: 1.5,
      throughputPerUserMbps: 4,
      redundancyEnabled: intakeData.needRedundancy === 'Yes',
      switchPorts: 24,
      upsRequired:
        intakeData.needRedundancy === 'Yes' || intakeData.needsBackupInternet === 'Yes',
      pricing: DEFAULT_PRICING,
    };

    const estimate = calculateNetworkEstimate(calculatorInput);
    localStorage.setItem(CALCULATOR_INPUT_STORAGE_KEY, JSON.stringify(calculatorInput));
    localStorage.setItem(CALCULATOR_RESULT_STORAGE_KEY, JSON.stringify(estimate));
    localStorage.setItem('secureOfficePostAuthRedirect', '/shop/designs/new');

    handleClose();
    if (user) {
      navigate('/shop/designs/new', { replace: true });
    } else {
      navigate('/login?next=/shop/designs/new', { replace: true });
    }
  };

  /* --- render helpers --- */

  const primaryReady = useMemo(
    () =>
      Boolean(
        intakeData.businessType &&
          intakeData.squareFootage &&
          intakeData.employees,
      ),
    [intakeData],
  );

  if (!open) return null;

  const fieldClass = (key: string) =>
    `intake-form-field ${highlightedFields[key] ? 'intake-field-highlighted' : ''}`;

  const advFieldClass = (key: string) =>
    `intake-form-field ${advancedUnlocked ? '' : 'locked'} ${
      highlightedFields[key] ? 'intake-field-highlighted' : ''
    }`;

  const currentSection = ADVANCED_SECTIONS[advancedStep];

  /* --- render a single field from a FieldDef --- */
  const renderField = (field: FieldDef) => {
    const val = intakeData[field.key];
    const onChange = (v: string) => updateIntakeField(field.key, v);
    const disabled = !advancedUnlocked;

    if (field.type === 'select' && field.options) {
      return (
        <div key={field.key} className={advFieldClass(field.key)} data-field={field.key}>
          <label>{field.label}</label>
          <select value={val} onChange={(e) => onChange(e.target.value)} disabled={disabled}>
            <option value="">Select...</option>
            {field.options.map((opt) => (
              <option key={opt} value={opt}>{opt}</option>
            ))}
          </select>
        </div>
      );
    }

    return (
      <div key={field.key} className={advFieldClass(field.key)} data-field={field.key}>
        <label>{field.label}</label>
        <input
          type={field.type === 'number' ? 'number' : 'text'}
          min={field.type === 'number' ? '0' : undefined}
          value={val}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
        />
      </div>
    );
  };

  /* --- determine if the latest message should get typewriter effect --- */
  const isLatestAssistantNew = (idx: number) => {
    return (
      idx === messages.length - 1 &&
      messages[idx].role === 'assistant' &&
      messages.length > prevMsgCountRef.current - 1
    );
  };

  return (
    <div className="intake-modal-backdrop" onClick={handleClose}>
      <div className="intake-modal-shell" onClick={(e) => e.stopPropagation()}>
        {/* ── Close button (floating) ── */}
        <button
          type="button"
          className="intake-modal-close-float"
          onClick={handleClose}
          aria-label="Close"
        >
          <X size={18} />
        </button>

        {/* ── BODY ─────────────────────────────────────────────── */}
        <div className="intake-modal-body">
          {/* LEFT: Mode select / Chat / Avatar */}
          <aside className="intake-chat-side">
            {/* ── MODE SELECTION ── */}
            {mode === 'select' && (
              <div className="intake-mode-select">
                <h3>How would you like to get started?</h3>
                <p className="intake-mode-subtitle">Choose your preferred way to describe your business</p>

                <button className="intake-mode-card" onClick={() => setMode('avatar')}>
                  <div className="intake-mode-avatar-img">
                    <img src="/ai-avatar-face.png" alt="AI Avatar" />
                  </div>
                  <span className="intake-mode-label">Talk to someone</span>
                  <span className="intake-mode-desc">Voice conversation with video avatar</span>
                </button>

                <button className="intake-mode-card" onClick={() => setMode('chat')}>
                  <div className="intake-mode-chat-icon">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none">
                      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                      <circle cx="9.5" cy="11.5" r="1" fill="currentColor"/>
                      <circle cx="12.5" cy="11.5" r="1" fill="currentColor"/>
                      <circle cx="15.5" cy="11.5" r="1" fill="currentColor"/>
                    </svg>
                  </div>
                  <span className="intake-mode-label">Chat with AI</span>
                  <span className="intake-mode-desc">Text-based AI assistant</span>
                </button>
              </div>
            )}

            {/* ── CHAT MODE ── */}
            {mode === 'chat' && (
              <>
                <div className="intake-chat-welcome">
                  <button
                    className="intake-mode-back"
                    onClick={() => setMode('select')}
                    title="Back to options"
                  >
                    <ArrowLeft size={14} />
                  </button>
                  <Sparkles size={14} />
                  <span>Secure AI Office Assistant</span>
                </div>

                <div className="intake-chat-messages" ref={messagesRef}>
                  {messages.map((msg, idx) => (
                    <div
                      key={idx}
                      className={`intake-chat-msg ${msg.role}`}
                    >
                      {msg.role === 'assistant' && isLatestAssistantNew(idx) ? (
                        <TypewriterText text={msg.content} onTick={scrollChatToBottom} />
                      ) : (
                        msg.content.split('\n').map((line, i) => (
                          <p key={i}>{line || '\u00A0'}</p>
                        ))
                      )}
                    </div>
                  ))}
                  {chatLoading && (
                    <div className="intake-chat-msg assistant">
                      <p className="intake-chat-typing">
                        <span></span>
                        <span></span>
                        <span></span>
                      </p>
                    </div>
                  )}
                </div>

                <form className="intake-chat-input" onSubmit={sendMessage}>
                  <input
                    ref={inputRef}
                    type="text"
                    placeholder="Tell me about your business..."
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    disabled={chatLoading}
                  />
                  <button type="submit" disabled={chatLoading || !chatInput.trim()}>
                    <Send size={15} />
                  </button>
                </form>
              </>
            )}

            {/* ── AVATAR MODE ── */}
            {mode === 'avatar' && (
              <>
                <div className="intake-chat-welcome">
                  <button
                    className="intake-mode-back"
                    onClick={() => {
                      avatarRef.current?.disconnect();
                      setMode('select');
                    }}
                    title="Back to options"
                  >
                    <ArrowLeft size={14} />
                  </button>
                  <Video size={14} />
                  <span>AI Avatar Assistant</span>
                </div>
                <div className="intake-avatar-panel">
                  <AnamAvatar
                    ref={avatarRef}
                    embedded
                    videoId="anam-modal-video"
                    formState={intakeData as unknown as Record<string, string>}
                    onFormUpdate={handleAvatarFormUpdate}
                  />
                </div>
              </>
            )}
          </aside>

          {/* RIGHT: Form */}
          <section className="intake-form-side">
            <div className="intake-form-primary">
              <div className="intake-form-head">
                <h3>Business Profile</h3>
                <span className="intake-form-sub">Required — 6 fields</span>
              </div>

              <div className={fieldClass('businessType')} data-field="businessType">
                <label>Business type / industry *</label>
                <select
                  value={intakeData.businessType}
                  onChange={(e) => updateIntakeField('businessType', e.target.value)}
                >
                  <option value="">Select...</option>
                  {BUSINESS_TYPE_OPTIONS.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              </div>

              <div className="intake-form-grid-2">
                <div className={fieldClass('locations')} data-field="locations">
                  <label>Number of locations</label>
                  <input
                    type="number"
                    min="0"
                    value={intakeData.locations}
                    onChange={(e) => updateIntakeField('locations', e.target.value)}
                    placeholder="1"
                  />
                </div>
                <div className={fieldClass('squareFootage')} data-field="squareFootage">
                  <label>Square footage *</label>
                  <input
                    type="number"
                    min="0"
                    value={intakeData.squareFootage}
                    onChange={(e) => updateIntakeField('squareFootage', e.target.value)}
                    placeholder="5000"
                  />
                </div>
                <div className={fieldClass('employees')} data-field="employees">
                  <label>Number of employees *</label>
                  <input
                    type="number"
                    min="0"
                    value={intakeData.employees}
                    onChange={(e) => updateIntakeField('employees', e.target.value)}
                    placeholder="15"
                  />
                </div>
                <div className={fieldClass('peakCustomers')} data-field="peakCustomers">
                  <label>Peak customers</label>
                  <input
                    type="number"
                    min="0"
                    value={intakeData.peakCustomers}
                    onChange={(e) => updateIntakeField('peakCustomers', e.target.value)}
                    placeholder="50"
                  />
                </div>
                <div
                  className={fieldClass('avgDailyCustomers')}
                  data-field="avgDailyCustomers"
                  style={{ gridColumn: '1 / -1' }}
                >
                  <label>Average daily customers</label>
                  <input
                    type="number"
                    min="0"
                    value={intakeData.avgDailyCustomers}
                    onChange={(e) =>
                      updateIntakeField('avgDailyCustomers', e.target.value)
                    }
                    placeholder="200"
                  />
                </div>
              </div>
            </div>

            {/* Advanced — multi-step */}
            <div className="intake-form-advanced">
              <div className="intake-form-advanced-head">
                <div>
                  <h3>Advanced Options</h3>
                  <span className="intake-form-sub">
                    Section {advancedStep + 2} of 12 — {currentSection.title}
                  </span>
                </div>
                <button
                  type="button"
                  className="intake-form-edit-btn"
                  onClick={() => setAdvancedUnlocked((v) => !v)}
                >
                  {advancedUnlocked ? (
                    <>
                      <Lock size={13} /> Lock
                    </>
                  ) : (
                    <>
                      <Unlock size={13} /> Edit
                    </>
                  )}
                </button>
              </div>

              {/* Step indicator dots */}
              <div className="intake-step-dots">
                {ADVANCED_SECTIONS.map((_, i) => (
                  <button
                    key={i}
                    className={`intake-step-dot ${i === advancedStep ? 'active' : ''}`}
                    onClick={() => setAdvancedStep(i)}
                    title={ADVANCED_SECTIONS[i].title}
                  />
                ))}
              </div>

              <div className="intake-section-title">{currentSection.title}</div>

              <div className="intake-form-grid-2">
                {currentSection.fields.map(renderField)}
              </div>

              {/* Step navigation */}
              <div className="intake-step-nav">
                <button
                  type="button"
                  onClick={() => setAdvancedStep((s) => Math.max(0, s - 1))}
                  disabled={advancedStep === 0}
                >
                  <ChevronLeft size={14} /> Back
                </button>
                <span className="intake-step-indicator">
                  {advancedStep + 1} / {ADVANCED_SECTIONS.length}
                </span>
                <button
                  type="button"
                  onClick={() =>
                    setAdvancedStep((s) => Math.min(ADVANCED_SECTIONS.length - 1, s + 1))
                  }
                  disabled={advancedStep === ADVANCED_SECTIONS.length - 1}
                >
                  Next <ChevronRight size={14} />
                </button>
              </div>
            </div>

            <button
              type="button"
              className="intake-submit"
              onClick={handleSubmit}
              disabled={!primaryReady}
            >
              {primaryReady ? 'Build My Design' : 'Fill required fields to continue'}
              <ArrowRight size={16} />
            </button>
          </section>
        </div>
      </div>
    </div>
  );
};
