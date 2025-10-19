/**
 * Renderer for the Train Graph Viewer
 * 
 * This module handles the rendering of the train graph using D3.js.
 */

class TrainGraphRenderer {
  constructor(container, trains, config, mappers, filters) {
    this.container = container;
    this.trains = trains;
    this.config = config;
    this.mappers = mappers;
    this.filters = filters;
    this.svg = null;
    this.zoom = null;
    this.selectedTrain = null;
    this.tooltip = document.getElementById('train-tooltip');
    this.init();
  }

  /**
   * Initialize the renderer
   */
  init() {
    const containerRect = this.container.getBoundingClientRect();
    const width = containerRect.width;
    const height = containerRect.height;

    // Update mappers with current dimensions
    this.mappers.resize(width, height);
    
    // Create SVG element
    this.svg = d3.select(this.container)
      .append('svg')
      .attr('width', width)
      .attr('height', height);

    // Add zoom behavior
    this.zoom = d3.zoom()
      .scaleExtent([0.5, 5])
      .on('zoom', (event) => {
        this.svg.select('.graph-content')
          .attr('transform', event.transform);
      });

    this.svg.call(this.zoom);
    
    // Create a group for all graph content so it can be zoomed together
    this.graphContent = this.svg.append('g')
      .attr('class', 'graph-content');
    
    // Initialize graph layers
    this.gridLayer = this.graphContent.append('g').attr('class', 'grid-layer');
    this.trainLayer = this.graphContent.append('g').attr('class', 'train-layer');
    this.axisLayer = this.graphContent.append('g').attr('class', 'axis-layer');
    this.labelLayer = this.graphContent.append('g').attr('class', 'label-layer');
    this.associationLayer = this.graphContent.append('g').attr('class', 'association-layer');
    
    // Set up event listeners
    window.addEventListener('resize', this.handleResize.bind(this));
  }

  /**
   * Handle window resize events
   */
  handleResize() {
    const containerRect = this.container.getBoundingClientRect();
    const width = containerRect.width;
    const height = containerRect.height;
    
    // Update SVG dimensions
    this.svg
      .attr('width', width)
      .attr('height', height);
    
    // Update mappers with new dimensions
    this.mappers.resize(width, height);
    
    // Redraw the graph
    this.render();
  }

  /**
   * Render the train graph
   */
  render() {
    this.renderGrid();
    this.renderAxes();
    this.renderTrains();
    this.renderAssociations();
    this.setupInteractions();
  }

  /**
   * Render the grid
   */
  renderGrid() {
    this.gridLayer.selectAll('*').remove();
    
    // Render horizontal grid lines (for locations)
    const locationPoints = this.mappers.getLocationAxisPoints();
    
    this.gridLayer.selectAll('.location-grid-line')
      .data(locationPoints)
      .enter()
      .append('line')
      .attr('class', 'location-grid-line grid-line')
      .attr('x1', this.mappers.padding.left)
      .attr('y1', d => d.y)
      .attr('x2', this.mappers.width - this.mappers.padding.right)
      .attr('y2', d => d.y)
      .attr('stroke', '#495057')
      .attr('stroke-opacity', 0.2)
      .attr('stroke-width', 1)
      .attr('stroke-dasharray', '3,3');
    
    // Render vertical grid lines (for time)
    try {
      const timePoints = this.mappers.getTimeAxisPoints();
      
      if (Array.isArray(timePoints) && timePoints.length > 0) {
        const majorTimePoints = timePoints.filter(d => d && d.is_major);
        
        if (majorTimePoints.length > 0) {
          this.gridLayer.selectAll('.time-grid-line')
            .data(majorTimePoints) // Only show major time lines
            .enter()
            .append('line')
            .attr('class', 'time-grid-line grid-line')
            .attr('x1', d => d && typeof d.x === 'number' ? d.x : 0)
            .attr('y1', this.mappers.padding ? this.mappers.padding.top : 0)
            .attr('x2', d => d && typeof d.x === 'number' ? d.x : 0)
            .attr('y2', this.mappers.height - (this.mappers.padding ? this.mappers.padding.bottom : 0))
            .attr('stroke', '#495057')
            .attr('stroke-opacity', 0.2)
            .attr('stroke-width', 1);
        }
      }
    } catch (error) {
      console.error('Error rendering time grid lines:', error);
    }
  }

