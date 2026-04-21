import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AnamAvatar } from '../components/AnamAvatar';
import { EnvironmentType, NetworkCalculatorInput, ObstructionType, WifiStandard, calculateNetworkEstimate } from '../calculator';
import { useAuth } from '../context/AuthContext';

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

const createInitialIntakeData = (): IntakeFormData => ({
  businessType: '',
  locations: '',
  squareFootage: '',
  employees: '',
  peakCustomers: '',
  avgDailyCustomers: '',
  internetType: '',
  primaryInternetSpeed: '',
  needsBackupInternet: '',
  guestWifiRequired: '',
  laptops: '',
  desktops: '',
  tablets: '',
  mobilePhones: '',
  posTerminals: '',
  handheldPosDevices: '',
  selfCheckoutMachines: '',
  barcodeScanners: '',
  receiptPrinters: '',
  labelPrinters: '',
  ipCameras: '',
  nvrDvrPresent: '',
  doorAccessControl: '',
  alarmSystem: '',
  digitalSignageScreens: '',
  selfOrderKiosks: '',
  guestWifiUsers: '',
  customerTablets: '',
  musicStreamingSystems: '',
  kitchenDisplaySystems: '',
  onlineOrderingTablets: '',
  driveThruSystems: '',
  deliveryIntegration: '',
  smartRefrigerators: '',
  smartCoffeeMachines: '',
  vendingMachines: '',
  lightingControllers: '',
  sensors: '',
  inventoryScanners: '',
  facilityManagementSystems: '',
  deliveryRobots: '',
  inventoryRobots: '',
  smartShelves: '',
  rfidGates: '',
  squarePos: '',
  odoo: '',
  salesforce: '',
  hubspot: '',
  otherSaasTools: '',
  downtimeTolerance: '',
  needRedundancy: '',
  managedServicePreference: '',
  installationSupportNeeded: '',
});

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

const NumericField = ({
  label,
  value,
  onChange,
  required = false,
  fieldKey,
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
  required?: boolean;
  fieldKey?: string;
}) => (
  <label data-field={fieldKey}>
    <span>{label}</span>
    <input type="number" min={0} inputMode="numeric" value={value} onChange={(e) => onChange(e.target.value)} required={required} />
  </label>
);

const SelectField = ({
  label,
  value,
  onChange,
  options,
  required = false,
  fieldKey,
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
  options: string[];
  required?: boolean;
  fieldKey?: string;
}) => (
  <label data-field={fieldKey}>
    <span>{label}</span>
    <select value={value} onChange={(e) => onChange(e.target.value)} required={required}>
      <option value="">Select</option>
      {options.map((option) => (
        <option key={option} value={option}>
          {option}
        </option>
      ))}
    </select>
  </label>
);

