/**
 * Filters for the Train Graph Viewer
 * 
 * This module handles filtering logic to determine which trains should be 
 * displayed on the graph.
 */

class TrainGraphFilters {
  constructor(config) {
    this.config = config;
    this.filterSettings = {
      showPassenger: true,
      showFreight: true,
      showECS: true,
      enableFilters: true
    };
  }

  /**
   * Update filter settings
   * @param {Object} settings - New filter settings
   */
  updateSettings(settings) {
    this.filterSettings = { ...this.filterSettings, ...settings };
  }

  /**
   * Determine if a train should be shown based on filter rules
   * @param {Object} train - Train data object
   * @returns {boolean} True if train should be displayed
   */
  shouldShowTrain(train) {
    // First check train category filters
    if (!this.matchesTrainCategoryFilters(train)) {
      return false;
    }

    // Then check config filter rules if enabled
    if (this.filterSettings.enableFilters && this.config.filters && this.config.filters.length > 0) {
      return this.matchesConfigFilters(train);
    }

    // If we get here, show the train
    return true;
  }

  /**
   * Check if train matches the category filters (passenger, freight, ECS)
   * @param {Object} train - Train data object
   * @returns {boolean} True if train matches category filters
   */
  matchesTrainCategoryFilters(train) {
    const { showPassenger, showFreight, showECS } = this.filterSettings;
    const category = train.train_category || "";
    
    // Check common train categories based on first letter
    // Passenger trains: A-F, K-O, W
    // Freight trains: G-J, P-V
    // Empty coaching stock (ECS): Z
    
    // Passenger check
    if (!showPassenger && /^[A-F]|^[K-O]|^W/.test(category)) {
      return false;
    }
    
    // Freight check
    if (!showFreight && /^[G-J]|^[P-V]/.test(category)) {
      return false;
    }
    
    // ECS check
    if (!showECS && /^Z/.test(category)) {
      return false;
    }
    
    return true;
  }

  /**
   * Check if train matches the config filter rules
   * @param {Object} train - Train data object
   * @returns {boolean} True if train matches filter rules
   */
  matchesConfigFilters(train) {
    const { filters, filter_mode } = this.config;
    
    // If no filters, show train
    if (!filters || filters.length === 0) {
      return true;
    }
    
    // Get all locations that match each filter criterion
    const matchResults = filters.map(filter => this.matchesFilter(train, filter));
    
    // Apply filter mode logic
    switch (filter_mode) {
      case 'match_any':
        // Train matches if any filter matches
        return matchResults.some(result => result);
        
      case 'match_all':
        // Train matches if all filters match
        return matchResults.every(result => result);
        
      case 'match_none':
        // Train matches if no filters match
        return !matchResults.some(result => result);
        
      default:
        // Default to match_any
        return matchResults.some(result => result);
    }
  }

  /**
   * Check if a train matches a specific filter rule
   * @param {Object} train - Train data object
   * @param {Object} filter - Filter rule
   * @returns {boolean} True if train matches filter
   */
  matchesFilter(train, filter) {
    const { locations } = train;
    
    // No locations means no match
    if (!locations || locations.length === 0) {
      return false;
    }
    
    // Check if any location matches all the filter criteria
    return locations.some(loc => {
      // Check location TIPLOC
      if (filter.location && loc.tiploc !== filter.location) {
        return false;
      }
      
      // Check platform
      if (filter.platform && loc.platform !== filter.platform) {
        return false;
      }
      
      // Check line
      if (filter.line && loc.line !== filter.line) {
        return false;
      }
      
      // Check path
      if (filter.path && loc.path !== filter.path) {
        return false;
      }
      
      // If we get here, location matches all specified criteria
      return true;
    });
  }
}