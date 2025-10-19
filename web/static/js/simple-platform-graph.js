/**
 * Simple Platform Docker Graph - A D3.js visualization for train schedules
 */

function createPlatformGraph(containerId, data, options = {}) {
    // Default options
    const config = {
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

    // Get container and clear it
    const container = d3.select(`#${containerId}`);
    container.html("");

    // No data case
    if (!data || !data.platforms || data.platforms.length === 0) {
        container.append("div")
            .attr("class", "alert alert-info")
            .text("No platform data available");
        return;
    }

    // Create SVG
    const svg = container.append("svg")
        .attr("width", "100%")
        .attr("height", config.height)
        .attr("viewBox", `0 0 ${config.width} ${config.height}`)
        .attr("preserveAspectRatio", "xMidYMid meet")
        .style("background-color", config.colors.background);

    // Create chart group with margins
    const chart = svg.append("g")
        .attr("transform", `translate(${config.marginLeft}, ${config.marginTop})`);

    // Create scales
    // Time scale (x-axis)
    const timeScale = d3.scaleLinear()
        .domain([config.startHour * 60, config.endHour * 60]) // minutes from midnight
        .range([0, config.width - config.marginLeft - config.marginRight]);

    // Platform scale (y-axis)
    const platforms = data.platforms.sort((a, b) => {
        const aNum = parseInt(a.name);
        const bNum = parseInt(b.name);
        if (!isNaN(aNum) && !isNaN(bNum)) return aNum - bNum;
        return a.name.localeCompare(b.name);
    });

    const platformScale = d3.scaleBand()
        .domain(platforms.map(p => p.name))
        .range([0, platforms.length * config.rowHeight])
        .padding(0.2);

    // Create axes
    // Time axis (top)
    const timeAxis = d3.axisTop(timeScale)
        .tickValues(d3.range(config.startHour, config.endHour + 1).map(h => h * 60))
        .tickFormat(d => {
            const hours = Math.floor(d / 60);
            return `${hours.toString().padStart(2, '0')}:00`;
        });

    chart.append("g")
        .attr("class", "time-axis")
        .call(timeAxis)
        .call(g => g.select(".domain").attr("stroke", config.colors.grid))
        .call(g => g.selectAll(".tick line").attr("stroke", config.colors.grid))
        .call(g => g.selectAll(".tick text").attr("fill", config.colors.axisText));

    // Platform labels (left)
    chart.selectAll(".platform-label")
        .data(platforms)
        .enter()
        .append("text")
        .attr("class", "platform-label")
        .attr("x", -10)
        .attr("y", d => platformScale(d.name) + platformScale.bandwidth() / 2)
        .attr("text-anchor", "end")
        .attr("dominant-baseline", "middle")
        .attr("fill", config.colors.axisText)
        .text(d => `Platform ${d.name}`);

    // Grid lines
    // Vertical (hour) lines
    chart.selectAll(".grid-line-hour")
        .data(d3.range(config.startHour, config.endHour + 1))
        .enter()
        .append("line")
        .attr("class", "grid-line-hour")
        .attr("x1", d => timeScale(d * 60))
        .attr("x2", d => timeScale(d * 60))
        .attr("y1", 0)
        .attr("y2", platforms.length * config.rowHeight)
        .attr("stroke", config.colors.grid)
        .attr("stroke-width", 1)
        .attr("stroke-dasharray", "3,3");

    // Horizontal (platform) lines
    chart.selectAll(".grid-line-platform")
        .data(platforms)
        .enter()
        .append("line")
        .attr("class", "grid-line-platform")
        .attr("x1", 0)
        .attr("x2", timeScale(config.endHour * 60) - timeScale(config.startHour * 60))
        .attr("y1", d => platformScale(d.name) + platformScale.bandwidth())
        .attr("y2", d => platformScale(d.name) + platformScale.bandwidth())
        .attr("stroke", config.colors.grid)
        .attr("stroke-width", 0.5);

    // Create tooltip
    const tooltip = container.append("div")
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

    // Helper: Convert CIF time format (HHMM) to minutes since midnight
    function timeToMinutes(cifTime) {
        if (!cifTime || cifTime.length !== 4) return null;
        const hours = parseInt(cifTime.substring(0, 2));
        const minutes = parseInt(cifTime.substring(2));
        return (hours * 60) + minutes;
    }

    // Helper: Format time from CIF format (HHMM) to display format (HH:MM)
    function formatTime(cifTime) {
        if (!cifTime || cifTime.length !== 4) return cifTime;
        return cifTime.substring(0, 2) + ':' + cifTime.substring(2);
    }

    // Draw trains for each platform
    platforms.forEach(platform => {
        if (!platform.events || platform.events.length === 0) return;
        
        const platformGroup = chart.append("g")
            .attr("class", `platform-${platform.name}`);
        
        platform.events.forEach(event => {
            // Process arrival and departure times
            let arrivalMinutes = null;
            let departureMinutes = null;
            
            if (event.arrival_time) {
                arrivalMinutes = timeToMinutes(event.arrival_time);
            }
            
            if (event.departure_time) {
                departureMinutes = timeToMinutes(event.departure_time);
            }
            
            // Domain boundaries
            const domainStart = config.startHour * 60;
            const domainEnd = config.endHour * 60;
            
            // Draw different types of events based on arrival/departure times
            // Both arrival and departure times (passing or stopping train)
            if (arrivalMinutes !== null && departureMinutes !== null) {
                // Skip if outside visible range
                if (departureMinutes < domainStart || arrivalMinutes > domainEnd) {
                    return;
                }
                
                // Clamp to visible range
                const visibleArrival = Math.max(arrivalMinutes, domainStart);
                const visibleDeparture = Math.min(departureMinutes, domainEnd);
                
                // Determine color
                let color = config.colors.train.passenger;
                if (event.is_terminating) {
                    color = config.colors.train.terminating;
                } else if (event.is_originating) {
                    color = config.colors.train.originating;
                }
                
                // Draw train bar
                const train = platformGroup.append("rect")
                    .attr("class", "train-event")
                    .attr("x", timeScale(visibleArrival))
                    .attr("y", platformScale(platform.name))
                    .attr("width", timeScale(visibleDeparture) - timeScale(visibleArrival))
                    .attr("height", platformScale.bandwidth())
                    .attr("rx", 3)
                    .attr("ry", 3)
                    .attr("fill", color)
                    .attr("stroke", "rgba(255, 255, 255, 0.3)")
                    .attr("stroke-width", 1);
                
                // Add event label if there's enough space
                if (timeScale(visibleDeparture) - timeScale(visibleArrival) > 50) {
                    platformGroup.append("text")
                        .attr("class", "train-label")
                        .attr("x", timeScale(visibleArrival) + 5)
                        .attr("y", platformScale(platform.name) + platformScale.bandwidth() / 2)
                        .attr("dominant-baseline", "middle")
                        .attr("fill", "white")
                        .attr("font-size", "10px")
                        .text(event.headcode || event.uid.substring(0, 5));
                }
                
                // Add tooltip
                train.on("mouseover", function(e) {
                    tooltip.transition()
                        .duration(200)
                        .style("opacity", 0.9);
                    
                    let html = `<div style="font-weight: bold; border-bottom: 1px solid #3a3f47; margin-bottom: 5px;">
                        ${event.headcode || 'N/A'} (${event.uid})
                    </div>`;
                    
                    html += `<div>Arrival: ${formatTime(event.arrival_time)}</div>`;
                    html += `<div>Departure: ${formatTime(event.departure_time)}</div>`;
                    html += `<div>Category: ${event.category || 'N/A'}</div>`;
                    
                    tooltip.html(html)
                        .style("left", (e.pageX + 10) + "px")
                        .style("top", (e.pageY - 28) + "px");
                })
                .on("mouseout", function() {
                    tooltip.transition()
                        .duration(500)
                        .style("opacity", 0);
                });
            }
            // Only arrival time (terminating train)
            else if (arrivalMinutes !== null) {
                if (arrivalMinutes < domainStart || arrivalMinutes > domainEnd) return;
                
                // Draw marker
                const marker = platformGroup.append("rect")
                    .attr("class", "arrival-marker")
                    .attr("x", timeScale(arrivalMinutes) - 2)
                    .attr("y", platformScale(platform.name))
                    .attr("width", 4)
                    .attr("height", platformScale.bandwidth())
                    .attr("fill", config.colors.train.terminating);
                
                // Add tooltip
                marker.on("mouseover", function(e) {
                    tooltip.transition()
                        .duration(200)
                        .style("opacity", 0.9);
                    
                    let html = `<div style="font-weight: bold; border-bottom: 1px solid #3a3f47; margin-bottom: 5px;">
                        ${event.headcode || 'N/A'} (${event.uid})
                    </div>`;
                    
                    html += `<div>Arrival: ${formatTime(event.arrival_time)}</div>`;
                    html += `<div>Terminating: Yes</div>`;
                    
                    tooltip.html(html)
                        .style("left", (e.pageX + 10) + "px")
                        .style("top", (e.pageY - 28) + "px");
                })
                .on("mouseout", function() {
                    tooltip.transition()
                        .duration(500)
                        .style("opacity", 0);
                });
            }
            // Only departure time (originating train)
            else if (departureMinutes !== null) {
                if (departureMinutes < domainStart || departureMinutes > domainEnd) return;
                
                // Draw marker
                const marker = platformGroup.append("rect")
                    .attr("class", "departure-marker")
                    .attr("x", timeScale(departureMinutes) - 2)
                    .attr("y", platformScale(platform.name))
                    .attr("width", 4)
                    .attr("height", platformScale.bandwidth())
                    .attr("fill", config.colors.train.originating);
                
                // Add tooltip
                marker.on("mouseover", function(e) {
                    tooltip.transition()
                        .duration(200)
                        .style("opacity", 0.9);
                    
                    let html = `<div style="font-weight: bold; border-bottom: 1px solid #3a3f47; margin-bottom: 5px;">
                        ${event.headcode || 'N/A'} (${event.uid})
                    </div>`;
                    
                    html += `<div>Departure: ${formatTime(event.departure_time)}</div>`;
                    html += `<div>Originating: Yes</div>`;
                    
                    tooltip.html(html)
                        .style("left", (e.pageX + 10) + "px")
                        .style("top", (e.pageY - 28) + "px");
                })
                .on("mouseout", function() {
                    tooltip.transition()
                        .duration(500)
                        .style("opacity", 0);
                });
            }
        });
    });

    // Add current time indicator if showing today's data
    const today = new Date().toISOString().split('T')[0];
    if (data.date === today) {
        const now = new Date();
        const hours = now.getHours();
        const minutes = now.getMinutes();
        const totalMinutes = (hours * 60) + minutes;
        
        if (totalMinutes >= config.startHour * 60 && totalMinutes <= config.endHour * 60) {
            chart.append("line")
                .attr("class", "current-time-line")
                .attr("x1", timeScale(totalMinutes))
                .attr("x2", timeScale(totalMinutes))
                .attr("y1", -10)
                .attr("y2", platforms.length * config.rowHeight)
                .attr("stroke", "#e74c3c")
                .attr("stroke-width", 2);
                
            chart.append("text")
                .attr("class", "current-time-label")
                .attr("x", timeScale(totalMinutes))
                .attr("y", -25)
                .attr("text-anchor", "middle")
                .attr("fill", "#e74c3c")
                .attr("font-size", "10px")
                .text(`${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`);
        }
    }

    // Add zoom behavior
    const zoom = d3.zoom()
        .scaleExtent([0.5, 4])
        .on("zoom", function(event) {
            chart.attr("transform", `translate(${event.transform.x + config.marginLeft}, ${event.transform.y + config.marginTop}) scale(${event.transform.k})`);
            
            // Update axis with zoom
            chart.select(".time-axis").call(timeAxis.scale(event.transform.rescaleX(timeScale)))
                .call(g => g.select(".domain").attr("stroke", config.colors.grid))
                .call(g => g.selectAll(".tick line").attr("stroke", config.colors.grid))
                .call(g => g.selectAll(".tick text").attr("fill", config.colors.axisText));
        });
        
    svg.call(zoom);
    
    // Return functions to control the graph
    return {
        zoomIn: function() {
            const currentTransform = d3.zoomTransform(svg.node());
            const newTransform = d3.zoomIdentity.translate(currentTransform.x, currentTransform.y).scale(currentTransform.k * 1.2);
            svg.transition().duration(300).call(zoom.transform, newTransform);
        },
        zoomOut: function() {
            const currentTransform = d3.zoomTransform(svg.node());
            const newTransform = d3.zoomIdentity.translate(currentTransform.x, currentTransform.y).scale(currentTransform.k * 0.8);
            svg.transition().duration(300).call(zoom.transform, newTransform);
        },
        resetZoom: function() {
            svg.transition().duration(300).call(zoom.transform, d3.zoomIdentity);
        }
    };
}