export const BusinessIntakePage = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [intakeData, setIntakeData] = useState<IntakeFormData>(() => {
    const saved = localStorage.getItem(INTAKE_STORAGE_KEY);
    if (!saved) return createDummyIntakeData();
    try {
      return { ...createInitialIntakeData(), ...JSON.parse(saved) };
    } catch {
      return createDummyIntakeData();
    }
  });

  // Track which fields were just updated by the avatar (for pink highlight)
  const [highlightedFields, setHighlightedFields] = useState<Set<string>>(new Set());
  const highlightTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Apply/remove pink highlight on fields via DOM data-field attributes
  useEffect(() => {
    if (highlightedFields.size === 0) return;

    // Add highlight class to matching labels
    const labels: HTMLElement[] = [];
    highlightedFields.forEach((field) => {
      const el = document.querySelector(`[data-field="${field}"]`) as HTMLElement | null;
      if (el) {
        el.classList.add('intake-field-highlighted');
        el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        labels.push(el);
      }
    });

    // Remove after 3.5 seconds
    if (highlightTimerRef.current) clearTimeout(highlightTimerRef.current);
    highlightTimerRef.current = setTimeout(() => {
      labels.forEach((el) => el.classList.remove('intake-field-highlighted'));
      setHighlightedFields(new Set());
    }, 3500);

    return () => { if (highlightTimerRef.current) clearTimeout(highlightTimerRef.current); };
  }, [highlightedFields]);

  const updateIntakeField = <K extends keyof IntakeFormData>(key: K, value: IntakeFormData[K]) => {
    setIntakeData((prev) => ({ ...prev, [key]: value }));
  };

  /** Called by AnamAvatar when the AI agent fills form fields */
  const handleAvatarFormUpdate = useCallback((updates: Record<string, string>) => {
    setIntakeData((prev) => {
      const next = { ...prev };
      for (const [key, value] of Object.entries(updates)) {
        if (key in next) {
          (next as any)[key] = value;
        }
      }
      return next;
    });
    // Highlight the updated fields in pink
    setHighlightedFields(new Set(Object.keys(updates)));
  }, []);

  const onSubmitIntake = (e: FormEvent) => {
    e.preventDefault();
    localStorage.setItem(INTAKE_STORAGE_KEY, JSON.stringify(intakeData));

    const employees = asNonNegative(intakeData.employees, 15);
    const peakCustomers = asNonNegative(intakeData.peakCustomers, 30);
    const guestWifiUsers = asNonNegative(intakeData.guestWifiUsers, 0);
    const totalUsers = Math.max(1, employees + Math.max(guestWifiUsers, peakCustomers * 0.35));

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
      upsRequired: intakeData.needRedundancy === 'Yes' || intakeData.needsBackupInternet === 'Yes',
      pricing: DEFAULT_PRICING,
    };

    const estimate = calculateNetworkEstimate(calculatorInput);
    localStorage.setItem(CALCULATOR_INPUT_STORAGE_KEY, JSON.stringify(calculatorInput));
    localStorage.setItem(CALCULATOR_RESULT_STORAGE_KEY, JSON.stringify(estimate));
    localStorage.setItem('secureOfficePostAuthRedirect', '/shop/designs/new');
    if (user) {
      navigate('/shop/designs/new', { replace: true });
      return;
    }
    navigate('/login?next=/shop/designs/new', { replace: true });
  };

  return (
    <div className="business-intake-page">
      <div className="business-intake-shell">
        <header className="business-intake-header">
          <h1>Business Network Intake</h1>
          <p>Tell us about your business environment and we will generate your full network design.</p>
        </header>

        <form className="intake-form" onSubmit={onSubmitIntake}>
          <section className="intake-section">
            <h3>1. Business Profile (Basic Context)</h3>
            <div className="intake-grid">
              <SelectField fieldKey="businessType" label="Business type / industry" value={intakeData.businessType} options={BUSINESS_TYPE_OPTIONS} onChange={(next) => updateIntakeField('businessType', next)} required />
              <NumericField fieldKey="locations" label="Number of locations" value={intakeData.locations} onChange={(next) => updateIntakeField('locations', next)} required />
              <NumericField fieldKey="squareFootage" label="Square footage of location" value={intakeData.squareFootage} onChange={(next) => updateIntakeField('squareFootage', next)} />
              <NumericField fieldKey="employees" label="Number of employees" value={intakeData.employees} onChange={(next) => updateIntakeField('employees', next)} />
              <NumericField fieldKey="peakCustomers" label="Peak number of customers" value={intakeData.peakCustomers} onChange={(next) => updateIntakeField('peakCustomers', next)} />
              <NumericField fieldKey="avgDailyCustomers" label="Average daily customers" value={intakeData.avgDailyCustomers} onChange={(next) => updateIntakeField('avgDailyCustomers', next)} />
            </div>
          </section>

          <section className="intake-section">
            <h3>2. Connectivity Requirements</h3>
            <div className="intake-grid">
              <SelectField fieldKey="internetType" label="Internet type" value={intakeData.internetType} options={INTERNET_TYPE_OPTIONS} onChange={(next) => updateIntakeField('internetType', next)} required />
              <label data-field="primaryInternetSpeed">
                <span>Primary internet speed (optional)</span>
                <input type="text" placeholder="e.g. 500 Mbps" value={intakeData.primaryInternetSpeed} onChange={(e) => updateIntakeField('primaryInternetSpeed', e.target.value)} />
              </label>
              <SelectField fieldKey="needsBackupInternet" label="Need backup internet?" value={intakeData.needsBackupInternet} options={YES_NO_OPTIONS} onChange={(next) => updateIntakeField('needsBackupInternet', next)} />
              <SelectField fieldKey="guestWifiRequired" label="Guest Wi-Fi required?" value={intakeData.guestWifiRequired} options={YES_NO_OPTIONS} onChange={(next) => updateIntakeField('guestWifiRequired', next)} />
            </div>
          </section>

          <section className="intake-section">
            <h3>3. Staff Devices</h3>
            <div className="intake-grid">
              <NumericField fieldKey="laptops" label="Laptops" value={intakeData.laptops} onChange={(next) => updateIntakeField('laptops', next)} />
              <NumericField fieldKey="desktops" label="Desktop computers" value={intakeData.desktops} onChange={(next) => updateIntakeField('desktops', next)} />
              <NumericField fieldKey="tablets" label="Tablets" value={intakeData.tablets} onChange={(next) => updateIntakeField('tablets', next)} />
              <NumericField fieldKey="mobilePhones" label="Mobile phones" value={intakeData.mobilePhones} onChange={(next) => updateIntakeField('mobilePhones', next)} />
            </div>
          </section>

          <section className="intake-section">
            <h3>4. POS &amp; Retail Systems</h3>
            <div className="intake-grid">
              <NumericField fieldKey="posTerminals" label="POS terminals" value={intakeData.posTerminals} onChange={(next) => updateIntakeField('posTerminals', next)} />
              <NumericField fieldKey="handheldPosDevices" label="Handheld POS devices" value={intakeData.handheldPosDevices} onChange={(next) => updateIntakeField('handheldPosDevices', next)} />
              <NumericField fieldKey="selfCheckoutMachines" label="Self-checkout machines" value={intakeData.selfCheckoutMachines} onChange={(next) => updateIntakeField('selfCheckoutMachines', next)} />
              <NumericField fieldKey="barcodeScanners" label="Barcode scanners" value={intakeData.barcodeScanners} onChange={(next) => updateIntakeField('barcodeScanners', next)} />
              <NumericField fieldKey="receiptPrinters" label="Receipt printers" value={intakeData.receiptPrinters} onChange={(next) => updateIntakeField('receiptPrinters', next)} />
              <NumericField fieldKey="labelPrinters" label="Label printers" value={intakeData.labelPrinters} onChange={(next) => updateIntakeField('labelPrinters', next)} />
            </div>
          </section>

          <section className="intake-section">
            <h3>5. Surveillance &amp; Security</h3>
            <div className="intake-grid">
              <NumericField fieldKey="ipCameras" label="Number of IP cameras" value={intakeData.ipCameras} onChange={(next) => updateIntakeField('ipCameras', next)} />
              <SelectField fieldKey="nvrDvrPresent" label="NVR / DVR system present" value={intakeData.nvrDvrPresent} options={YES_NO_OPTIONS} onChange={(next) => updateIntakeField('nvrDvrPresent', next)} />
              <SelectField fieldKey="doorAccessControl" label="Door access control" value={intakeData.doorAccessControl} options={YES_NO_OPTIONS} onChange={(next) => updateIntakeField('doorAccessControl', next)} />
              <SelectField fieldKey="alarmSystem" label="Alarm system" value={intakeData.alarmSystem} options={YES_NO_OPTIONS} onChange={(next) => updateIntakeField('alarmSystem', next)} />
            </div>
          </section>

          <section className="intake-section">
            <h3>6. Customer Experience Systems</h3>
            <div className="intake-grid">
              <NumericField fieldKey="digitalSignageScreens" label="Digital signage screens" value={intakeData.digitalSignageScreens} onChange={(next) => updateIntakeField('digitalSignageScreens', next)} />
              <NumericField fieldKey="selfOrderKiosks" label="Self-order kiosks" value={intakeData.selfOrderKiosks} onChange={(next) => updateIntakeField('selfOrderKiosks', next)} />
              <NumericField fieldKey="guestWifiUsers" label="Guest Wi-Fi users" value={intakeData.guestWifiUsers} onChange={(next) => updateIntakeField('guestWifiUsers', next)} />
              <NumericField fieldKey="customerTablets" label="Customer tablets" value={intakeData.customerTablets} onChange={(next) => updateIntakeField('customerTablets', next)} />
              <NumericField fieldKey="musicStreamingSystems" label="Music / audio streaming systems" value={intakeData.musicStreamingSystems} onChange={(next) => updateIntakeField('musicStreamingSystems', next)} />
            </div>
          </section>

          <section className="intake-section">
            <h3>7. Restaurant / QSR Systems</h3>
            <div className="intake-grid">
              <NumericField fieldKey="kitchenDisplaySystems" label="Kitchen display systems" value={intakeData.kitchenDisplaySystems} onChange={(next) => updateIntakeField('kitchenDisplaySystems', next)} />
              <NumericField fieldKey="onlineOrderingTablets" label="Online ordering tablets" value={intakeData.onlineOrderingTablets} onChange={(next) => updateIntakeField('onlineOrderingTablets', next)} />
              <NumericField fieldKey="driveThruSystems" label="Drive-thru systems" value={intakeData.driveThruSystems} onChange={(next) => updateIntakeField('driveThruSystems', next)} />
              <SelectField fieldKey="deliveryIntegration" label="Delivery integration" value={intakeData.deliveryIntegration} options={YES_NO_OPTIONS} onChange={(next) => updateIntakeField('deliveryIntegration', next)} />
            </div>
          </section>

          <section className="intake-section">
            <h3>8. IoT &amp; Smart Devices</h3>
            <div className="intake-grid">
              <NumericField fieldKey="smartRefrigerators" label="Smart refrigerators" value={intakeData.smartRefrigerators} onChange={(next) => updateIntakeField('smartRefrigerators', next)} />
              <NumericField fieldKey="smartCoffeeMachines" label="Smart coffee machines" value={intakeData.smartCoffeeMachines} onChange={(next) => updateIntakeField('smartCoffeeMachines', next)} />
              <NumericField fieldKey="vendingMachines" label="Vending machines" value={intakeData.vendingMachines} onChange={(next) => updateIntakeField('vendingMachines', next)} />
              <NumericField fieldKey="lightingControllers" label="Lighting controllers" value={intakeData.lightingControllers} onChange={(next) => updateIntakeField('lightingControllers', next)} />
              <NumericField fieldKey="sensors" label="Sensors" value={intakeData.sensors} onChange={(next) => updateIntakeField('sensors', next)} />
              <NumericField fieldKey="inventoryScanners" label="Inventory scanners" value={intakeData.inventoryScanners} onChange={(next) => updateIntakeField('inventoryScanners', next)} />
              <NumericField fieldKey="facilityManagementSystems" label="Facility management systems" value={intakeData.facilityManagementSystems} onChange={(next) => updateIntakeField('facilityManagementSystems', next)} />
            </div>
          </section>

          <section className="intake-section">
            <h3>9. Advanced Automation Devices</h3>
            <div className="intake-grid">
              <NumericField fieldKey="deliveryRobots" label="Delivery robots" value={intakeData.deliveryRobots} onChange={(next) => updateIntakeField('deliveryRobots', next)} />
              <NumericField fieldKey="inventoryRobots" label="Inventory robots" value={intakeData.inventoryRobots} onChange={(next) => updateIntakeField('inventoryRobots', next)} />
              <NumericField fieldKey="smartShelves" label="Smart shelves" value={intakeData.smartShelves} onChange={(next) => updateIntakeField('smartShelves', next)} />
              <NumericField fieldKey="rfidGates" label="RFID gates" value={intakeData.rfidGates} onChange={(next) => updateIntakeField('rfidGates', next)} />
            </div>
          </section>

          <section className="intake-section">
            <h3>10. Applications / SaaS</h3>
            <div className="intake-grid">
              <SelectField fieldKey="squarePos" label="Square POS" value={intakeData.squarePos} options={YES_NO_OPTIONS} onChange={(next) => updateIntakeField('squarePos', next)} />
              <SelectField fieldKey="odoo" label="Odoo" value={intakeData.odoo} options={YES_NO_OPTIONS} onChange={(next) => updateIntakeField('odoo', next)} />
              <SelectField fieldKey="salesforce" label="Salesforce" value={intakeData.salesforce} options={YES_NO_OPTIONS} onChange={(next) => updateIntakeField('salesforce', next)} />
              <SelectField fieldKey="hubspot" label="HubSpot" value={intakeData.hubspot} options={YES_NO_OPTIONS} onChange={(next) => updateIntakeField('hubspot', next)} />
              <label data-field="otherSaasTools">
                <span>Other SaaS tools</span>
                <input type="text" placeholder="Optional" value={intakeData.otherSaasTools} onChange={(e) => updateIntakeField('otherSaasTools', e.target.value)} />
              </label>
            </div>
          </section>

          <section className="intake-section">
            <h3>11. Network Reliability Needs</h3>
            <div className="intake-grid">
              <SelectField fieldKey="downtimeTolerance" label="Downtime tolerance" value={intakeData.downtimeTolerance} options={DOWNTIME_OPTIONS} onChange={(next) => updateIntakeField('downtimeTolerance', next)} required />
              <SelectField fieldKey="needRedundancy" label="Need redundancy?" value={intakeData.needRedundancy} options={YES_NO_OPTIONS} onChange={(next) => updateIntakeField('needRedundancy', next)} />
            </div>
          </section>

          <section className="intake-section">
            <h3>12. Managed Services Preference</h3>
            <div className="intake-grid">
              <SelectField fieldKey="managedServicePreference" label="Network ownership" value={intakeData.managedServicePreference} options={MANAGED_OPTIONS} onChange={(next) => updateIntakeField('managedServicePreference', next)} required />
              <SelectField fieldKey="installationSupportNeeded" label="Installation support needed" value={intakeData.installationSupportNeeded} options={YES_NO_OPTIONS} onChange={(next) => updateIntakeField('installationSupportNeeded', next)} />
            </div>
          </section>

          <div className="business-intake-actions">
            <button className="secondary-btn" type="button" onClick={() => setIntakeData(createDummyIntakeData())}>
              Load Dummy Data
            </button>
            <button className="primary-btn" type="submit">Continue to Design</button>
          </div>
        </form>
      </div>

      {/* AI Avatar — bottom-left, has full form context, can fill fields via voice/text */}
      <AnamAvatar formState={intakeData as unknown as Record<string, string>} onFormUpdate={handleAvatarFormUpdate} />
    </div>
  );
};
