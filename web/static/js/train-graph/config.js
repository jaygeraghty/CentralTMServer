/**
 * Configuration for the Train Graph Viewer
 * 
 * This module handles loading and managing graph configurations.
 */

class TrainGraphConfig {
  constructor() {
    this.configs = null;
    this.currentConfig = null;
  }

  /**
   * Load the list of available configurations
   * @returns {Promise} Promise that resolves with the list of configurations
   */
  async loadConfigs() {
    try {
      console.log('Fetching configurations from /web/api/train-graph/configs');
      const response = await fetch('/web/api/train-graph/configs');
      console.log('Config response status:', response.status);
      
      if (!response.ok) {
        throw new Error(`Failed to load configurations: ${response.status} ${response.statusText}`);
      }
      
      const responseText = await response.text();
      console.log('Raw config response:', responseText);
      
      try {
        this.configs = JSON.parse(responseText);
        console.log('Parsed configurations:', this.configs);
        return this.configs;
      } catch (parseError) {
        console.error('Error parsing configurations:', parseError);
        throw new Error(`Invalid JSON response: ${parseError.message}`);
      }
    } catch (error) {
      console.error('Error loading configurations:', error);
      // Provide default config if loading fails
      this.configs = {
        'default': {
          name: 'Default Configuration',
          locations: ['CHRX', 'WLOE'],
          direction: 'down',
          display_names: {
            'CHRX': 'Charing Cross',
            'WLOE': 'Waterloo East'
          },
          filters: []
        }
      };
      return this.configs;
    }
  }

  /**
   * Load a specific configuration by ID
   * @param {string} configId - ID of the configuration to load
   * @returns {Promise} Promise that resolves with the loaded configuration
   */
  async loadConfig(configId) {
    try {
      if (!this.configs) {
        await this.loadConfigs();
      }
      
      // If the config exists in our loaded configs, use it
      if (this.configs[configId]) {
        this.currentConfig = this.configs[configId];
        return this.currentConfig;
      }
      
      // Otherwise, try to fetch it specifically
      const response = await fetch(`/web/api/train-graph/configs/${configId}`);
      if (!response.ok) {
        throw new Error(`Failed to load configuration ${configId}: ${response.status} ${response.statusText}`);
      }
      
      this.currentConfig = await response.json();
      return this.currentConfig;
    } catch (error) {
      console.error(`Error loading configuration ${configId}:`, error);
      // Use default config if specific one fails
      this.currentConfig = this.configs.default || Object.values(this.configs)[0];
      return this.currentConfig;
    }
  }

  /**
   * Get the currently active configuration
   * @returns {Object} Current configuration
   */
  getCurrentConfig() {
    return this.currentConfig;
  }

  /**
   * Initialize select dropdown with available configurations
   * @param {HTMLElement} selectElement - The select element to populate
   */
  populateConfigSelect(selectElement) {
    if (!selectElement) return;
    
    // Clear existing options
    selectElement.innerHTML = '';
    
    // Add options for each configuration
    if (this.configs) {
      Object.keys(this.configs).forEach(configId => {
        const config = this.configs[configId];
        const option = document.createElement('option');
        option.value = configId;
        option.textContent = config.name || configId;
        selectElement.appendChild(option);
      });
    } else {
      // Add placeholder if configs not loaded
      const option = document.createElement('option');
      option.value = '';
      option.textContent = 'No configurations available';
      selectElement.appendChild(option);
    }
  }
}