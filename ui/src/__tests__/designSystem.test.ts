import { describe, it, expect } from 'vitest';
import designTokens from '../styles/design-system.css?inline';

const REQUIRED_COLOR_TOKENS = ['--bg-primary', '--text-primary', '--primary-500'];
const REQUIRED_SPACING_TOKENS = ['--space-2', '--space-6', '--space-12'];
const REQUIRED_ELEVATION_TOKENS = ['--border-primary', '--radius-md', '--shadow-base'];

describe('design-system token definitions', () => {
  it('retains key color tokens for accessibility states', () => {
    for (const token of REQUIRED_COLOR_TOKENS) {
      expect(designTokens, `missing ${token}`).toContain(token);
    }
  });

  it('retains spacing scale required by layout utilities', () => {
    for (const token of REQUIRED_SPACING_TOKENS) {
      expect(designTokens, `missing ${token}`).toContain(token);
    }
  });

  it('retains elevation primitives used by shared components', () => {
    for (const token of REQUIRED_ELEVATION_TOKENS) {
      expect(designTokens, `missing ${token}`).toContain(token);
    }
  });
});
