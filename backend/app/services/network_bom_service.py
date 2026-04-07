from __future__ import annotations

import math
from typing import Any

from app.models.catalog import CatalogItemType


class NetworkBomService:
    CABLE_PRICE_PER_METER = {
        'CAT5': 0.35,
        'CAT6': 0.55,
        'CAT6e': 0.80,
    }
    DEFAULT_CABLE_TYPE = 'CAT6'

    SIM_KEYWORDS = (
        'sim',
        '5g',
        'lte',
        'cellular',
        'hotspot',
        'mifi',
        'esim',
    )
    WIRELESS_KEYWORDS = (
        'wi-fi',
        'wifi',
        'wireless',
        'wlan',
    )
    WIRED_KEYWORDS = (
        'ethernet',
        'rj45',
        'poe',
        'lan',
        'wired',
        'cat5',
        'cat6',
        'cat6e',
        'fiber',
    )

    SIM_CATEGORIES = {'cellular_backup', 'cellular_gateway', 'hotspot'}
    WIRELESS_DEFAULT_CATEGORIES = {'laptop', 'desktop', 'tablet', 'phone'}
    WIRED_INFRA_CATEGORIES = {
        'switch',
        'wifi_ap',
        'router',
        'gateway',
        'firewall',
        'security_appliance',
    }
    WIRED_DEFAULT_CATEGORIES = {'camera', 'pos_systems', 'digital_signage', 'kiosks', 'kitchen_systems', 'antenna', 'cabling'}
    NON_DROP_CATEGORIES = {'managed_service', 'managed_service_candidate', 'service', 'license', 'installation', 'labor', 'cabling', 'accessory'}

    def __init__(self, catalog_service):
        self.catalog_service = catalog_service

    @staticmethod
    def _as_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _as_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _pref_value(preferences: dict[str, Any], *keys: str):
        for key in keys:
            if key in preferences:
                return preferences[key]
        return None

    @staticmethod
    def _pref_bool(preferences: dict[str, Any], default: bool, *keys: str) -> bool:
        value = NetworkBomService._pref_value(preferences, *keys)
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {'1', 'true', 'yes', 'y', 'on'}
        return bool(value)

    @staticmethod
    def _is_yes(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value or '').strip().lower() in {'1', 'true', 'yes', 'y', 'on'}

    @staticmethod
    def _clean_tokens(values: list[str | None]) -> list[str]:
        tokens: list[str] = []
        seen: set[str] = set()
        for raw in values:
            text = str(raw or '').strip().lower()
            if not text:
                continue
            for token in text.replace('/', ' ').replace('-', ' ').split():
                token = token.strip()
                if len(token) < 2:
                    continue
                if token in seen:
                    continue
                seen.add(token)
                tokens.append(token)
        return tokens

    @staticmethod
    def _item_category(item) -> str:
        return str((item.attributes or {}).get('category') or '').strip().lower()

    @staticmethod
    def _item_search_blob(item) -> str:
        attrs = item.attributes or {}
        text_parts = [
            item.name,
            item.sku,
            item.vendor,
            item.vendor_sku,
            item.description,
            attrs.get('category'),
            attrs.get('product_type'),
            attrs.get('model'),
            attrs.get('family_type'),
            attrs.get('device_type'),
            attrs.get('brand'),
        ]
        return ' '.join(str(part or '') for part in text_parts).lower()

    def _sum_business_counts(self, business_context: dict[str, Any], *keys: str) -> int:
        total = 0
        for key in keys:
            total += max(0, self._as_int(business_context.get(key)))
        return total

    @classmethod
    def _normalize_cable_type(cls, value: Any) -> str:
        normalized = str(value or '').strip().upper()
        if normalized == 'CAT6E':
            return 'CAT6e'
        if normalized in {'CAT5', 'CAT6'}:
            return normalized
        return cls.DEFAULT_CABLE_TYPE

    def _office_area_sqft(self, *, normalized_inputs: dict[str, Any], business_context: dict[str, Any], assumptions: list[str]) -> float:
        sqft_keys = (
            'totalFloorAreaSqft',
            'officeAreaSqft',
            'floorAreaSqft',
            'office_square_area_sqft',
            'total_floor_area_sqft',
        )
        for key in sqft_keys:
            value = self._as_float(normalized_inputs.get(key), self._as_float(business_context.get(key)))
            if value > 0:
                return value

        sqm_keys = (
            'totalFloorAreaSqm',
            'officeAreaSqm',
            'floorAreaSqm',
            'office_square_area_sqm',
            'total_floor_area_sqm',
        )
        for key in sqm_keys:
            sqm = self._as_float(normalized_inputs.get(key), self._as_float(business_context.get(key)))
            if sqm > 0:
                return round(sqm * 10.7639, 2)

        assumptions.append('Office floor area was not provided; assumed 1500 sqft to derive structured cabling length.')
        return 1500.0

    def _connectivity_from_category_and_blob(self, *, category: str | None, blob: str) -> str | None:
        category_normalized = str(category or '').strip().lower()
        text = str(blob or '').lower()

        has_sim = any(token in text for token in self.SIM_KEYWORDS)
        has_wireless = any(token in text for token in self.WIRELESS_KEYWORDS)
        has_wired = any(token in text for token in self.WIRED_KEYWORDS)

        if has_sim and category_normalized not in {'switch', 'wifi_ap'}:
            return 'sim'
        if category_normalized in self.SIM_CATEGORIES:
            return 'sim'
        if category_normalized in self.WIRED_INFRA_CATEGORIES:
            return 'wired'
        if category_normalized in self.WIRELESS_DEFAULT_CATEGORIES:
            if has_sim:
                return 'sim'
            if has_wired:
                return 'wired'
            return 'wireless'
        if category_normalized == 'sensor':
            if has_sim:
                return 'sim'
            if has_wired:
                return 'wired'
            return 'wireless'
        if category_normalized in self.WIRED_DEFAULT_CATEGORIES:
            if has_sim:
                return 'sim'
            if has_wireless and not has_wired:
                return 'wireless'
            return 'wired'

        if has_sim:
            return 'sim'
        if has_wired and not has_wireless:
            return 'wired'
        if has_wireless:
            return 'wireless'
        return None

    def _line_connectivity(self, line: dict[str, Any]) -> str | None:
        explicit = str(line.get('connectivity') or '').strip().lower()
        if explicit in {'wired', 'wireless', 'sim'}:
            return explicit
        category = str(line.get('category') or '').strip().lower()
        blob = ' '.join(
            [
                str(line.get('name') or ''),
                str(line.get('sku') or ''),
                str(line.get('selection_reason') or ''),
                category,
            ]
        )
        return self._connectivity_from_category_and_blob(category=category, blob=blob)

    def _estimate_wired_drop_count(self, line_items: list[dict[str, Any]]) -> int:
        drops = 0
        for line in line_items:
            category = str(line.get('category') or '').strip().lower()
            if category in self.NON_DROP_CATEGORIES:
                continue
            if self._line_connectivity(line) != 'wired':
                continue
            drops += max(1, self._as_int(line.get('quantity'), 1))
        return drops

    def _line_from_catalog_item(
        self,
        *,
        line_id: str,
        item,
        quantity: int,
        category_override: str | None,
        selection_reason: str,
    ) -> dict[str, Any]:
        quantity = max(1, int(quantity or 1))
        item_dict = self.catalog_service.to_catalog_response_dict(item)
        unit_price = self._as_float(item_dict['price'])
        category = category_override or item_dict.get('category')
        connectivity = self._connectivity_from_category_and_blob(
            category=category,
            blob=self._item_search_blob(item),
        )

        line = {
            'line_id': line_id,
            'item_id': item_dict['id'],
            'sku': item_dict['sku'],
            'source_type': item_dict['source_type'],
            'name': item_dict['name'],
            'vendor': item_dict['vendor'],
            'category': category,
            'quantity': quantity,
            'unit_price': unit_price,
            'line_total': round(unit_price * quantity, 2),
            'selection_reason': selection_reason,
        }
        if connectivity:
            line['connectivity'] = connectivity
        return line

    def _line_from_derived(
        self,
        *,
        line_id: str,
        name: str,
        category: str,
        quantity: int,
        unit_price: float,
        selection_reason: str,
        sku: str | None = None,
        connectivity: str | None = None,
    ) -> dict[str, Any]:
        quantity = max(1, int(quantity or 1))
        unit_price = float(unit_price or 0.0)
        detected_connectivity = connectivity or self._connectivity_from_category_and_blob(
            category=category,
            blob=' '.join([name, category, selection_reason]),
        )
        line = {
            'line_id': line_id,
            'item_id': None,
            'sku': sku,
            'source_type': 'derived',
            'name': name,
            'vendor': 'Derived',
            'category': category,
            'quantity': quantity,
            'unit_price': round(unit_price, 2),
            'line_total': round(unit_price * quantity, 2),
            'selection_reason': selection_reason,
        }
        if detected_connectivity:
            line['connectivity'] = detected_connectivity
        return line

    def _list_excel_devices_by_category(self, category: str) -> list:
        return self.catalog_service.list_items(
            item_type=CatalogItemType.DEVICE,
            category=category,
            service_kind=None,
            source_type='excel',
            sort='price_low',
            page=1,
            page_size=25,
        )

    def _list_paapi_devices_by_category(self, category: str) -> list:
        return self.catalog_service.list_items(
            item_type=CatalogItemType.DEVICE,
            category=category,
            service_kind=None,
            source_type='paapi',
            sort='price_low',
            page=1,
            page_size=25,
        )

    def _list_devices(self, *, category: str | None, source_type: str, max_pages: int = 4) -> list:
        collected: list[Any] = []
        seen: set[str] = set()
        for page in range(1, max_pages + 1):
            rows = self.catalog_service.list_items(
                item_type=CatalogItemType.DEVICE,
                category=category,
                service_kind=None,
                source_type=source_type,
                sort='recommended',
                page=page,
                page_size=25,
            )
            if not rows:
                break
            for item in rows:
                key = str(getattr(item, 'id', '') or getattr(item, 'sku', ''))
                if key in seen:
                    continue
                seen.add(key)
                collected.append(item)
            if len(rows) < 25:
                break
        return collected

    def _choose_requirement_device(
        self,
        *,
        categories: list[str],
        source_types: list[str],
        preferred_vendor: str | None,
        keywords: list[str] | None = None,
        excluded_keywords: list[str] | None = None,
        require_keyword_hit: bool = False,
        assumptions: list[str] | None = None,
        intent_label: str = 'device',
    ):
        assumptions = assumptions or []
        candidates: list[Any] = []
        seen: set[str] = set()
        for source_type in source_types:
            for category in categories:
                for item in self._list_devices(category=category, source_type=source_type):
                    key = str(getattr(item, 'id', '') or getattr(item, 'sku', ''))
                    if key in seen:
                        continue
                    seen.add(key)
                    candidates.append(item)

        if not candidates:
            assumptions.append(f'No catalog candidates found for {intent_label}; placeholder line was used.')
            return None, f'No catalog candidate found for {intent_label}.'

        preferred_vendor_l = str(preferred_vendor or '').strip().lower()
        keyword_tokens = self._clean_tokens(keywords or [])
        excluded_tokens = self._clean_tokens(excluded_keywords or [])

        ranked: list[tuple[float, int, int, float, str, Any]] = []
        for item in candidates:
            text = self._item_search_blob(item)
            keyword_hits = sum(1 for token in keyword_tokens if token in text)
            excluded_hits = sum(1 for token in excluded_tokens if token in text)
            if require_keyword_hit and keyword_tokens and keyword_hits == 0:
                continue

            vendor_match = int(bool(preferred_vendor_l and str(item.vendor or '').strip().lower() == preferred_vendor_l))
            price = self._as_float(getattr(item, 'price', 0.0))
            has_price = int(price > 0)
            source_type = str((item.attributes or {}).get('source_type') or '').strip().lower()
            source_pref = 1 if source_type == 'excel' else 0
            score = float(keyword_hits * 10 + vendor_match * 7 + has_price * 3 + source_pref - excluded_hits * 12)
            ranked.append((score, keyword_hits, has_price, price if price > 0 else 10_000_000.0, str(item.name or ''), item))

        if not ranked:
            assumptions.append(
                f'No keyword-compatible catalog candidate found for {intent_label}; placeholder line was used.'
            )
            return None, f'No keyword-compatible catalog candidate found for {intent_label}.'

        ranked.sort(key=lambda row: (-row[0], -row[1], -row[2], row[3], row[4]))
        chosen = ranked[0][5]
        chosen_vendor = str(chosen.vendor or '').strip()
        if preferred_vendor_l and chosen_vendor.lower() == preferred_vendor_l:
            reason = f'Preferred vendor {chosen_vendor} selected for {intent_label}.'
        else:
            reason = f'Requirement-driven selection for {intent_label} using catalog relevance and pricing.'
        return chosen, reason

    def _choose_device(
        self,
        *,
        category: str,
        preferred_vendor: str | None,
        assumptions: list[str],
        required_ports: int | None = None,
    ):
        candidates = self._list_excel_devices_by_category(category)
        if not candidates:
            assumptions.append(f'No Excel catalog item found for category={category}; using placeholder derived line.')
            return None, f'No Excel catalog match for {category}; inserted placeholder line.'

        vendor_l = (preferred_vendor or '').strip().lower()
        if vendor_l:
            vendor_matches = [item for item in candidates if str(item.vendor or '').strip().lower() == vendor_l]
            if vendor_matches:
                candidates = vendor_matches
            else:
                assumptions.append(
                    f'Preferred vendor {preferred_vendor} not available for category={category}; fell back to lowest priced compatible option.'
                )

        if category == 'switch' and required_ports:
            compatible = [
                item
                for item in candidates
                if self.catalog_service._extract_port_count(item) >= required_ports
            ]
            if compatible:
                candidates = compatible
            else:
                assumptions.append(
                    f'No switch met required port count ({required_ports}); selected lowest priced switch from available Excel catalog.'
                )

        chosen = min(candidates, key=lambda item: float(item.price))
        if preferred_vendor and str(chosen.vendor or '').strip().lower() == (preferred_vendor or '').strip().lower():
            reason = f'Preferred vendor {preferred_vendor} match within {category} category.'
        else:
            reason = f'Lowest priced compatible {category} from Excel-backed network catalog.'
        return chosen, reason

    def _choose_paapi_endpoint_device(
        self,
        *,
        categories: list[str],
        preferred_vendor: str | None,
        keywords: list[str] | None = None,
        excluded_keywords: list[str] | None = None,
        require_keyword_hit: bool = False,
    ):
        return self._choose_requirement_device(
            categories=categories,
            source_types=['paapi'],
            preferred_vendor=preferred_vendor,
            keywords=keywords,
            excluded_keywords=excluded_keywords,
            require_keyword_hit=require_keyword_hit,
            intent_label='/'.join(categories),
        )

    def generate_bom_from_estimate(
        self,
        calculator_result: dict[str, Any],
        business_context: dict[str, Any] | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        preferences = preferences or {}
        business_context = business_context or {}
        assumptions: list[str] = []

        summary = calculator_result.get('summary') or {}
        counts = calculator_result.get('counts') or {}
        costs = calculator_result.get('costs') or {}
        normalized_inputs = (
            calculator_result.get('inputsNormalized')
            or calculator_result.get('inputs_normalized')
            or {}
        )
        pricing = normalized_inputs.get('pricing') or {}

        ap_count = self._as_int(summary.get('recommendedIndoorAPs'), self._as_int(counts.get('indoorAPsFinal'), 1))
        ap_count = max(1, ap_count)

        switch_count = self._as_int(summary.get('recommendedSwitches'), self._as_int(counts.get('switchCount'), 1))
        switch_count = max(1, switch_count)

        preferred_vendor = self._pref_value(preferences, 'preferredVendor', 'preferred_vendor')
        switch_port_preference = self._as_int(
            self._pref_value(preferences, 'switchPortPreference', 'switch_port_preference'),
            self._as_int(normalized_inputs.get('switchPorts'), 24),
        )
        switch_port_preference = max(1, switch_port_preference)

        include_licenses = self._pref_bool(preferences, True, 'includeLicenses', 'include_licenses')
        include_installation = self._pref_bool(preferences, True, 'includeInstallation', 'include_installation')
        include_ups = self._pref_bool(
            preferences,
            bool(normalized_inputs.get('upsRequired')),
            'includeUPS',
            'include_ups',
        )
        include_managed_services = self._pref_bool(preferences, False, 'includeManagedServices', 'include_managed_services')

        line_items: list[dict[str, Any]] = []

        def next_line_id() -> str:
            return f'line-{len(line_items) + 1}'

        ap_item, ap_reason = self._choose_device(
            category='wifi_ap',
            preferred_vendor=preferred_vendor,
            assumptions=assumptions,
        )
        if ap_item:
            line_items.append(
                self._line_from_catalog_item(
                    line_id=next_line_id(),
                    item=ap_item,
                    quantity=ap_count,
                    category_override='wifi_ap',
                    selection_reason=ap_reason,
                )
            )
        else:
            line_items.append(
                self._line_from_derived(
                    line_id=next_line_id(),
                    name='Wi-Fi AP (placeholder)',
                    category='wifi_ap',
                    quantity=ap_count,
                    unit_price=0.0,
                    selection_reason=ap_reason,
                )
            )

        switch_item, switch_reason = self._choose_device(
            category='switch',
            preferred_vendor=preferred_vendor,
            assumptions=assumptions,
            required_ports=switch_port_preference,
        )
        if switch_item:
            line_items.append(
                self._line_from_catalog_item(
                    line_id=next_line_id(),
                    item=switch_item,
                    quantity=switch_count,
                    category_override='switch',
                    selection_reason=f'{switch_reason} Port target: {switch_port_preference}.',
                )
            )
        else:
            line_items.append(
                self._line_from_derived(
                    line_id=next_line_id(),
                    name='Network switch (placeholder)',
                    category='switch',
                    quantity=switch_count,
                    unit_price=0.0,
                    selection_reason=switch_reason,
                )
            )

        context_keywords = [
            business_context.get('businessType'),
            business_context.get('environmentType'),
            normalized_inputs.get('businessType'),
            normalized_inputs.get('environmentType'),
        ]
        exclusion_for_endpoint = ['gateway', 'router', 'firewall', 'modem', 'mifi', 'hotspot', 'cpe']

        needs_gateway = (
            self._pref_bool(preferences, False, 'needsGateway', 'needs_gateway', 'includeGateway', 'include_gateway')
            or self._is_yes(business_context.get('needsGateway'))
            or self._is_yes(business_context.get('needGateway'))
            or self._is_yes(business_context.get('needRedundancy'))
            or 'critical' in str(business_context.get('downtimeTolerance') or '').lower()
        )
        if needs_gateway:
            gateway_item, gateway_reason = self._choose_requirement_device(
                categories=['firewall', 'security_appliance', 'gateway', 'router'],
                source_types=['excel', 'paapi'],
                preferred_vendor=preferred_vendor,
                keywords=context_keywords + ['gateway', 'router', 'firewall', 'security'],
                excluded_keywords=['phone', 'tablet', 'laptop'],
                assumptions=assumptions,
                intent_label='gateway/firewall',
            )
            if gateway_item:
                gateway_category = self._item_category(gateway_item)
                if gateway_category not in {'gateway', 'router', 'firewall', 'security_appliance'}:
                    gateway_category = 'gateway'
                line_items.append(
                    self._line_from_catalog_item(
                        line_id=next_line_id(),
                        item=gateway_item,
                        quantity=1,
                        category_override=gateway_category,
                        selection_reason=gateway_reason,
                    )
                )
            else:
                line_items.append(
                    self._line_from_derived(
                        line_id=next_line_id(),
                        name='Gateway / Firewall (placeholder)',
                        category='gateway',
                        quantity=1,
                        unit_price=0.0,
                        selection_reason='Gateway requested by requirements but no catalog match found.',
                    )
                )

        needs_cellular_backup = (
            self._pref_bool(
                preferences,
                False,
                'needsCellularBackup',
                'needs_cellular_backup',
                'includeCellularBackup',
                'include_cellular_backup',
            )
            or self._is_yes(business_context.get('needsBackupInternet'))
            or self._is_yes(business_context.get('needsCellularBackup'))
        )
        if needs_cellular_backup:
            backup_qty = max(1, self._as_int(business_context.get('locations'), 1))
            backup_item, backup_reason = self._choose_requirement_device(
                categories=['cellular_gateway', 'router', 'hotspot'],
                source_types=['excel', 'paapi'],
                preferred_vendor=preferred_vendor,
                keywords=context_keywords + ['backup', 'internet', '5g', 'lte', 'cellular', 'failover', 'hotspot'],
                excluded_keywords=['laptop', 'tablet'],
                assumptions=assumptions,
                intent_label='backup internet',
            )
            if backup_item:
                line_items.append(
                    self._line_from_catalog_item(
                        line_id=next_line_id(),
                        item=backup_item,
                        quantity=backup_qty,
                        category_override='cellular_backup',
                        selection_reason=f'{backup_reason} Quantity aligned to site/locations.',
                    )
                )
            else:
                assumptions.append('Backup internet was requested; no catalog backup device found.')
                line_items.append(
                    self._line_from_derived(
                        line_id=next_line_id(),
                        name='5G Backup Internet Device (placeholder)',
                        category='cellular_backup',
                        quantity=backup_qty,
                        unit_price=0.0,
                        selection_reason='Backup internet requested but no compatible cellular device found in catalog.',
                    )
                )

        endpoint_laptop_qty = max(
            0,
            self._as_int(business_context.get('laptops'))
            + self._as_int(business_context.get('desktops')),
        )
        endpoint_phone_qty = max(0, self._as_int(business_context.get('mobilePhones')))
        endpoint_tablet_qty = max(
            0,
            self._as_int(business_context.get('tablets'))
            + self._as_int(business_context.get('customerTablets')),
        )

        endpoint_specs = [
            (
                'laptop',
                ['laptop'],
                endpoint_laptop_qty,
                'Business laptops / desktops',
                context_keywords + ['staff', 'employee', 'laptop', 'desktop'],
                exclusion_for_endpoint,
                False,
            ),
            (
                'tablet',
                ['tablet', 'laptop'],
                endpoint_tablet_qty,
                'Business tablets',
                context_keywords + ['tablet', 'touch'],
                exclusion_for_endpoint + ['phone'],
                True,
            ),
            (
                'phone',
                ['phone'],
                endpoint_phone_qty,
                'Business mobile phones',
                context_keywords + ['business', 'mobile', 'phone', 'smartphone', '5g'],
                exclusion_for_endpoint + ['tablet', 'laptop'],
                False,
            ),
        ]

        for (
            endpoint_category,
            endpoint_categories,
            endpoint_qty,
            fallback_name,
            endpoint_keywords,
            endpoint_excluded,
            require_keyword_hit,
        ) in endpoint_specs:
            if endpoint_qty <= 0:
                continue

            endpoint_item, endpoint_reason = self._choose_paapi_endpoint_device(
                categories=endpoint_categories,
                preferred_vendor=preferred_vendor,
                keywords=endpoint_keywords,
                excluded_keywords=endpoint_excluded,
                require_keyword_hit=require_keyword_hit,
            )
            if endpoint_item:
                line_items.append(
                    self._line_from_catalog_item(
                        line_id=next_line_id(),
                        item=endpoint_item,
                        quantity=endpoint_qty,
                        category_override=endpoint_category,
                        selection_reason=f'{endpoint_reason} Quantity derived from business intake.',
                    )
                )
            else:
                assumptions.append(
                    f'No PAAPI endpoint item found for category={endpoint_category} with requirement fit; added placeholder endpoint line.'
                )
                line_items.append(
                    self._line_from_derived(
                        line_id=next_line_id(),
                        name=f'{fallback_name} (placeholder)',
                        category=endpoint_category,
                        quantity=endpoint_qty,
                        unit_price=0.0,
                        selection_reason='Placeholder endpoint line added because no PAAPI catalog item was found.',
                    )
                )

        pos_qty = self._sum_business_counts(
            business_context,
            'posTerminals',
            'handheldPosDevices',
            'selfCheckoutMachines',
        )
        if pos_qty > 0:
            pos_item, pos_reason = self._choose_requirement_device(
                categories=['tablet', 'phone', 'laptop'],
                source_types=['paapi'],
                preferred_vendor=preferred_vendor,
                keywords=context_keywords + ['pos', 'point', 'sale', 'payment', 'terminal', 'checkout', 'kiosk'],
                excluded_keywords=['gateway', 'router', 'modem', 'hotspot'],
                assumptions=assumptions,
                intent_label='POS endpoints',
            )
            if pos_item:
                line_items.append(
                    self._line_from_catalog_item(
                        line_id=next_line_id(),
                        item=pos_item,
                        quantity=pos_qty,
                        category_override='pos_systems',
                        selection_reason=f'{pos_reason} Quantity derived from POS terminal counts.',
                    )
                )
            else:
                assumptions.append('POS device counts provided but no compatible endpoint product was found in catalog.')

        camera_qty = self._sum_business_counts(business_context, 'ipCameras')
        if camera_qty > 0:
            camera_item, camera_reason = self._choose_requirement_device(
                categories=['camera'],
                source_types=['excel', 'paapi'],
                preferred_vendor=preferred_vendor,
                keywords=context_keywords + ['camera', 'cctv', 'surveillance'],
                assumptions=assumptions,
                intent_label='security cameras',
            )
            if camera_item:
                line_items.append(
                    self._line_from_catalog_item(
                        line_id=next_line_id(),
                        item=camera_item,
                        quantity=camera_qty,
                        category_override='camera',
                        selection_reason=f'{camera_reason} Quantity derived from surveillance requirements.',
                    )
                )

        iot_qty = self._sum_business_counts(
            business_context,
            'sensors',
            'smartRefrigerators',
            'smartCoffeeMachines',
            'vendingMachines',
            'lightingControllers',
            'inventoryScanners',
            'facilityManagementSystems',
            'deliveryRobots',
            'inventoryRobots',
            'smartShelves',
            'rfidGates',
        )
        if iot_qty > 0:
            iot_item, iot_reason = self._choose_requirement_device(
                categories=['sensor'],
                source_types=['excel', 'paapi'],
                preferred_vendor=preferred_vendor,
                keywords=context_keywords + ['iot', 'sensor', 'smart', 'rfid', 'automation'],
                assumptions=assumptions,
                intent_label='iot devices',
            )
            if iot_item:
                line_items.append(
                    self._line_from_catalog_item(
                        line_id=next_line_id(),
                        item=iot_item,
                        quantity=iot_qty,
                        category_override='sensor',
                        selection_reason=f'{iot_reason} Quantity derived from IoT/smart device intake.',
                    )
                )

        if include_licenses:
            license_unit_price = self._as_float(pricing.get('licensePrice'))
            if license_unit_price <= 0 and ap_count > 0:
                derived_total = self._as_float(costs.get('licenses'))
                license_unit_price = round(derived_total / ap_count, 2) if derived_total > 0 else 0.0

            line_items.append(
                self._line_from_derived(
                    line_id=next_line_id(),
                    name='AP License',
                    category='managed_service_candidate',
                    quantity=ap_count,
                    unit_price=license_unit_price,
                    selection_reason='Derived from calculator licensing assumptions.',
                )
            )

        # Cabling is always a derived BOM line: type + area-based meter calculation.
        cable_type = self._normalize_cable_type(self._pref_value(preferences, 'cableType', 'cable_type'))
        floor_area_sqft = self._office_area_sqft(
            normalized_inputs=normalized_inputs,
            business_context=business_context,
            assumptions=assumptions,
        )
        wired_drop_count = self._estimate_wired_drop_count(line_items)
        if wired_drop_count > 0:
            avg_run_meters = math.sqrt(floor_area_sqft) * 0.3048
            slack_factor = 1.2
            total_cable_meters = round(avg_run_meters * wired_drop_count * slack_factor, 1)
            price_per_meter = self.CABLE_PRICE_PER_METER[cable_type]
            cable_quantity_meters = max(1, int(round(total_cable_meters)))
            cable_line = self._line_from_derived(
                line_id=next_line_id(),
                name=f'{cable_type} Structured Cabling',
                category='cabling',
                quantity=cable_quantity_meters,
                unit_price=price_per_meter,
                selection_reason=(
                    f'{cable_type} derived from office area using formula: sqrt({round(floor_area_sqft, 2)} sqft) '
                    f'× 0.3048 × {wired_drop_count} wired drops × 1.2 slack = {total_cable_meters}m.'
                ),
                sku=cable_type,
                connectivity='wired',
            )
            cable_line['cable_type'] = cable_type
            cable_line['cable_length_meters'] = total_cable_meters
            cable_line['price_per_meter'] = price_per_meter
            cable_line['wired_drop_count'] = wired_drop_count
            cable_line['office_area_sqft'] = round(floor_area_sqft, 2)
            cable_line['is_derived_bom'] = True
            projected_total = round(sum(float(line['line_total']) for line in line_items) + float(cable_line['line_total']), 2)
            if projected_total > 0:
                cable_line['cost_share_pct'] = round((float(cable_line['line_total']) / projected_total) * 100.0, 1)
            line_items.append(cable_line)
        else:
            assumptions.append('No wired devices were selected by SKU/category, so no CAT cabling line was added.')

        if include_installation:
            labor_unit = self._as_float(pricing.get('laborHoursPerAP')) * self._as_float(pricing.get('laborRate'))
            if labor_unit <= 0 and ap_count > 0:
                labor_total = self._as_float(costs.get('labor'))
                labor_unit = round(labor_total / ap_count, 2) if labor_total > 0 else 0.0

            line_items.append(
                self._line_from_derived(
                    line_id=next_line_id(),
                    name='Installation labor',
                    category='managed_service_candidate',
                    quantity=ap_count,
                    unit_price=labor_unit,
                    selection_reason='Derived non-catalog labor line from calculator labor assumptions.',
                )
            )

        if include_ups:
            accessory_items = self._list_excel_devices_by_category('accessory')
            ups_item = next(
                (
                    item
                    for item in accessory_items
                    if 'ups' in str(item.name or '').lower() or 'ups' in str((item.attributes or {}).get('model') or '').lower()
                ),
                None,
            )
            if ups_item:
                line_items.append(
                    self._line_from_catalog_item(
                        line_id=next_line_id(),
                        item=ups_item,
                        quantity=switch_count,
                        category_override='accessory',
                        selection_reason='Excel catalog UPS selection matched accessory inventory.',
                    )
                )
            else:
                ups_unit_price = self._as_float(pricing.get('upsPrice'))
                if ups_unit_price <= 0 and switch_count > 0:
                    ups_total = self._as_float(costs.get('upsCost'))
                    ups_unit_price = round(ups_total / switch_count, 2) if ups_total > 0 else 0.0

                assumptions.append('No UPS catalog SKU found; generated a derived UPS line from calculator pricing assumptions.')
                line_items.append(
                    self._line_from_derived(
                        line_id=next_line_id(),
                        name='UPS (derived)',
                        category='accessory',
                        quantity=switch_count,
                        unit_price=ups_unit_price,
                        selection_reason='Derived UPS line because no catalog UPS match was available.',
                    )
                )

        if include_managed_services:
            managed_services = self.catalog_service.list_items(
                item_type=CatalogItemType.SERVICE,
                category='managed_service',
                service_kind='managed_router',
                sort='price_low',
            )
            if managed_services:
                service_item = managed_services[0]
                line_items.append(
                    self._line_from_catalog_item(
                        line_id=next_line_id(),
                        item=service_item,
                        quantity=max(1, switch_count),
                        category_override='managed_service_candidate',
                        selection_reason='Managed service option added from existing managed service catalog tier.',
                    )
                )
            else:
                line_items.append(
                    self._line_from_derived(
                        line_id=next_line_id(),
                        name='Managed network service (placeholder)',
                        category='managed_service_candidate',
                        quantity=1,
                        unit_price=0.0,
                        selection_reason='No managed service SKU available; placeholder line added for later quote refinement.',
                    )
                )
                assumptions.append('Managed service placeholder was added because no managed service SKU was found.')

        subtotal = round(sum(float(line['line_total']) for line in line_items), 2)

        tax_pct = self._as_float(pricing.get('taxPct'), self._as_float(preferences.get('taxPct')))
        tax = round(subtotal * (tax_pct / 100.0), 2) if tax_pct > 0 else 0.0
        grand_total = round(subtotal + tax, 2)

        summary_text = (
            f'Generated V1 BOM with {len(line_items)} lines for {ap_count} AP(s) and {switch_count} switch(es). '
            f'Preferred vendor: {preferred_vendor or "not specified"}.'
        )

        return {
            'line_items': line_items,
            'subtotal': subtotal,
            'tax': tax,
            'grand_total': grand_total,
            'summary': summary_text,
            'assumptions': assumptions,
        }
