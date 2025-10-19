/**
 * Platform Docker Visualization with D3.js
 * This module provides a graphical platform docker visualization using D3.js
 * to display train schedules on platforms with time on the horizontal axis.
 */

class PlatformDockerGraph {
    constructor(containerId, options = {}) {
        this.containerId = containerId;
        this.container = d3.select(`#${containerId}`);
        
        // Default configuration options
        this.config = {
            width: options.width || 1200,
            height: options.height || 600,
            marginLeft: options.marginLeft || 80,
            marginRight: options.marginRight || 20,
            marginTop: options.marginTop || 50,
            marginBottom: options.marginBottom || 20,
            startHour: options.startHour || 6,
            endHour: options.endHour || 22,
            rowHeight: options.rowHeight || 60,
            platformGap: options.platformGap || 10,
            timeFormat: options.timeFormat || "%H:%M",
            colors: options.colors || {
                background: "#1e2124",
                grid: "#3a3f47",
                axisText: "#ffffff",
                train: {
                    passenger: "#3498db",
                    freight: "#f39c12",
                    terminating: "#e74c3c",
                    originating: "#2ecc71",
                    empty: "#9b59b6"
                }
            }
        };

        // Initialize data structures
        this.data = null;
        this.timeScale = null;
        this.platformScale = null;
        this.svg = null;
        this.tooltip = null;
        
        // Initialize the visualization
        this._initialize();
    }
    
    /**
     * Initialize the SVG container and scales
     */
    _initialize() {
        // Clear any existing content
        this.container.html("");
        
        // Create SVG container
        this.svg = this.container.append("svg")
            .attr("width", "100%")
            .attr("height", this.config.height)
            .attr("viewBox", `0 0 ${this.config.width} ${this.config.height}`)
            .attr("preserveAspectRatio", "xMidYMid meet")
            .style("background-color", this.config.colors.background);
            
        // Create tooltip
        this.tooltip = this.container.append("div")
            .attr("class", "train-tooltip")
            .style("opacity", 0)
            .style("position", "absolute")
            .style("pointer-events", "none")
            .style("background-color", "#2a2e33")
            .style("border", "1px solid #3a3f47")
            .style("border-radius", "4px")
            .style("padding", "8px")
            .style("color", "white")
            .style("font-size", "12px")
            .style("z-index", 100);
            
        // Add zoom behavior
        const zoom = d3.zoom()
            .scaleExtent([0.5, 4])
            .on("zoom", (event) => {
                this.svg.select(".chart-group").attr("transform", event.transform);
                this._updateAxisOnZoom(event.transform);
            });
            
        this.svg.call(zoom);
        
        // Create a main group for the chart
        this.chartGroup = this.svg.append("g")
            .attr("class", "chart-group")
            .attr("transform", `translate(${this.config.marginLeft}, ${this.config.marginTop})`);
            
        // Initialize time axis
        const startMinutes = this.config.startHour * 60;
        const endMinutes = this.config.endHour * 60;
        
        this.timeScale = d3.scaleLinear()
            .domain([startMinutes, endMinutes])
            .range([0, this.config.width - this.config.marginLeft - this.config.marginRight]);
            
        // Add time axis (top)
        this.timeAxisGroup = this.chartGroup.append("g")
            .attr("class", "time-axis")
            .attr("transform", `translate(0, -10)`);
            
        // Add grid lines group
        this.gridGroup = this.chartGroup.append("g")
            .attr("class", "grid-lines");
            
        // Add platforms group
        this.platformsGroup = this.chartGroup.append("g")
            .attr("class", "platforms");
    }
    
    /**
     * Render the platform docker visualization with the provided data
     * @param {Object} data - The platform docker data
     */
    render(data) {
        if (!data || !data.platforms || data.platforms.length === 0) {
            this._showNoDataMessage();
            return;
        }
        
        this.data = data;
        this._clearChart();
        this._setupScales();
        this._drawTimeAxis();
        this._drawGridLines();
        this._drawPlatformLabels();
        this._drawTrains();
        
        // Add current time indicator if showing today's data
        if (this._isToday(data.date)) {
            this._addCurrentTimeIndicator();
        }
    }
    
