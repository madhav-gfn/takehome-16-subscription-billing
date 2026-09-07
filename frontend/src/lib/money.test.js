import { describe, it, expect } from 'vitest';
import { formatMoney } from './money.js';

describe('formatMoney', () => {
  it('returns "—" for null or undefined', () => {
    expect(formatMoney(null)).toBe('—');
    expect(formatMoney(undefined)).toBe('—');
  });

  it('returns "—" for an empty string', () => {
    expect(formatMoney('')).toBe('—');
  });

  it('formats positive numbers correctly', () => {
    expect(formatMoney(10.5)).toBe('£10.50');
    expect(formatMoney(1000)).toBe('£1,000.00');
    expect(formatMoney(0.99)).toBe('£0.99');
  });

  it('formats negative numbers correctly', () => {
    expect(formatMoney(-5)).toBe('-£5.00');
    expect(formatMoney(-1500.5)).toBe('-£1,500.50');
  });

  it('formats zero correctly', () => {
    expect(formatMoney(0)).toBe('£0.00');
    expect(formatMoney(-0)).toBe('-£0.00');
  });

  it('formats string numbers correctly', () => {
    expect(formatMoney('10.5')).toBe('£10.50');
    expect(formatMoney('1000')).toBe('£1,000.00');
    expect(formatMoney('-5')).toBe('-£5.00');
    expect(formatMoney('0')).toBe('£0.00');
  });

  it('returns the original string for invalid numbers', () => {
    expect(formatMoney('abc')).toBe('abc');
    expect(formatMoney('10.5.5')).toBe('10.5.5');
    expect(formatMoney('£10')).toBe('£10');
  });

  it('returns the original value converted to string for invalid types if not null or undefined', () => {
    expect(formatMoney({})).toBe('[object Object]');
    // Although you probably wouldn't pass arrays or objects intentionally,
    // it tests the fallback String(value) behavior.
    expect(formatMoney(['a', 'b'])).toBe('a,b');
  });
});
