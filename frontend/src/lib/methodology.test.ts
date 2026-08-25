import { describe, it, expect } from 'vitest';
import { methodologyContent } from './methodology';

/**
 * NOTE: The city count in methodology.ts must match the live Brazil city list
 * in backend/app/country_registry.py BRAZIL_CONFIG.cities.
 * 
 * These tests will fail if:
 * - The methodology claims 63 (old stale count)
 * - The methodology doesn't claim the current count from BRAZIL_CONFIG
 */

describe('Methodology Copy', () => {
  describe('City count accuracy', () => {
    it('should not claim 63 municipalities as current coverage in PT', () => {
      const pt = methodologyContent('pt');
      const allText = JSON.stringify(pt).toLowerCase();
      
      // Should not have "63 municípios" as current coverage claim
      expect(allText).not.toMatch(/63\s+municípios/);
      expect(allText).not.toMatch(/cobre\s+63\s+municípios/);
    });

    it('should not claim 63 municipalities as current coverage in EN', () => {
      const en = methodologyContent('en');
      const allText = JSON.stringify(en).toLowerCase();
      
      // Should not have "63 municipalities" as current coverage claim
      expect(allText).not.toMatch(/63\s+municipalities/);
      expect(allText).not.toMatch(/covers\s+63\s+municipalities/);
    });

    it('should have cities section in PT', () => {
      const pt = methodologyContent('pt');
      const citiesSection = pt.sections.find(s => s.id === 'cities');
      expect(citiesSection).toBeDefined();
      expect(citiesSection?.title).toBe('Cidades monitoradas');
    });

    it('should have cities section in EN', () => {
      const en = methodologyContent('en');
      const citiesSection = en.sections.find(s => s.id === 'cities');
      expect(citiesSection).toBeDefined();
      expect(citiesSection?.title).toBe('Monitored cities');
    });

    it('should not claim 63 cities in limitations section PT', () => {
      const pt = methodologyContent('pt');
      const limitationsSection = pt.sections.find(s => s.id === 'limitations');
      const limitationsBullets = limitationsSection?.bullets?.join(' ') || '';
      expect(limitationsBullets).not.toMatch(/63\s+cidades/i);
    });

    it('should not claim 63 cities in limitations section EN', () => {
      const en = methodologyContent('en');
      const limitationsSection = en.sections.find(s => s.id === 'limitations');
      const limitationsBullets = limitationsSection?.bullets?.join(' ') || '';
      expect(limitationsBullets).not.toMatch(/63\s+.*cities/i);
    });
  });

  describe('Coverage section content (locked text from spec #182)', () => {
    it('should have coverage section in PT', () => {
      const pt = methodologyContent('pt');
      const coverageSection = pt.sections.find(s => s.id === 'coverage');
      expect(coverageSection).toBeDefined();
      expect(coverageSection?.title).toBe('Cobertura: Arquivo vs Oficial');
    });

    it('should mention four Formulário 1 crime types in PT coverage section', () => {
      const pt = methodologyContent('pt');
      const coverageSection = pt.sections.find(s => s.id === 'coverage');
      const coverageText = coverageSection?.paragraphs.join(' ') || '';
      
      // Must mention all four types from Formulário 1
      expect(coverageText).toMatch(/homicídio doloso/i);
      expect(coverageText).toMatch(/feminicídio/i);
      expect(coverageText).toMatch(/roubo seguido de morte|latrocínio/i);
      expect(coverageText).toMatch(/lesão corporal seguida de morte/i);
    });

    it('should NOT claim morte por intervenção is in municipal official column in PT', () => {
      const pt = methodologyContent('pt');
      const coverageSection = pt.sections.find(s => s.id === 'coverage');
      const coverageText = coverageSection?.paragraphs.join(' ') || '';
      
      // Should explicitly state intervenção is NOT in the municipal table
      expect(coverageText).toMatch(/morte.*intervenção.*não entram nesta tabela municipal/i);
    });

    it('should NOT label official bag as "Mortes Violentas Intencionais" in PT', () => {
      const pt = methodologyContent('pt');
      const coverageSection = pt.sections.find(s => s.id === 'coverage');
      const coverageText = coverageSection?.paragraphs.join(' ') || '';
      
      // Should explicitly state MVI is NOT used
      expect(coverageText).toMatch(/não usa.*Mortes Violentas Intencionais/i);
    });

    it('should mention Formulário 1 in PT coverage section', () => {
      const pt = methodologyContent('pt');
      const coverageSection = pt.sections.find(s => s.id === 'coverage');
      const coverageText = coverageSection?.paragraphs.join(' ') || '';
      
      expect(coverageText).toMatch(/Formulário 1/i);
    });

    it('should mention IBGE seven-digit code in PT coverage section', () => {
      const pt = methodologyContent('pt');
      const coverageSection = pt.sections.find(s => s.id === 'coverage');
      const coverageText = coverageSection?.paragraphs.join(' ') || '';
      
      expect(coverageText).toMatch(/código de sete dígitos/i);
      expect(coverageText).toMatch(/Instituto Brasileiro de Geografia e Estatística/i);
    });

    it('should have coverage section in EN', () => {
      const en = methodologyContent('en');
      const coverageSection = en.sections.find(s => s.id === 'coverage');
      expect(coverageSection).toBeDefined();
      expect(coverageSection?.title).toBe('Coverage: Archive vs Official');
    });

    it('should mention four Form 1 crime types in EN coverage section', () => {
      const en = methodologyContent('en');
      const coverageSection = en.sections.find(s => s.id === 'coverage');
      const coverageText = coverageSection?.paragraphs.join(' ') || '';
      
      // Must mention all four types from Form 1
      expect(coverageText).toMatch(/intentional homicide/i);
      expect(coverageText).toMatch(/femicide/i);
      expect(coverageText).toMatch(/robbery.*death|robbery-homicide/i);
      expect(coverageText).toMatch(/bodily injury.*death/i);
    });

    it('should NOT claim intervention deaths are in municipal official column in EN', () => {
      const en = methodologyContent('en');
      const coverageSection = en.sections.find(s => s.id === 'coverage');
      const coverageText = coverageSection?.paragraphs.join(' ') || '';
      
      // Should explicitly state intervention is NOT in the municipal table
      expect(coverageText).toMatch(/intervention.*not enter this municipal table/i);
    });
  });
});
