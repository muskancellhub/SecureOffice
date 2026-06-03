import { useRef, useCallback, ChangeEvent, InputHTMLAttributes } from 'react';

const MASK = '(###) ###-####';
const DIGIT_PLACEHOLDER = '_';

function digitsOnly(s: string): string {
  return s.replace(/\D/g, '');
}

function applyMask(digits: string): string {
  let out = '';
  let d = 0;
  for (let i = 0; i < MASK.length; i++) {
    if (d >= digits.length) {
      out += MASK[i] === '#' ? DIGIT_PLACEHOLDER : MASK[i];
    } else if (MASK[i] === '#') {
      out += digits[d++];
    } else {
      out += MASK[i];
    }
  }
  return out;
}

function cursorAfterDigit(formatted: string, digitIndex: number): number {
  let count = 0;
  for (let i = 0; i < formatted.length; i++) {
    if (/\d/.test(formatted[i])) {
      count++;
      if (count === digitIndex) return i + 1;
    }
  }
  return formatted.length;
}

interface PhoneInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'onChange' | 'value' | 'type'> {
  value: string;
  onChange: (raw: string) => void;
}

export const PhoneInput = ({ value, onChange, ...rest }: PhoneInputProps) => {
  const ref = useRef<HTMLInputElement>(null);
  const digits = digitsOnly(value);
  const display = digits.length > 0 ? applyMask(digits) : '';

  const handleChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const raw = e.target.value;
      const newDigits = digitsOnly(raw).slice(0, 10);
      onChange(newDigits);

      requestAnimationFrame(() => {
        if (ref.current) {
          const pos = cursorAfterDigit(applyMask(newDigits), newDigits.length);
          ref.current.setSelectionRange(pos, pos);
        }
      });
    },
    [onChange],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Backspace' && digits.length > 0) {
        e.preventDefault();
        const newDigits = digits.slice(0, -1);
        onChange(newDigits);
        requestAnimationFrame(() => {
          if (ref.current) {
            const pos = cursorAfterDigit(applyMask(newDigits), newDigits.length);
            ref.current.setSelectionRange(pos, pos);
          }
        });
      }
    },
    [digits, onChange],
  );

  return (
    <input
      ref={ref}
      type="tel"
      value={display}
      onChange={handleChange}
      onKeyDown={handleKeyDown}
      placeholder="(___) ___-____"
      {...rest}
    />
  );
};
