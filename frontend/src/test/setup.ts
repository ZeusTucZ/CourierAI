// Setup file for jsdom testing
if (typeof window !== 'undefined') {
  // Leaflet mocks for JSDOM
  window.URL.createObjectURL = () => '';
}
