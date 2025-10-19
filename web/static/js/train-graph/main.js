/**
 * Main controller for the Train Graph Viewer
 * 
 * This module initializes the entire train graph viewer and handles
 * user interactions with the controls.
 */

document.addEventListener('DOMContentLoaded', () => {
  // Initialize components
  const config = new TrainGraphConfig();
  let mappers = null;
  let filters = null;
  let renderer = null;
  
  // DOM elements
  const trainGraphContainer = document.getElementById('train-graph');
  const graphLoading = document.getElementById('train-graph-loading');
  const configSelect = document.getElementById('config-select');
  const datePicker = document.getElementById('date-picker');
  const refreshButton = document.getElementById('refresh-graph');
  
  // Control buttons
  const showPassengerCheckbox = document.getElementById('show-passenger');
  const showFreightCheckbox = document.getElementById('show-freight');
  const showECSCheckbox = document.getElementById('show-ecs');
  const showPlatformsCheckbox = document.getElementById('show-platforms');
  const showAssociationsCheckbox = document.getElementById('show-associations');
  const enableFiltersCheckbox = document.getElementById('enable-filters');
  
  // Zoom controls
  const zoomInButton = document.getElementById('zoom-in');
  const zoomOutButton = document.getElementById('zoom-out');
  const resetViewButton = document.getElementById('reset-view');
  const exportSvgButton = document.getElementById('export-svg');
  
  // Set default date
  const today = new Date();
  datePicker.value = today.toISOString().split('T')[0];
  
  /**
   * Initialize the application
   */
  async function init() {
    try {
      // Load available configurations
      await config.loadConfigs();
      
      // Populate the config select dropdown
      config.populateConfigSelect(configSelect);
      
      // Default to first config
      if (configSelect.options.length > 0) {
        configSelect.selectedIndex = 0;
      }
      
      // Set up event listeners
      refreshButton.addEventListener('click', loadGraph);
      showPassengerCheckbox.addEventListener('change', updateFilters);
      showFreightCheckbox.addEventListener('change', updateFilters);
      showECSCheckbox.addEventListener('change', updateFilters);
      showAssociationsCheckbox.addEventListener('change', updateGraph);
      enableFiltersCheckbox.addEventListener('change', updateFilters);
      
      // Zoom controls
      zoomInButton.addEventListener('click', () => renderer && renderer.zoomIn());
      zoomOutButton.addEventListener('click', () => renderer && renderer.zoomOut());
      resetViewButton.addEventListener('click', () => renderer && renderer.resetZoom());
      exportSvgButton.addEventListener('click', () => renderer && renderer.exportSVG());
      
      // Load the initial graph
      loadGraph();
    } catch (error) {
      console.error('Error initializing train graph:', error);
      showError('Failed to initialize train graph viewer');
    }
  }
  
  /**
   * Load train graph data and render it
   */
  async function loadGraph() {
    try {
      showLoading(true);
      
      // Get selected configuration and date
      const configId = configSelect.value;
      const dateStr = datePicker.value;
      
      if (!configId) {
        throw new Error('No configuration selected');
      }
      
      if (!dateStr) {
        throw new Error('No date selected');
      }
      
      console.log('Loading configuration:', configId);
      // Load the selected configuration
      const currentConfig = await config.loadConfig(configId);
      console.log('Loaded configuration:', currentConfig);
      
      // Get train data from the API
      console.log('Fetching train data for locations:', currentConfig.locations);
      const trains = await fetchTrainData(currentConfig, dateStr);
      console.log('Fetched train data:', trains.length, 'trains');
      
      // Clear any existing graph
      trainGraphContainer.innerHTML = '';
      
      // Check if we have train data before proceeding
      if (!trains || trains.length === 0) {
        // Show a friendly message instead of trying to render an empty graph
        trainGraphContainer.innerHTML = `
          <div class="no-data-message" style="text-align: center; margin-top: 100px; color: #6c757d;">
            <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path>
              <circle cx="9" cy="7" r="4"></circle>
              <path d="M22 21v-2a4 4 0 0 0-3-3.87"></path>
              <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
            </svg>
            <h3>No train data available</h3>
            <p>There are no trains scheduled for the selected locations and date.</p>
            <p>Try selecting a different date or location configuration.</p>
          </div>
        `;
        // Hide the loading indicator
        showLoading(false);
        return;
      }
      
      try {
        // Create new mappers, filters, and renderer
        mappers = new TrainGraphMappers(
          trainGraphContainer.offsetWidth,
          trainGraphContainer.offsetHeight,
          currentConfig
        );
        
        filters = new TrainGraphFilters(currentConfig);
        updateFilters(); // Set initial filter settings
        
        renderer = new TrainGraphRenderer(
          trainGraphContainer,
          trains,
          currentConfig,
          mappers,
          filters
        );
        
        // Render the graph
        renderer.render();
      } catch (error) {
        console.error('Error initializing train graph components:', error);
        trainGraphContainer.innerHTML = `
          <div class="error-message" style="text-align: center; margin-top: 100px; color: #dc3545;">
            <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
            <h3>Error rendering train graph</h3>
            <p>${error.message || 'An unexpected error occurred'}</p>
          </div>
        `;
        showLoading(false);
      }
      
      showLoading(false);
    } catch (error) {
      console.error('Error loading train graph:', error);
      showError('Failed to load train graph data: ' + error.message);
      showLoading(false);
    }
  }
  
  /**
   * Fetch train data from the API
   * @param {Object} currentConfig - Current configuration
   * @param {string} dateStr - Date string (YYYY-MM-DD)
   * @returns {Promise} Promise that resolves with train data
   */
  async function fetchTrainData(currentConfig, dateStr) {
    // Get location list from config
    const locations = currentConfig.locations;
    
    if (!locations || locations.length === 0) {
      throw new Error('No locations defined in configuration');
    }
    
    // Build URL with locations and date
    const url = `/web/api/train-graph/schedules?date_str=${dateStr}&locations=${locations.join(',')}`;
    
    // Fetch the data
    const response = await fetch(url);
    
    if (!response.ok) {
      let errorMessage = `Failed to fetch train data: ${response.status} ${response.statusText}`;
      
      try {
        const errorData = await response.json();
        if (errorData.error) {
          errorMessage = errorData.error;
        }
      } catch (e) {
        // Ignore JSON parsing errors
      }
      
      throw new Error(errorMessage);
    }
    
    const data = await response.json();
    
    // Return the schedules
    return data.schedules || [];
  }
  
  /**
   * Update filter settings based on checkbox values
   */
  function updateFilters() {
    if (!filters) return;
    
    // Get current filter settings from checkboxes
    const settings = {
      showPassenger: showPassengerCheckbox.checked,
      showFreight: showFreightCheckbox.checked,
      showECS: showECSCheckbox.checked,
      enableFilters: enableFiltersCheckbox.checked
    };
    
    // Update filters
    filters.updateSettings(settings);
    
    // Re-render the graph
    updateGraph();
  }
  
  /**
   * Update the graph with current settings
   */
  function updateGraph() {
    if (!renderer) return;
    
    // Re-render the graph
    renderer.render();
  }
  
  /**
   * Show or hide the loading indicator
   * @param {boolean} show - Whether to show the loading indicator
   */
  function showLoading(show) {
    graphLoading.style.display = show ? 'flex' : 'none';
  }
  
  /**
   * Show an error message
   * @param {string} message - Error message to display
   */
  function showError(message) {
    // Create alert element
    const alertElement = document.createElement('div');
    alertElement.className = 'alert alert-danger mt-3';
    alertElement.textContent = message;
    
    // Add dismiss button
    const dismissButton = document.createElement('button');
    dismissButton.type = 'button';
    dismissButton.className = 'btn-close';
    dismissButton.setAttribute('data-bs-dismiss', 'alert');
    dismissButton.setAttribute('aria-label', 'Close');
    alertElement.appendChild(dismissButton);
    
    // Insert before the refresh button
    refreshButton.parentNode.insertBefore(alertElement, refreshButton);
    
    // Remove after a delay
    setTimeout(() => {
      if (alertElement.parentNode) {
        alertElement.parentNode.removeChild(alertElement);
      }
    }, 5000);
  }
  
  // Initialize the application
  init();
});