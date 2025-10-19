/**
 * Mappers for the Train Graph Viewer
 * 
 * These functions handle converting between data values (time, locations) 
 * and pixel coordinates for rendering.
 */

class TrainGraphMappers {
  constructor(width, height, config) {
    this.width = width;
    this.height = height;
    this.config = config;
    this.padding = { top: 40, right: 30, bottom: 50, left: 100 };
    this.setupScales();
  }

  setupScales() {
    const { width, height, padding, config } = this;
    const { locations } = config;

    // Set up the location scale (vertical) - locations mapped to Y coordinates
    this.locationScale = d3.scalePoint()
      .domain(locations)
      .range([padding.top, height - padding.bottom])
      .padding(0.5);

    // Set up the time scale (horizontal) - time in minutes mapped to X coordinates
    // We'll use 24 hours (00:00 to 23:59)
    const timeRange = [0, 24 * 60]; // Minutes in a day
    this.timeScale = d3.scaleLinear()
      .domain(timeRange)
      .range([padding.left, width - padding.right]);

    // If direction is up, invert location scale
    if (config.direction === 'up') {
      this.locationScale = d3.scalePoint()
        .domain([...locations].reverse())  // Reverse the array to invert the scale
        .range([padding.top, height - padding.bottom])
        .padding(0.5);
    }
  }

  /**
   * Convert a time string (HH:MM) to minutes since midnight
   * @param {string} timeStr - Time in HH:MM format
   * @returns {number} Minutes since midnight
   */
  timeToMinutes(timeStr) {
    if (!timeStr) return null;
    
    // Handle ISO format dates (extract time portion)
    if (timeStr.includes('T')) {
      timeStr = timeStr.split('T')[1].substring(0, 5);
    }
    
    const [hours, minutes] = timeStr.split(':').map(Number);
    return hours * 60 + minutes;
  }

  /**
   * Convert a time string to X coordinate
   * @param {string} timeStr - Time in HH:MM format
   * @returns {number} X coordinate
   */
  timeToX(timeStr) {
    const minutes = this.timeToMinutes(timeStr);
    if (minutes === null) return null;
    return this.timeScale(minutes);
  }

  /**
   * Convert a TIPLOC code to Y coordinate
   * @param {string} tiploc - TIPLOC location code
   * @returns {number} Y coordinate
   */
  locationToY(tiploc) {
    return this.locationScale(tiploc);
  }

  /**
   * Generate time labels for the X axis
   * @returns {Array} Array of time labels
   */
  getTimeLabels() {
    const labels = [];
    // Create labels every hour
    for (let hour = 0; hour < 24; hour++) {
      const timeStr = `${hour.toString().padStart(2, '0')}:00`;
      const minutes = hour * 60;
      const x = this.timeScale(minutes);
      labels.push({
        time: timeStr,
        time_value: hour * 100, // 24-hour format numeric value
        x,
        is_major: hour % 3 === 0, // Major tick every 3 hours
      });
    }
    return labels;
  }

  /**
   * Get time axis points for the graph
   * @returns {Array} Array of time axis point objects
   */
  getTimeAxisPoints() {
    const points = [];
    // Create points every 15 minutes
    for (let minutes = 0; minutes < 24 * 60; minutes += 15) {
      const hour = Math.floor(minutes / 60);
      const min = minutes % 60;
      const timeStr = `${hour.toString().padStart(2, '0')}:${min.toString().padStart(2, '0')}`;
      const x = this.timeScale(minutes);
      
      points.push({
        time: timeStr,
        time_value: hour * 100 + min,
        x,
        is_major: min === 0, // Major tick on the hour
      });
    }
    return points;
  }

  /**
   * Get location points for the location axis
   * @returns {Array} Array of location point objects
   */
  getLocationAxisPoints() {
    const { config } = this;
    return config.locations.map(tiploc => {
      return {
        tiploc,
        y: this.locationToY(tiploc),
        display_name: config.display_names[tiploc] || tiploc
      };
    });
  }

  /**
   * Resize the mappers with new dimensions
   * @param {number} width - New width
   * @param {number} height - New height
   */
  resize(width, height) {
    this.width = width;
    this.height = height;
    this.setupScales();
  }

  /**
   * Create a path data string for a train's journey
   * @param {Object} train - Train object with locations
   * @returns {string} SVG path data string
   */
  createTrainPath(train) {
    const locations = train.locations.filter(loc => 
      // Only include locations that are in our config
      this.config.locations.includes(loc.tiploc)
    ).sort((a, b) => a.sequence - b.sequence);

    if (locations.length < 2) return ''; // Need at least 2 points to draw a line
    
    const points = [];
    
    for (const loc of locations) {
      const y = this.locationToY(loc.tiploc);
      
      // Arrival point (if available)
      if (loc.arr || loc.public_arr) {
        const x = this.timeToX(loc.arr || loc.public_arr);
        if (x !== null) points.push({ x, y });
      }
      
      // Departure point (if available)
      if (loc.dep || loc.public_dep) {
        const x = this.timeToX(loc.dep || loc.public_dep);
        if (x !== null) points.push({ x, y });
      }
      
      // Pass time (if available and no arrival/departure)
      if (!loc.arr && !loc.dep && !loc.public_arr && !loc.public_dep && loc.pass_time) {
        const x = this.timeToX(loc.pass_time);
        if (x !== null) points.push({ x, y });
      }
    }
    
    // Sort points by x value to ensure correct path
    points.sort((a, b) => a.x - b.x);
    
    if (points.length < 2) return ''; // Need at least 2 points after filtering
    
    // Generate the path data
    try {
      // Make sure we have an array of valid points
      if (!Array.isArray(points) || points.length < 2) {
        return '';
      }
      
      // Check if all points have valid x,y coordinates
      for (const point of points) {
        if (typeof point.x !== 'number' || typeof point.y !== 'number' || 
            isNaN(point.x) || isNaN(point.y)) {
          console.warn('Invalid point found:', point);
          return '';
        }
      }
      
      const pathGenerator = d3.line()
        .x(d => d.x)
        .y(d => d.y)
        .curve(d3.curveMonotoneX); // Smooth curve
      
      // Generate and return the path string
      return pathGenerator(points);
    } catch (error) {
      console.error('Error generating train path:', error);
      return '';
    }
  }
}