  /**
   * Render the axes
   */
  renderAxes() {
    this.axisLayer.selectAll('*').remove();
    this.labelLayer.selectAll('*').remove();
    
    // Render location axis (Y axis)
    try {
      const locationPoints = this.mappers.getLocationAxisPoints();
      
      if (Array.isArray(locationPoints) && locationPoints.length > 0) {
        // Location ticks
        this.axisLayer.selectAll('.location-tick')
          .data(locationPoints)
          .enter()
          .append('line')
          .attr('class', 'location-tick')
          .attr('x1', this.mappers.padding ? this.mappers.padding.left - 5 : 0)
          .attr('y1', d => d && typeof d.y === 'number' ? d.y : 0)
          .attr('x2', this.mappers.padding ? this.mappers.padding.left : 5)
          .attr('y2', d => d && typeof d.y === 'number' ? d.y : 0)
          .attr('stroke', '#495057')
          .attr('stroke-width', 1);
        
        // Location labels
        this.labelLayer.selectAll('.location-label')
          .data(locationPoints)
          .enter()
          .append('text')
          .attr('class', 'location-label')
          .attr('x', this.mappers.padding ? this.mappers.padding.left - 10 : 0)
          .attr('y', d => d && typeof d.y === 'number' ? d.y : 0)
          .attr('text-anchor', 'end')
          .attr('dominant-baseline', 'middle')
          .text(d => d && d.display_name ? d.display_name : '');
      }
    } catch (error) {
      console.error('Error rendering location axis:', error);
    }
    
    // Render time axis (X axis)
    try {
      const timePoints = this.mappers.getTimeAxisPoints();
      
      if (Array.isArray(timePoints) && timePoints.length > 0) {
        // Time ticks
        this.axisLayer.selectAll('.time-tick')
          .data(timePoints)
          .enter()
          .append('line')
          .attr('class', d => `time-tick ${d && d.is_major ? 'major' : 'minor'}`)
          .attr('x1', d => d && typeof d.x === 'number' ? d.x : 0)
          .attr('y1', this.mappers.height - (this.mappers.padding ? this.mappers.padding.bottom : 0))
          .attr('x2', d => d && typeof d.x === 'number' ? d.x : 0)
          .attr('y2', this.mappers.height - (this.mappers.padding ? this.mappers.padding.bottom : 0) + (d && d.is_major ? 8 : 4))
          .attr('stroke', '#495057')
          .attr('stroke-width', d => d && d.is_major ? 1 : 0.5);
        
        // Filter for major ticks (with safety check)
        const majorTimePoints = timePoints.filter(d => d && d.is_major);
        
        if (majorTimePoints.length > 0) {
          // Time labels (only show major ticks)
          this.labelLayer.selectAll('.time-label')
            .data(majorTimePoints)
            .enter()
            .append('text')
            .attr('class', 'time-label')
            .attr('x', d => d && typeof d.x === 'number' ? d.x : 0)
            .attr('y', this.mappers.height - (this.mappers.padding ? this.mappers.padding.bottom : 0) + 20)
            .attr('text-anchor', 'middle')
            .text(d => d && d.time ? d.time : '');
        }
      }
    } catch (error) {
      console.error('Error rendering time axis:', error);
    }
  }

  /**
   * Render the trains
   */
  renderTrains() {
    this.trainLayer.selectAll('*').remove();
    
    // If there are no trains, just display a message
    if (!this.trains || this.trains.length === 0) {
      // Add a text message to the train layer
      this.trainLayer.append('text')
        .attr('x', this.mappers.width / 2)
        .attr('y', this.mappers.height / 2)
        .attr('text-anchor', 'middle')
        .attr('fill', '#adb5bd')
        .attr('font-size', '16px')
        .text('No train data available for the selected locations and date');
      
      return;
    }
    
    // Filter trains based on current filter settings
    const filteredTrains = this.trains.filter(train => 
      this.filters.shouldShowTrain(train)
    );
    
    // If no trains match the filter criteria
    if (filteredTrains.length === 0) {
      // Add a text message to the train layer
      this.trainLayer.append('text')
        .attr('x', this.mappers.width / 2)
        .attr('y', this.mappers.height / 2)
        .attr('text-anchor', 'middle')
        .attr('fill', '#adb5bd')
        .attr('font-size', '16px')
        .text('No trains match the current filter criteria');
      
      return;
    }
    
    // Render train paths
    this.trainLayer.selectAll('.train-line')
      .data(filteredTrains)
      .enter()
      .append('path')
      .attr('class', train => {
        const category = train.train_category || '';
        let trainClass = 'train-line';
        
        // Add category class
        if (/^[A-F]|^[K-O]|^W/.test(category)) {
          trainClass += ' passenger';
        } else if (/^[G-J]|^[P-V]/.test(category)) {
          trainClass += ' freight';
        } else if (/^Z/.test(category)) {
          trainClass += ' ecs';
        } else {
          trainClass += ' other';
        }
        
        // Add cancelled class if applicable
        if (train.cancelled) {
          trainClass += ' cancelled';
        }
        
        return trainClass;
      })
      .attr('d', train => this.mappers.createTrainPath(train) || 'M0,0 L0,0') // Provide a default empty path if none
      .attr('data-uid', train => train.uid || '')
      .attr('data-headcode', train => train.train_identity || '');
  }