    /**
     * Show a message when no data is available
     */
    _showNoDataMessage() {
        this.svg.append("text")
            .attr("x", this.config.width / 2)
            .attr("y", this.config.height / 2)
            .attr("text-anchor", "middle")
            .attr("fill", "white")
            .text("No platform data available");
    }
    
    /**
     * Clear chart elements before redrawing
     */
    _clearChart() {
        this.timeAxisGroup.html("");
        this.gridGroup.html("");
        this.platformsGroup.html("");
    }
    
    /**
     * Setup scales based on data
     */
    _setupScales() {
        // Sort platforms numerically if possible
        const platforms = this.data.platforms.sort((a, b) => {
            const aNum = parseInt(a.name);
            const bNum = parseInt(b.name);
            if (!isNaN(aNum) && !isNaN(bNum)) return aNum - bNum;
            return a.name.localeCompare(b.name);
        });
        
        // Setup platform scale
        this.platformScale = d3.scaleBand()
            .domain(platforms.map(d => d.name))
            .range([0, platforms.length * this.config.rowHeight])
            .padding(0.1);
    }
    
    /**
     * Draw time axis with hour markers
     */
    _drawTimeAxis() {
        // Create time axis
        const timeAxis = d3.axisTop(this.timeScale)
            .tickValues(this._generateHourTicks())
            .tickFormat(d => {
                const hours = Math.floor(d / 60);
                return `${hours.toString().padStart(2, '0')}:00`;
            });
            
        // Add time axis to chart
        this.timeAxisGroup.call(timeAxis)
            .call(g => g.select(".domain").attr("stroke", this.config.colors.grid))
            .call(g => g.selectAll(".tick line").attr("stroke", this.config.colors.grid))
            .call(g => g.selectAll(".tick text").attr("fill", this.config.colors.axisText));
            
        // Add minor tick marks for 30-minute intervals
        const minorTicks = this._generateHalfHourTicks();
        
        this.timeAxisGroup.selectAll(".minor-tick")
            .data(minorTicks)
            .enter()
            .append("line")
            .attr("class", "minor-tick")
            .attr("x1", d => this.timeScale(d))
            .attr("x2", d => this.timeScale(d))
            .attr("y1", 0)
            .attr("y2", 6)
            .attr("stroke", this.config.colors.grid);
            
        // Add minor tick labels
        this.timeAxisGroup.selectAll(".minor-tick-label")
            .data(minorTicks)
            .enter()
            .append("text")
            .attr("class", "minor-tick-label")
            .attr("x", d => this.timeScale(d))
            .attr("y", -15)
            .attr("text-anchor", "middle")
            .attr("fill", this.config.colors.axisText)
            .attr("font-size", "10px")
            .text(d => {
                const hours = Math.floor(d / 60);
                const minutes = d % 60;
                return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`;
            });
    }
    
    /**
     * Draw vertical grid lines
     */
    _drawGridLines() {
        // Draw hour grid lines
        const hourTicks = this._generateHourTicks();
        
        this.gridGroup.selectAll(".grid-line-hour")
            .data(hourTicks)
            .enter()
            .append("line")
            .attr("class", "grid-line-hour")
            .attr("x1", d => this.timeScale(d))
            .attr("x2", d => this.timeScale(d))
            .attr("y1", 0)
            .attr("y2", this.data.platforms.length * this.config.rowHeight)
            .attr("stroke", this.config.colors.grid)
            .attr("stroke-width", 1)
            .attr("stroke-dasharray", "3,3");
            
        // Draw half-hour grid lines
        const halfHourTicks = this._generateHalfHourTicks();
        
        this.gridGroup.selectAll(".grid-line-half-hour")
            .data(halfHourTicks)
            .enter()
            .append("line")
            .attr("class", "grid-line-half-hour")
            .attr("x1", d => this.timeScale(d))
            .attr("x2", d => this.timeScale(d))
            .attr("y1", 0)
            .attr("y2", this.data.platforms.length * this.config.rowHeight)
            .attr("stroke", this.config.colors.grid)
            .attr("stroke-width", 0.5)
            .attr("stroke-dasharray", "2,2");
    }
    
    /**
     * Draw platform labels and horizontal separators
     */
    _drawPlatformLabels() {
        // Draw platform labels on the left
        this.platformsGroup.selectAll(".platform-label")
            .data(this.data.platforms)
            .enter()
            .append("text")
            .attr("class", "platform-label")
            .attr("x", -10)
            .attr("y", d => this.platformScale(d.name) + this.platformScale.bandwidth() / 2)
            .attr("text-anchor", "end")
            .attr("dominant-baseline", "middle")
            .attr("fill", this.config.colors.axisText)
            .text(d => `Platform ${d.name}`);
            
        // Draw platform separators
        this.platformsGroup.selectAll(".platform-separator")
            .data(this.data.platforms)
            .enter()
            .append("line")
            .attr("class", "platform-separator")
            .attr("x1", 0)
            .attr("x2", this.config.width - this.config.marginLeft - this.config.marginRight)
            .attr("y1", d => this.platformScale(d.name) + this.platformScale.bandwidth())
            .attr("y2", d => this.platformScale(d.name) + this.platformScale.bandwidth())
            .attr("stroke", this.config.colors.grid)
            .attr("stroke-width", 0.5);
    }
    
    /**
     * Draw train events on the chart
     */
    _drawTrains() {
        // For each platform, draw its train events
        this.data.platforms.forEach(platform => {
            if (!platform.events || platform.events.length === 0) return;
            
            // Create a group for this platform's events
            const platformGroup = this.platformsGroup.append("g")
                .attr("class", `platform-${platform.name}`);
                
            // For each event, draw a train
            platform.events.forEach(event => {
                this._drawTrainEvent(event, platform.name, platformGroup);
            });
        });
    }
    
    /**
     * Draw a single train event
     */
    _drawTrainEvent(event, platformName, parentGroup) {
        // Convert times to minutes since midnight
        let arrivalMinutes = null;
        let departureMinutes = null;
        
        if (event.arrival_time) {
            arrivalMinutes = this._timeToMinutes(event.arrival_time);
        }
        
        if (event.departure_time) {
            departureMinutes = this._timeToMinutes(event.departure_time);
        }
        
        // Skip events outside the visible range
        const domainStart = this.config.startHour * 60;
        const domainEnd = this.config.endHour * 60;
        
        // If both times exist, draw a bar representing the dwell time
        if (arrivalMinutes !== null && departureMinutes !== null) {
            // Check if event is visible
            if (departureMinutes < domainStart || arrivalMinutes > domainEnd) {
                return;
            }
            
            // Clamp times to visible range
            const visibleArrival = Math.max(arrivalMinutes, domainStart);
            const visibleDeparture = Math.min(departureMinutes, domainEnd);
            
            // Determine train color
            let trainColor = this.config.colors.train.passenger;
            if (event.is_terminating) {
                trainColor = this.config.colors.train.terminating;
            } else if (event.is_originating) {
                trainColor = this.config.colors.train.originating;
            } else if (event.train_status === 'F') {
                trainColor = this.config.colors.train.freight;
            } else if (event.train_status === 'T') {
                trainColor = this.config.colors.train.empty;
            }
            
            // Draw train bar
            const train = parentGroup.append("rect")
                .attr("class", "train-event")
                .attr("x", this.timeScale(visibleArrival))
                .attr("y", this.platformScale(platformName))
                .attr("width", this.timeScale(visibleDeparture) - this.timeScale(visibleArrival))
                .attr("height", this.platformScale.bandwidth())
                .attr("rx", 3)
                .attr("ry", 3)
                .attr("fill", trainColor)
                .attr("stroke", "rgba(255, 255, 255, 0.3)")
                .attr("stroke-width", 1);
                
            // Add a label if there's enough space
            const width = this.timeScale(visibleDeparture) - this.timeScale(visibleArrival);
            if (width > 50) {
                parentGroup.append("text")
                    .attr("class", "train-label")
                    .attr("x", this.timeScale(visibleArrival) + 5)
                    .attr("y", this.platformScale(platformName) + this.platformScale.bandwidth() / 2)
                    .attr("dominant-baseline", "middle")
                    .attr("fill", "white")
                    .attr("font-size", "10px")
                    .text(event.headcode || event.uid.substring(0, 5));
            }
            
            // Add tooltip behavior
            this._addTooltip(train, event);
        }
        // If only arrival time exists, draw a marker for terminating train
        else if (arrivalMinutes !== null) {
            // Check if event is visible
            if (arrivalMinutes < domainStart || arrivalMinutes > domainEnd) {
                return;
            }
            
            // Draw arrival marker
            const marker = parentGroup.append("rect")
                .attr("class", "arrival-marker")
                .attr("x", this.timeScale(arrivalMinutes) - 2)
                .attr("y", this.platformScale(platformName))
                .attr("width", 4)
                .attr("height", this.platformScale.bandwidth())
                .attr("fill", this.config.colors.train.terminating);
                
            // Add tooltip behavior
            this._addTooltip(marker, event);
        }
        // If only departure time exists, draw a marker for originating train
        else if (departureMinutes !== null) {
            // Check if event is visible
            if (departureMinutes < domainStart || departureMinutes > domainEnd) {
                return;
            }
            
            // Draw departure marker
            const marker = parentGroup.append("rect")
                .attr("class", "departure-marker")
                .attr("x", this.timeScale(departureMinutes) - 2)
                .attr("y", this.platformScale(platformName))
                .attr("width", 4)
                .attr("height", this.platformScale.bandwidth())
                .attr("fill", this.config.colors.train.originating);
                
            // Add tooltip behavior
            this._addTooltip(marker, event);
        }
    }
    
    /**
     * Add tooltip to a train element
     */
    _addTooltip(element, event) {
        element
            .on("mouseover", (e, d) => {
                this.tooltip.transition()
                    .duration(200)
                    .style("opacity", 0.9);
                    
                // Format tooltip content
                let html = `<div style="border-bottom: 1px solid #3a3f47; margin-bottom: 5px; font-weight: bold;">
                    ${event.headcode || 'N/A'} (${event.uid})
                </div>`;
                
                html += `<div style="display: grid; grid-template-columns: auto 1fr; gap: 5px;">`;
                
                // Add arrival time
                html += `<div style="color: #aaa;">Arrival:</div>
                    <div>${event.arrival_time ? this._formatTime(event.arrival_time) : '-'}</div>`;
                
                // Add departure time
                html += `<div style="color: #aaa;">Departure:</div>
                    <div>${event.departure_time ? this._formatTime(event.departure_time) : '-'}</div>`;
                
                // Add category
                html += `<div style="color: #aaa;">Category:</div>
                    <div>${event.category || 'N/A'}</div>`;
                
                // Add train status
                html += `<div style="color: #aaa;">Status:</div>
                    <div>${this._getTrainStatusName(event.train_status)}</div>`;
                
                // Add terminating/originating info
                if (event.is_terminating) {
                    html += `<div style="color: #aaa;">Terminating:</div><div>Yes</div>`;
                }
                if (event.is_originating) {
                    html += `<div style="color: #aaa;">Originating:</div><div>Yes</div>`;
                }
                
                html += `</div>`;
                
                this.tooltip.html(html)
                    .style("left", (e.pageX + 10) + "px")
                    .style("top", (e.pageY - 28) + "px");
            })
            .on("mouseout", () => {
                this.tooltip.transition()
                    .duration(500)
                    .style("opacity", 0);
            })
            .on("mousemove", (e) => {
                this.tooltip
                    .style("left", (e.pageX + 10) + "px")
                    .style("top", (e.pageY - 28) + "px");
            });
    }
    
    /**
     * Add current time indicator to chart
     */
    _addCurrentTimeIndicator() {
        const now = new Date();
        const hours = now.getHours();
        const minutes = now.getMinutes();
        const totalMinutes = (hours * 60) + minutes;
        
        // Only add if current time is in the visible range
        if (totalMinutes >= this.config.startHour * 60 && totalMinutes <= this.config.endHour * 60) {
            // Add current time vertical line
            this.chartGroup.append("line")
                .attr("class", "current-time-line")
                .attr("x1", this.timeScale(totalMinutes))
                .attr("x2", this.timeScale(totalMinutes))
                .attr("y1", -10)
                .attr("y2", this.data.platforms.length * this.config.rowHeight)
                .attr("stroke", "#e74c3c")
                .attr("stroke-width", 2);
                
            // Add current time label
            this.chartGroup.append("text")
                .attr("class", "current-time-label")
                .attr("x", this.timeScale(totalMinutes))
                .attr("y", -25)
                .attr("text-anchor", "middle")
                .attr("fill", "#e74c3c")
                .attr("font-size", "10px")
                .text(`${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`);
        }
    }
    
    /**
     * Update the axis display during zoom operations
     */
    _updateAxisOnZoom(transform) {
        // Create a rescaled time axis
        const rescaledX = transform.rescaleX(this.timeScale);
        const timeAxis = d3.axisTop(rescaledX)
            .tickValues(this._generateHourTicks())
            .tickFormat(d => {
                const hours = Math.floor(d / 60);
                return `${hours.toString().padStart(2, '0')}:00`;
            });
            
        // Update time axis
        this.timeAxisGroup.call(timeAxis)
            .call(g => g.select(".domain").attr("stroke", this.config.colors.grid))
            .call(g => g.selectAll(".tick line").attr("stroke", this.config.colors.grid))
            .call(g => g.selectAll(".tick text").attr("fill", this.config.colors.axisText));
    }
    
    /**
     * Generate tick marks for hours
     */
    _generateHourTicks() {
        const ticks = [];
        for (let hour = this.config.startHour; hour <= this.config.endHour; hour++) {
            ticks.push(hour * 60);
        }
        return ticks;
    }
    
    /**
     * Generate tick marks for half hours
     */
    _generateHalfHourTicks() {
        const ticks = [];
        for (let hour = this.config.startHour; hour < this.config.endHour; hour++) {
            ticks.push(hour * 60 + 30);
        }
        return ticks;
    }
    
    /**
     * Convert CIF time format (HHMM) to minutes since midnight
     */
    _timeToMinutes(cifTime) {
        if (!cifTime || cifTime.length !== 4) return null;
        const hours = parseInt(cifTime.substring(0, 2));
        const minutes = parseInt(cifTime.substring(2));
        return (hours * 60) + minutes;
    }
    
    /**
     * Format time from CIF format (HHMM) to display format (HH:MM)
     */
    _formatTime(cifTime) {
        if (!cifTime || cifTime.length !== 4) return cifTime;
        return cifTime.substring(0, 2) + ':' + cifTime.substring(2);
    }
    
    /**
     * Get friendly name for train status code
     */
    _getTrainStatusName(status) {
        const statusMap = {
            'P': 'Passenger',
            'F': 'Freight',
            'T': 'Trip',
            'B': 'Bus',
            'S': 'Ship'
        };
        return statusMap[status] || status;
    }
    
    /**
     * Check if a date string is today
     */
    _isToday(dateStr) {
        const today = new Date().toISOString().split('T')[0];
        return dateStr === today;
    }
    
    /**
     * Resize the chart - call when container size changes
     */
    resize() {
        // Update dimensions
        const containerWidth = this.container.node().getBoundingClientRect().width;
        this.config.width = containerWidth;
        
        // Recreate SVG with new dimensions
        this.svg.attr("viewBox", `0 0 ${this.config.width} ${this.config.height}`);
        
        // Update time scale range
        this.timeScale.range([0, this.config.width - this.config.marginLeft - this.config.marginRight]);
        
        // Re-render with updated dimensions
        if (this.data) {
            this.render(this.data);
        }
    }
    
    /**
     * Zoom in on the chart
     */
    zoomIn() {
        const transform = d3.zoomIdentity.scale(1.2).translate(0, 0);
        this.svg.transition().duration(300).call(
            d3.zoom().transform, transform
        );
    }
    
    /**
     * Zoom out on the chart
     */
    zoomOut() {
        const transform = d3.zoomIdentity.scale(0.8).translate(0, 0);
        this.svg.transition().duration(300).call(
            d3.zoom().transform, transform
        );
    }
    
    /**
     * Reset zoom to default
     */
    resetZoom() {
        const transform = d3.zoomIdentity;
        this.svg.transition().duration(300).call(
            d3.zoom().transform, transform
        );
    }
}