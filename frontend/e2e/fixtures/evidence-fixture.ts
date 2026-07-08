import { test as base, type Locator, type Page, type TestInfo } from '@playwright/test';

/**
 * Test evidence helpers.
 *
 * Playwright's built-in screenshots/videos are useful, but videos can miss
 * meaningful UI states when tests run quickly or use storageState. These
 * helpers attach step screenshots directly to the HTML report for passed and
 * failed tests.
 */

type EvidenceFixtures = {
  captureEvidence: (label: string) => Promise<void>;
  captureStepScreenshot: (stepName: string) => Promise<void>;
};

type PageWithEvidenceInstrumentation = Page & {
  __stepScreenshotInstrumentationInstalled?: boolean;
};

type LocatorWithEvidenceInstrumentation = Locator & {
  __stepScreenshotInstrumentationInstalled?: boolean;
};

const screenshotCounters = new WeakMap<TestInfo, number>();

const sanitizeStepName = (stepName: string) =>
  stepName
    .replace(/[^a-z0-9]+/gi, '-')
    .replace(/^-+|-+$/g, '')
    .toLowerCase()
    .slice(0, 80) || 'step';

const formatSelectorLabel = (source: string, args: unknown[]) => {
  const firstArg = args[0];
  const options = args[1];
  if (options && typeof options === 'object' && 'name' in options) {
    const roleName = (options as { name?: unknown }).name;
    if (typeof roleName === 'string') {
      return `${source}: ${String(firstArg)} "${roleName.slice(0, 80)}"`;
    }
    if (roleName instanceof RegExp) {
      return `${source}: ${String(firstArg)} ${roleName.toString().slice(0, 80)}`;
    }
  }

  if (typeof firstArg === 'string') {
    return `${source}: ${firstArg.slice(0, 80)}`;
  }
  if (firstArg instanceof RegExp) {
    return `${source}: ${firstArg.toString().slice(0, 80)}`;
  }
  if (typeof firstArg === 'number') {
    return `${source}: ${firstArg}`;
  }

  return source;
};

/**
 * Capture a full-page screenshot and attach it to the Playwright HTML report.
 *
 * This helper is intentionally best-effort: a screenshot failure should never
 * change the behavior or result of an existing test.
 */
