/**
 * Sector info display
 */

/**
 * Update sector banner with info
 * @param {Object} sectorInfo 
 */
export function updateSectorBanner(sectorInfo) {
    const banner = document.getElementById('sector-banner');
    const container = document.getElementById('sector-container');

    if (!sectorInfo || (!sectorInfo.industry && (!sectorInfo.concepts || sectorInfo.concepts.length === 0))) {
        banner.style.display = 'none';
        return;
    }

    container.innerHTML = '';
    banner.style.display = 'flex';

    // Industry
    if (sectorInfo.industry) {
        const tag = createSectorTag(sectorInfo.industry.name, 'industry', sectorInfo.industry.performance);
        container.appendChild(tag);
    }

    // Concepts
    if (sectorInfo.concepts && sectorInfo.concepts.length > 0) {
        sectorInfo.concepts.forEach(c => {
            const tag = createSectorTag(c.name, 'concept', c.performance);
            container.appendChild(tag);
        });
    }
}

/**
 * Create a sector tag element
 * @param {string} name 
 * @param {string} type 
 * @param {Object} perf 
 * @returns {HTMLElement}
 */
function createSectorTag(name, type, perf) {
    const tag = document.createElement('div');
    tag.className = `sector-tag ${type}`;

    // Default show daily change
    let pct = 0;
    let period = 'D'; // Default display period

    if (perf) {
        pct = perf.day || 0;
    }

    // Color class
    const colorClass = pct > 0 ? 'up' : pct < 0 ? 'down' : 'flat';

    tag.innerHTML = `
        <span class="sector-name">${name}</span>
        <span class="sector-val ${colorClass}">${pct > 0 ? '+' : ''}${pct.toFixed(2)}%</span>
    `;

    // Add tooltip/popover logic for detailed stats (Day/Week/Month)
    // For simplicity, we just use title attribute for now, or a custom click handler
    if (perf) {
        const tooltipText = `Day: ${perf.day}%\nWeek: ${perf.week}%\nMonth: ${perf.month}%`;
        tag.title = tooltipText;

        tag.addEventListener('click', (e) => {
            // Simple toggle to scroll through periods? or show alert?
            // For now, let's just show details in a small overlay or console
            // Improve UI: expand tag to show full details?
            // Let's toggle between Day -> Week -> Month -> Day

            e.stopPropagation(); // prevent other clicks

            const valSpan = tag.querySelector('.sector-val');
            const currentText = valSpan.textContent;

            // Cycle: Day -> Week -> Month
            let nextVal = perf.day;
            let nextPeriod = 'D';

            if (valSpan.dataset.period === 'D') {
                nextVal = perf.week;
                nextPeriod = 'W';
            } else if (valSpan.dataset.period === 'W') {
                nextVal = perf.month;
                nextPeriod = 'M';
            } else {
                nextVal = perf.day;
                nextPeriod = 'D';
            }

            const nextColor = nextVal > 0 ? 'up' : nextVal < 0 ? 'down' : 'flat';
            valSpan.className = `sector-val ${nextColor}`;
            valSpan.textContent = `${nextPeriod}: ${nextVal > 0 ? '+' : ''}${nextVal.toFixed(2)}%`;
            valSpan.dataset.period = nextPeriod;
        });

        // Set initial data attr
        tag.querySelector('.sector-val').dataset.period = 'D';
    }

    return tag;
}