  /**
   * Render train associations
   */
  renderAssociations() {
    // Clear the association layer
    this.associationLayer.selectAll('*').remove();
    
    // Exit early if we don't have the necessary data
    if (!this.trains || this.trains.length === 0) {
      return;
    }
    
    // Only render associations if checkbox is checked
    if (!document.getElementById('show-associations') || !document.getElementById('show-associations').checked) {
      return;
    }
    
    // Get filtered trains
    const filteredTrains = this.trains.filter(train => 
      this.filters.shouldShowTrain(train)
    );
    
    // Exit if no filtered trains
    if (filteredTrains.length === 0) {
      return;
    }
    
    // Build a lookup map of trains by UID
    const trainMap = {};
    filteredTrains.forEach(train => {
      if (train.uid) {
        trainMap[train.uid] = train;
      }
    });
    
    // Draw association lines between trains
    const associations = [];
    
    // Process each train to find associations
    filteredTrains.forEach(train => {
      if (!train.associations || !Array.isArray(train.associations) || train.associations.length === 0) {
        return;
      }
      
      // For each association
      train.associations.forEach(assoc => {
        if (!assoc || !assoc.assoc_uid || !assoc.location) return;
        
        // Ensure the associated train is also displayed
        const assocTrain = trainMap[assoc.assoc_uid];
        if (!assocTrain) return;
        
        // Find the location where the association occurs
        const mainTrainLoc = train.locations.find(loc => loc.tiploc === assoc.location);
        const assocTrainLoc = assocTrain.locations.find(loc => loc.tiploc === assoc.location);
        
        if (!mainTrainLoc || !assocTrainLoc) return;
        
        // Determine the times to use for the association points
        const mainTime = mainTrainLoc.dep || mainTrainLoc.arr || mainTrainLoc.public_dep || mainTrainLoc.public_arr;
        const assocTime = assocTrainLoc.dep || assocTrainLoc.arr || assocTrainLoc.public_dep || assocTrainLoc.public_arr;
        
        if (!mainTime || !assocTime) return;
        
        const mainX = this.mappers.timeToX(mainTime);
        const mainY = this.mappers.locationToY(assoc.location);
        const assocX = this.mappers.timeToX(assocTime);
        const assocY = this.mappers.locationToY(assoc.location);
        
        // Skip if we couldn't calculate valid coordinates
        if (mainX === null || mainY === null || assocX === null || assocY === null) return;
        
        // Create association object
        associations.push({
          main_uid: train.uid,
          assoc_uid: assocTrain.uid,
          location: assoc.location,
          category: assoc.category,
          main_x: mainX,
          main_y: mainY,
          assoc_x: assocX,
          assoc_y: assocY
        });
      });
    });
    
    // If no valid associations were found, exit
    if (associations.length === 0) {
      return;
    }
    
    // Draw the association lines
    this.associationLayer.selectAll('.association-line')
      .data(associations)
      .enter()
      .append('line')
      .attr('class', 'association-line')
      .attr('x1', d => d.main_x)
      .attr('y1', d => d.main_y)
      .attr('x2', d => d.assoc_x)
      .attr('y2', d => d.assoc_y)
      .attr('data-main-uid', d => d.main_uid || '')
      .attr('data-assoc-uid', d => d.assoc_uid || '')
      .attr('data-category', d => d.category || '');
  }

  /**
   * Set up interaction handlers
   */
  setupInteractions() {
    // Train selection
    this.trainLayer.selectAll('.train-line')
      .on('mouseover', (event, train) => this.handleTrainHover(event, train))
      .on('mouseout', () => this.handleTrainUnhover())
      .on('click', (event, train) => this.handleTrainClick(event, train));
  }