export async function captureStepScreenshot(
  page: Page,
  testInfo: TestInfo,
  stepName: string,
): Promise<void> {
  if (page.isClosed()) return;

  const nextCount = (screenshotCounters.get(testInfo) ?? 0) + 1;
  screenshotCounters.set(testInfo, nextCount);

  const paddedCount = String(nextCount).padStart(2, '0');
  const cleanStepName = sanitizeStepName(stepName);
  const attachmentName = `step-${paddedCount}-${cleanStepName}`;

  try {
    const body = await page.screenshot({
      fullPage: true,
      timeout: 10_000,
    });

    await testInfo.attach(attachmentName, {
      body,
      contentType: 'image/png',
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);

    try {
      await testInfo.attach(`${attachmentName}-not-captured`, {
        body: Buffer.from(message),
        contentType: 'text/plain',
      });
    } catch {
      // Keep evidence capture from affecting test behavior.
    }
  }
}

export function instrumentPageForStepScreenshots(page: Page, testInfo: TestInfo): Page {
  const instrumentedPage = page as PageWithEvidenceInstrumentation;
  if (instrumentedPage.__stepScreenshotInstrumentationInstalled) return page;

  instrumentedPage.__stepScreenshotInstrumentationInstalled = true;

  const capture = async (stepName: string) => {
    await captureStepScreenshot(page, testInfo, stepName);
  };

  const patchPageAction = <MethodName extends keyof Page>(
    methodName: MethodName,
    getLabel: (args: unknown[]) => string,
    captureBefore = false,
  ) => {
    const original = page[methodName];
    if (typeof original !== 'function') return;

    (page as unknown as Record<MethodName, unknown>)[methodName] = async (...args: unknown[]) => {
      const label = getLabel(args);
      if (captureBefore) {
        await capture(`before ${label}`);
      }

      const result = await (original as (...methodArgs: unknown[]) => Promise<unknown>).apply(page, args);
      await capture(`after ${label}`);
      return result;
    };
  };

  const patchLocatorFactory = <MethodName extends keyof Page>(
    methodName: MethodName,
    getLabel: (args: unknown[]) => string,
  ) => {
    const original = page[methodName];
    if (typeof original !== 'function') return;

    (page as unknown as Record<MethodName, unknown>)[methodName] = (...args: unknown[]) => {
      const locator = (original as (...methodArgs: unknown[]) => Locator).apply(page, args);
      return instrumentLocator(locator, testInfo, getLabel(args));
    };
  };

  patchPageAction('goto', (args) => `page loaded ${String(args[0] ?? '')}`);
  patchPageAction('reload', () => 'page reloaded');
  patchPageAction('waitForURL', (args) => `navigation matched ${String(args[0] ?? '')}`);
  patchPageAction('waitForLoadState', (args) => `load state ${String(args[0] ?? 'load')}`);

  patchPageAction('click', (args) => `click ${String(args[0] ?? '')}`, true);
  patchPageAction('dblclick', (args) => `double click ${String(args[0] ?? '')}`, true);
  patchPageAction('fill', (args) => `fill ${String(args[0] ?? '')}`, true);
  patchPageAction('type', (args) => `type ${String(args[0] ?? '')}`, true);
  patchPageAction('press', (args) => `press ${String(args[0] ?? '')}`, true);
  patchPageAction('selectOption', (args) => `select option ${String(args[0] ?? '')}`, true);
  patchPageAction('check', (args) => `check ${String(args[0] ?? '')}`, true);
  patchPageAction('uncheck', (args) => `uncheck ${String(args[0] ?? '')}`, true);
  patchPageAction('setInputFiles', (args) => `set input files ${String(args[0] ?? '')}`, true);

  patchLocatorFactory('locator', (args) => formatSelectorLabel('locator', args));
  patchLocatorFactory('getByRole', (args) => formatSelectorLabel('role', args));
  patchLocatorFactory('getByLabel', (args) => formatSelectorLabel('label', args));
  patchLocatorFactory('getByPlaceholder', (args) => formatSelectorLabel('placeholder', args));
  patchLocatorFactory('getByText', (args) => formatSelectorLabel('text', args));
  patchLocatorFactory('getByTestId', (args) => formatSelectorLabel('test id', args));
  patchLocatorFactory('getByTitle', (args) => formatSelectorLabel('title', args));
  patchLocatorFactory('getByAltText', (args) => formatSelectorLabel('alt text', args));

  return page;
}

function instrumentLocator(locator: Locator, testInfo: TestInfo, label: string): Locator {
  const instrumentedLocator = locator as LocatorWithEvidenceInstrumentation;
  if (instrumentedLocator.__stepScreenshotInstrumentationInstalled) return locator;

  instrumentedLocator.__stepScreenshotInstrumentationInstalled = true;

  const page = locator.page();
  const capture = async (stepName: string) => {
    await captureStepScreenshot(page, testInfo, stepName);
  };

  const patchLocatorAction = <MethodName extends keyof Locator>(
    methodName: MethodName,
    actionLabel: string,
    captureBefore = true,
  ) => {
    const original = locator[methodName];
    if (typeof original !== 'function') return;

    (locator as unknown as Record<MethodName, unknown>)[methodName] = async (...args: unknown[]) => {
      if (captureBefore) {
        await capture(`before ${actionLabel} ${label}`);
      }

      const result = await (original as (...methodArgs: unknown[]) => Promise<unknown>).apply(locator, args);
      await capture(`after ${actionLabel} ${label}`);
      return result;
    };
  };

  const patchNestedLocatorFactory = <MethodName extends keyof Locator>(
    methodName: MethodName,
    sourceLabel: string,
  ) => {
    const original = locator[methodName];
    if (typeof original !== 'function') return;

    (locator as unknown as Record<MethodName, unknown>)[methodName] = (...args: unknown[]) => {
      const nestedLocator = (original as (...methodArgs: unknown[]) => Locator).apply(locator, args);
      return instrumentLocator(
        nestedLocator,
        testInfo,
        `${label} -> ${formatSelectorLabel(sourceLabel, args)}`,
      );
    };
  };

  patchLocatorAction('click', 'click');
  patchLocatorAction('dblclick', 'double click');
  patchLocatorAction('fill', 'fill');
  patchLocatorAction('type', 'type');
  patchLocatorAction('press', 'press');
  patchLocatorAction('selectOption', 'select option');
  patchLocatorAction('check', 'check');
  patchLocatorAction('uncheck', 'uncheck');
  patchLocatorAction('setInputFiles', 'set input files');

  patchNestedLocatorFactory('locator', 'locator');
  patchNestedLocatorFactory('getByRole', 'role');
  patchNestedLocatorFactory('getByLabel', 'label');
  patchNestedLocatorFactory('getByPlaceholder', 'placeholder');
  patchNestedLocatorFactory('getByText', 'text');
  patchNestedLocatorFactory('getByTestId', 'test id');
  patchNestedLocatorFactory('getByTitle', 'title');
  patchNestedLocatorFactory('getByAltText', 'alt text');
  patchNestedLocatorFactory('first', 'first');
  patchNestedLocatorFactory('last', 'last');
  patchNestedLocatorFactory('nth', 'nth');
  patchNestedLocatorFactory('filter', 'filter');
  patchNestedLocatorFactory('or', 'or');

  return locator;
}

export const test = base.extend<EvidenceFixtures>({
  page: async ({ page }, use, testInfo) => {
    instrumentPageForStepScreenshots(page, testInfo);
    await use(page);
    await captureStepScreenshot(page, testInfo, 'final result state');
  },

  captureStepScreenshot: async ({ page }, use, testInfo) => {
    await use(async (stepName: string) => {
      await captureStepScreenshot(page, testInfo, stepName);
    });
  },

  captureEvidence: async ({ page }, use, testInfo) => {
    await use(async (label: string) => {
      await captureStepScreenshot(page, testInfo, label);
    });
  },
});

export { expect } from '@playwright/test';
export type { Page, TestInfo } from '@playwright/test';