  /**
   * Handle train hover
   * @param {Event} event - Mouse event
   * @param {Object} train - Train data object
   */
  handleTrainHover(event, train) {
    // Highlight the train
    d3.select(event.currentTarget).classed('hover', true);
    
    // Show tooltip
    const mouseX = event.pageX;
    const mouseY = event.pageY;
    
    // Fill tooltip content
    const title = document.querySelector('.tooltip-title');
    const body = document.querySelector('.tooltip-body');
    
    title.textContent = `${train.train_identity || 'Unknown'} (${train.uid})`;
    
    // Build tooltip content
    let content = `
      <table>
        <tr><td>Category:</td><td>${train.train_category || 'Unknown'}</td></tr>
        <tr><td>Status:</td><td>${train.cancelled ? 'Cancelled' : 'Active'}</td></tr>
        <tr><td>Days:</td><td>${train.days_run || 'Unknown'}</td></tr>
      </table>
      <p><strong>Locations:</strong></p>
    `;
    
    // Add location information
    const relevantLocations = train.locations.filter(loc => 
      this.config.locations.includes(loc.tiploc)
    ).sort((a, b) => a.sequence - b.sequence);
    
    if (relevantLocations.length > 0) {
      content += '<table>';
      relevantLocations.forEach(loc => {
        const displayName = this.config.display_names[loc.tiploc] || loc.tiploc;
        const arr = loc.arr || loc.public_arr || '';
        const dep = loc.dep || loc.public_dep || '';
        const platform = loc.platform ? `Plat ${loc.platform}` : '';
        
        content += `<tr><td>${displayName}:</td><td>${arr ? 'Arr ' + arr : ''}${arr && dep ? ' - ' : ''}${dep ? 'Dep ' + dep : ''} ${platform}</td></tr>`;
      });
      content += '</table>';
    } else {
      content += '<p>No relevant locations</p>';
    }
    
    body.innerHTML = content;
    
    // Position and show tooltip
    this.tooltip.style.left = `${mouseX + 10}px`;
    this.tooltip.style.top = `${mouseY + 10}px`;
    this.tooltip.style.display = 'block';
  }

  /**
   * Handle train unhover
   */
  handleTrainUnhover() {
    // Remove highlight
    d3.selectAll('.train-line').classed('hover', false);
    
    // Hide tooltip
    this.tooltip.style.display = 'none';
  }

  /**
   * Handle train click
   * @param {Event} event - Mouse event
   * @param {Object} train - Train data object
   */
  handleTrainClick(event, train) {
    // Toggle selection
    if (this.selectedTrain === train.uid) {
      // Deselect
      this.selectedTrain = null;
      d3.selectAll('.train-line').classed('selected', false);
    } else {
      // Select
      this.selectedTrain = train.uid;
      d3.selectAll('.train-line').classed('selected', false);
      d3.select(event.currentTarget).classed('selected', true);
    }
  }

  /**
   * Reset the zoom level
   */
  resetZoom() {
    this.svg.transition()
      .duration(750)
      .call(this.zoom.transform, d3.zoomIdentity);
  }

  /**
   * Zoom in by a fixed amount
   */
  zoomIn() {
    this.svg.transition()
      .duration(300)
      .call(this.zoom.scaleBy, 1.3);
  }

  /**
   * Zoom out by a fixed amount
   */
  zoomOut() {
    this.svg.transition()
      .duration(300)
      .call(this.zoom.scaleBy, 0.7);
  }

  /**
   * Export the graph as an SVG file
   */
  exportSVG() {
    // Get the SVG element
    const svgEl = this.svg.node();
    
    // Create a copy of the SVG element
    const svgCopy = svgEl.cloneNode(true);
    
    // Set the width and height attributes
    svgCopy.setAttribute('width', this.mappers.width);
    svgCopy.setAttribute('height', this.mappers.height);
    
    // Add CSS styles as a style element
    const styleEl = document.createElement('style');
    // Extract styles from the CSS file
    Array.from(document.styleSheets)
      .filter(sheet => sheet.href && sheet.href.includes('train-graph'))
      .forEach(sheet => {
        try {
          Array.from(sheet.cssRules).forEach(rule => {
            styleEl.textContent += rule.cssText;
          });
        } catch (e) {
          console.warn('Unable to access stylesheet rules', e);
        }
      });
    
    svgCopy.insertBefore(styleEl, svgCopy.firstChild);
    
    // Serialize the SVG to a string
    const serializer = new XMLSerializer();
    let svgString = serializer.serializeToString(svgCopy);
    
    // Add XML declaration
    svgString = '<?xml version="1.0" standalone="no"?>\n' + svgString;
    
    // Create a blob from the SVG string
    const blob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' });
    
    // Create a download link
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `train-graph-${new Date().toISOString().slice(0, 10)}.svg`;
    
    // Trigger download
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }
}