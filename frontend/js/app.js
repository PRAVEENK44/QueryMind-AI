/**
 * QueryMind AI - Nexus Frontend (Stable Build v10)
 * Synchronized with Nexus API Structure
 */

const API_ROOT = `${window.location.origin}/api`;

// ===================== CUSTOM DB SESSION STATE =====================
let _customDbSession = null; // { session_id, filename, tables }

function initCustomDbSession() {
    const saved = localStorage.getItem('querymind_custom_db');
    if (saved) {
        try { _customDbSession = JSON.parse(saved); } catch(e) {}
    }
    if (_customDbSession) {
        showCustomDbBadge(_customDbSession.filename);
    }
}

function setCustomDbSession(sessionData) {
    _customDbSession = sessionData;
    localStorage.setItem('querymind_custom_db', JSON.stringify(sessionData));
    showCustomDbBadge(sessionData.filename);
}

function clearCustomDbSession() {
    if (_customDbSession) {
        // Best-effort cleanup on server
        fetch(`${API_ROOT}/upload-db/${_customDbSession.session_id}`, { method: 'DELETE' }).catch(() => {});
    }
    _customDbSession = null;
    localStorage.removeItem('querymind_custom_db');
    const badge = document.getElementById('customDbBadge');
    if (badge) badge.classList.remove('active');
    const statusText = document.getElementById('statusText');
    if (statusText) statusText.textContent = 'Link Active';
}

function showCustomDbBadge(filename) {
    const badge = document.getElementById('customDbBadge');
    const nameEl = document.getElementById('customDbName');
    const statusText = document.getElementById('statusText');
    if (badge) badge.classList.add('active');
    if (nameEl) nameEl.textContent = filename;
    if (statusText) statusText.textContent = 'Custom DB';
}

document.addEventListener('DOMContentLoaded', () => {
    initInterface();
    loadSampleQueries();
    initCustomDbSession();
    initUploadModal();
});

// Load dynamic sample questions
async function loadSampleQueries() {
    try {
        const res = await fetch(`${API_ROOT}/sample-queries`);
        const samples = await res.json();
        const container = document.getElementById('sampleQueries');
        if (container) {
            container.innerHTML = '';
            samples.forEach(s => {
                const pill = document.createElement('div');
                pill.className = 'query-pill';
                pill.style.cssText = 'padding: 0.5rem 1rem; background: var(--bg-ice); border: 1px solid var(--border); border-radius: 99px; cursor: pointer; font-size: 0.9rem; transition: all 0.2s;';
                pill.innerText = s.query;
                pill.onclick = () => {
                    document.getElementById('queryInput').value = s.query;
                    runSearch();
                };
                // Add hover effect
                pill.onmouseenter = () => pill.style.borderColor = 'var(--primary)';
                pill.onmouseleave = () => pill.style.borderColor = 'var(--border)';
                container.appendChild(pill);
            });
        }
    } catch (err) {
        console.warn('Could not load samples', err);
    }
}

// User Interaction Controller
function initInterface() {
    const queryInput = document.getElementById('queryInput');
    const submitBtn = document.getElementById('submitQuery');

    if (submitBtn) {
        submitBtn.onclick = () => runSearch();
    }

    if (queryInput) {
        queryInput.onkeypress = (e) => {
            if (e.key === 'Enter') runSearch();
        };
    }
    
    // Knowledge Drawer ( Retractable )
    const drawer = document.getElementById('knowledgeDrawer');
    const openBtn = document.getElementById('openKnowledge');
    const closeBtn = document.getElementById('closeKnowledge');

    if (openBtn) openBtn.onclick = () => {
        drawer.classList.add('open');
        loadKnowledge();
    };
    if (closeBtn) closeBtn.onclick = () => drawer.classList.remove('open');
    
    const loadDashboardBtn = document.getElementById('loadDashboardBtn');
    if (loadDashboardBtn) {
        loadDashboardBtn.onclick = () => {
            loadDashboardBtn.style.display = 'none'; // Remove button
            refreshPulse();
        };
    }

    // Atlas Toggle
    const atlasOverlay = document.getElementById('atlasOverlay');
    const openAtlasBtn = document.getElementById('openAtlas');
    const closeAtlasBtn = document.getElementById('closeAtlas');

    if (openAtlasBtn) {
        openAtlasBtn.onclick = () => {
            atlasOverlay.classList.add('active');
            setTimeout(() => initAtlas(), 50);
        };
    }
    if (closeAtlasBtn) closeAtlasBtn.onclick = () => atlasOverlay.classList.remove('active');

    // Upload DB Button
    const uploadDbBtn = document.getElementById('uploadDbBtn');
    if (uploadDbBtn) uploadDbBtn.onclick = () => document.getElementById('uploadModal').classList.add('active');

    // Remove custom DB badge
    const removeCustomDb = document.getElementById('removeCustomDb');
    if (removeCustomDb) removeCustomDb.onclick = (e) => {
        e.stopPropagation();
        clearCustomDbSession();
    };
}

// On-Demand Dashboard Logic
async function refreshPulse() {
    const card = document.getElementById('dashboardCard');
    const kpisWrap = document.getElementById('dashboardKpis');
    const vizWrap = document.getElementById('dashboardViz');
    
    if(!card) return;
    card.style.display = 'block'; // Unhide skeletons!

    try {
        const response = await fetch(`${API_ROOT}/dashboard`);
        if(!response.ok) throw new Error('API failed.');
        
        const data = await response.json();
        
        // Populate KPIs
        kpisWrap.innerHTML = '';
        data.kpis.forEach(k => {
            let val = k.value;
            if(k.format === 'currency') val = '₹' + val.toLocaleString(undefined, {minimumFractionDigits: 2});
            else val = val.toLocaleString();
            
            kpisWrap.innerHTML += `
                <div class="kpi-box">
                    <div class="kpi-label">${k.label}</div>
                    <div class="kpi-val">${val}</div>
                </div>
            `;
        });
        
        // Populate Viz
        vizWrap.style.display = 'block';
        vizWrap.innerHTML = ''; // reset previous charts
        
        if(data.dashboard_charts && data.dashboard_charts.length > 0) {
            data.dashboard_charts.forEach((chartPkg, idx) => {
                const chartId = `viz-board-${idx}`;
                const chartDiv = document.createElement('div');
                chartDiv.id = chartId;
                chartDiv.style.height = '350px';
                chartDiv.style.marginBottom = '2rem';
                vizWrap.appendChild(chartDiv);
                
                drawNexusChart(chartId, {data: chartPkg.data, layout: chartPkg.layout});
            });
        } else {
             vizWrap.style.display = 'none';
        }
    } catch(e) {
        console.error('Pulse Error:', e);
        kpisWrap.innerHTML = '<div class="insight-content" style="color: var(--error); padding: 1rem;">Agentic Dashboard Generation Failed. Please retry.</div>';
    }
}

// Core Search Execution
async function runSearch() {
    const input = document.getElementById('queryInput');
    const btn = document.getElementById('submitQuery');
    const stream = document.getElementById('resultsStream');
    
    const text = input.value.trim();
    if (!text) return;
    
    // UI Feedback
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i><span>Analyzing...</span>';

    try {
        const response = await fetch(`${API_ROOT}/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                query: text, 
                session_id: Date.now().toString(),
                use_llm: true,
                custom_db_id: _customDbSession ? _customDbSession.session_id : null
            })
        });

        if (!response.ok) throw new Error(`Nexus Gateway Error: ${response.status}`);

        const result = await response.json();
        if (result.success) {
            renderNexusCard(text, result);
        } else {
            renderNexusError(text, result.error || 'The system could not parse this request.');
        }
        
        input.value = '';
    } catch (err) {
        console.error('Nexus Link Failed:', err);
        renderNexusError(text, 'Connection to Nexus Brain lost. Please verify server status.');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span>Ask Query</span><i class="fas fa-arrow-right"></i>';
    }
}

// Render Synchronized Result Card
function renderNexusCard(query, responseBody) {
    const stream = document.getElementById('resultsStream');
    
    // 1. DATA SYNCHRONIZATION (Mapping to Backend Nesting)
    const _id = responseBody.session_id || `rec-${Date.now()}`;
    const _insight = responseBody.explanation || "No automated insight available.";
    const _data = responseBody.data || {};
    const _rows = _data.results || [];
    const _viz = responseBody.visualization || null;
    const _meta = responseBody.metadata || {};
    
    const card = document.createElement('div');
    card.className = 'feed-card';
    
    // Extract usage stats safely
    const _usage = _meta.usage || {};
    const _latency = _usage.latency_ms || 0;
    const _tokens = _usage.total_tokens || 0;
    const _cost = _usage.cost_usd !== undefined ? _usage.cost_usd : null;
    const _model = _usage.model || 'local';
    const _costLabel = _cost === 0.0 ? 'Free (Local)' : (_cost ? `$${_cost.toFixed(5)}` : '—');
    
    card.innerHTML = `
        <div class="card-header">
            <div class="card-title">
                <i class="fas fa-bolt" style="color: var(--primary);"></i>
                <span>ANALYSIS: "${query}"</span>
            </div>
            <div style="display:flex; gap:1rem; align-items:center; font-size: 0.78rem; color: var(--text-muted);">
                <span title="Latency"><i class="fas fa-clock" style="margin-right:0.3rem;"></i>${_latency}ms</span>
                <span title="Tokens used"><i class="fas fa-coins" style="margin-right:0.3rem;"></i>${_tokens} tokens</span>
                <span title="Estimated cost" style="color: ${_cost === 0.0 ? 'var(--success)' : 'var(--text-muted)'};">
                    <i class="fas fa-tag" style="margin-right:0.3rem;"></i>${_costLabel}
                </span>
                <span title="Model">${_model}</span>
            </div>
        </div>
        
        <div class="insight-content" id="pulse-${_id}">
            <!-- Typewriter injection -->
        </div>

        <div class="kpi-row" style="margin-top: 2rem; margin-bottom: 2rem;">
            <div class="kpi-box">
                <div class="kpi-label">RECORDS RETRIEVED</div>
                <div class="kpi-val">${_data.total_rows || _rows.length}</div>
            </div>
        </div>

        <div class="chart-box" id="viz-${_id}" style="margin-bottom: 2rem; height: 350px;"></div>

        <div class="table-wrap">
            <table id="tbl-${_id}"></table>
        </div>

        <div style="margin-top: 2rem; opacity: 0.6;">
            <div class="kpi-label">COMPILED SQL ENGINE</div>
            <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; padding: 1rem; background: var(--bg-ice); border-radius: 8px;">
                ${_meta.generated_sql || '-- SQL Abstracted --'}
            </div>
        </div>
    `;

    stream.prepend(card);

    // 2. ENHANCEMENTS
    injectTypewriter(`pulse-${_id}`, _insight);

    if (_viz && _viz.data && _viz.data.length > 0) {
        drawNexusChart(`viz-${_id}`, _viz);
    } else {
        const box = document.getElementById(`viz-${_id}`);
        if (box) box.style.display = 'none';
    }

    if (_rows.length > 0) {
        populateNexusTable(`tbl-${_id}`, _rows);
    }
}

function renderNexusError(query, message) {
    const stream = document.getElementById('resultsStream');
    const card = document.createElement('div');
    card.className = 'feed-card';
    card.style.borderLeft = '4px solid var(--error)';
    card.innerHTML = `
        <div class="card-header">
            <div class="card-title" style="color: var(--error);">
                <i class="fas fa-exclamation-triangle"></i>
                <span>ENGINE REJECTION</span>
            </div>
        </div>
        <div class="insight-content" style="color: var(--text-main);">
            We hit a wall with: "${query}"
            <br><small style="color: var(--error);">${message}</small>
        </div>
    `;
    stream.prepend(card);
}

// UTILITIES
function injectTypewriter(targetId, textString) {
    const el = document.getElementById(targetId);
    if (!el || !textString) return;
    
    let pointer = 0;
    el.innerHTML = '';
    
    function tick() {
        if (pointer < textString.length) {
            el.innerHTML += textString.charAt(pointer);
            pointer++;
            setTimeout(tick, 10);
        }
    }
    tick();
}

function drawNexusChart(chartId, package) {
    const context = {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#1e293b', family: 'Inter' },
        margin: { t: 40, b: 60, l: 60, r: 20 },
        xaxis: { gridcolor: 'rgba(0,0,0,0.05)', zeroline: false },
        yaxis: { gridcolor: 'rgba(0,0,0,0.05)', zeroline: false },
        showlegend: true
    };

    const config = { responsive: true, displayModeBar: false };
    const themeColors = ['#4f46e5', '#10b981', '#f59e0b', '#ef4444', '#6366f1'];
    
    if (package.data) {
        package.data.forEach((tr, i) => {
            if (tr.type !== 'pie') {
                tr.marker = { color: tr.marker?.color || themeColors[i % 5] };
            }
        });
    }

    Plotly.newPlot(chartId, package.data || [], { ...package.layout, ...context }, config);
}

function populateNexusTable(tableId, rows) {
    const el = document.getElementById(tableId);
    if (!el || !rows.length) return;

    const headers = Object.keys(rows[0]);
    let content = `<thead><tr>${headers.map(h => `<th>${h}</th>`).join('')}</tr></thead>`;
    content += `<tbody>${rows.map(r => `<tr>${headers.map(h => `<td>${r[h]}</td>`).join('')}</tr>`).join('')}</tbody>`;
    el.innerHTML = content;
}

// ================= NEXUS ATLAS LOGIC =================
let atlasNetwork = null;
let atlasInitialized = false;

// Vibrant color palette for concentric node grouping
const ATLAS_COLORS = {
    primary: '#FFD700',    // Bright yellow
    secondary: '#8A2BE2',  // Deep purple
    tertiary: '#32CD32',   // Lime green
    quaternary: '#1E90FF', // Vivid blue
    accent: '#FF6B35'      // Orange
};

const NODE_COLOR_MAP = [
    ATLAS_COLORS.primary,
    ATLAS_COLORS.secondary,
    ATLAS_COLORS.tertiary,
    ATLAS_COLORS.quaternary,
    ATLAS_COLORS.accent
];

async function initAtlas() {
    const container = document.getElementById('atlasContainer');
    const overlay = document.getElementById('atlasOverlay');
    if (!container) return;

    // Prevent double initialization
    if (atlasInitialized && atlasNetwork) {
        setTimeout(() => {
            atlasNetwork.redraw();
            atlasNetwork.fit({ animation: { duration: 300 } });
        }, 100);
        return;
    }

    // Ensure overlay is visible before initializing
    if (!overlay.classList.contains('active')) {
        console.warn('Atlas container not visible, deferring initialization');
        return;
    }

    // Show loading state
    container.innerHTML = '<div style="display:flex; height:100%; align-items:center; justify-content:center; color:var(--text-muted);"><i class="fas fa-circle-notch fa-spin fa-2x"></i><span style="margin-left:1rem">Loading topology...</span></div>';

    try {
        const response = await fetch(`${API_ROOT}/atlas`);
        if (!response.ok) throw new Error(`API returned ${response.status}`);
        const data = await response.json();

        if(!data.nodes || data.nodes.length === 0) {
            container.innerHTML = '<div style="display:flex; height:100%; align-items:center; justify-content:center; color:var(--text-muted);flex-direction:column;"><i class="fas fa-project-diagram fa-2x" style="margin-bottom:1rem;opacity:0.5"></i>Nexus Topology Pending...</div>';
            return;
        }

        // Calculate node centrality for sizing
        const edgeCounts = {};
        data.edges.forEach(e => {
            edgeCounts[e.from] = (edgeCounts[e.from] || 0) + 1;
            edgeCounts[e.to] = (edgeCounts[e.to] || 0) + 1;
        });

        const maxEdges = Math.max(...Object.values(edgeCounts), 1);

        // Transform nodes with vibrant colors and dynamic sizing
        const styledNodes = data.nodes.map((node, idx) => {
            const connections = edgeCounts[node.id] || 0;
            // Scale size from 15 (terminal) to 45 (hub) based on connectivity
            const size = 15 + (connections / maxEdges) * 30;
            const color = NODE_COLOR_MAP[idx % NODE_COLOR_MAP.length];

            return {
                id: node.id,
                label: node.label,
                size: size,
                color: {
                    background: color,
                    border: color,
                    highlight: { background: '#ffffff', border: color },
                    hover: { background: '#ffffff', border: color }
                },
                group: idx % 5
            };
        });

        // Transform edges with directed arrows and color inheritance
        const styledEdges = data.edges.map(e => {
            const sourceNode = styledNodes.find(n => n.id === e.from);
            const sourceColor = sourceNode ? sourceNode.color.background : '#94a3b8';

            return {
                from: e.from,
                to: e.to,
                color: {
                    color: sourceColor,
                    highlight: sourceColor,
                    hover: sourceColor,
                    inherit: false
                },
                arrows: { to: { enabled: true, scaleFactor: 0.6 } }
            };
        });

        const visNodes = new vis.DataSet(styledNodes);
        const visEdges = new vis.DataSet(styledEdges);

        const options = {
            nodes: {
                shape: 'dot',
                borderWidth: 0,
                borderWidthSelected: 2,
                font: {
                    face: 'Arial, Helvetica, sans-serif',
                    color: '#1e293b',
                    size: 13,
                    background: 'transparent'
                },
                shadow: {
                    enabled: true,
                    color: 'rgba(0, 0, 0, 0.15)',
                    size: 8,
                    x: 2,
                    y: 4
                },
                scaling: {
                    min: 15,
                    max: 45
                }
            },
            edges: {
                width: 1.5,
                smooth: {
                    type: 'continuous',
                    roundness: 0.5
                },
                selectionWidth: 3,
                hoverWidth: 2
            },
            physics: {
                enabled: true,
                forceAtlas2Based: {
                    gravitationalConstant: -60,
                    centralGravity: 0.015,
                    springLength: 180,
                    springConstant: 0.08,
                    damping: 0.9,
                    avoidOverlap: 0.5
                },
                maxVelocity: 50,
                minVelocity: 0.1,
                solver: 'forceAtlas2Based',
                stabilization: {
                    enabled: true,
                    iterations: 200,
                    updateInterval: 25
                }
            },
            layout: {
                randomSeed: 2
            },
            interaction: {
                hover: true,
                tooltipDelay: 150,
                zoomView: true,
                dragView: true
            }
        };

        container.innerHTML = '';
        atlasNetwork = new vis.Network(container, { nodes: visNodes, edges: visEdges }, options);
        atlasInitialized = true;

        // Progressive zoom reveal
        atlasNetwork.once('stabilizationIterationsDone', () => {
            atlasNetwork.fit({
                animation: { duration: 800, easingFunction: 'easeInOutQuad' }
            });
        });

        setTimeout(() => {
            if (atlasNetwork) {
                atlasNetwork.redraw();
                atlasNetwork.fit({
                    animation: { duration: 600, easingFunction: 'easeInOutQuad' }
                });
            }
        }, 500);

        atlasNetwork.on("click", (params) => {
            if (params.nodes.length > 0) {
                const nodeId = params.nodes[0];
                showTableDetails(nodeId);
            } else {
                document.getElementById('atlasDetails').classList.remove('active');
            }
        });

    } catch (err) {
        console.error('Atlas Failed to Load:', err);
        container.innerHTML = `<div style="display:flex; height:100%; align-items:center; justify-content:center; color:var(--error);flex-direction:column;padding:2rem;text-align:center;"><i class="fas fa-exclamation-triangle fa-2x" style="margin-bottom:1rem"></i>Failed to sync with Nexus Atlas.<br><small style="margin-top:0.5rem;opacity:0.7">${err.message}</small></div>`;
    }
}

async function showTableDetails(tableName) {
    const pane = document.getElementById('atlasDetails');
    const nameEl = document.getElementById('detailTableName');
    const descEl = document.getElementById('detailTableDesc');
    const colEl = document.getElementById('detailCols');
    const tableEl = document.getElementById('detailSampleTbl');

    pane.classList.add('active');
    nameEl.innerText = tableName.toUpperCase();
    descEl.innerText = "Synchronizing with table indices...";
    colEl.innerHTML = '';
    tableEl.innerHTML = '';

    try {
        const response = await fetch(`${API_ROOT}/table/${tableName}`);
        const data = await response.json();

        descEl.innerText = data.description || `Structural metadata for the ${tableName} collective.`;
        
        // Render Columns
        Object.entries(data.columns).forEach(([col, type]) => {
            const span = document.createElement('span');
            span.style.cssText = 'font-size: 0.75rem; padding: 0.25rem 0.75rem; background: var(--bg-ice); border-radius: 8px; border: 1px solid var(--border-soft); color: var(--text-muted); font-family: "JetBrains Mono";';
            span.innerHTML = `${col} <span style="opacity: 0.5;">${type}</span>`;
            colEl.appendChild(span);
        });

        // Render Sample Table
        if (data.sample_data && data.sample_data.length > 0) {
            populateNexusTable('detailSampleTbl', data.sample_data);
        } else {
            tableEl.innerHTML = '<tr><td style="color:var(--text-muted); text-align:center; padding: 2rem;">No exploratory records found in this table segment.</td></tr>';
        }

    } catch (err) {
        console.error('Table Sync Error:', err);
        descEl.innerHTML = `<span style="color:var(--error)">Intelligence Link Interrupted:</span> ${err.message}`;
    }
}
// ================= KNOWLEDGE DRAWER =================
let _knowledgeLoaded = false;

async function loadKnowledge() {
    if (_knowledgeLoaded) return; // Only fetch once
    const container = document.getElementById('schemaContainer');
    if (!container) return;

    container.innerHTML = '<div style="color:var(--text-muted);padding:2rem;text-align:center;"><i class="fas fa-circle-notch fa-spin"></i> Synchronizing schema...</div>';

    try {
        // Fetch table topology from Atlas endpoint
        const res = await fetch(`${API_ROOT}/atlas`);
        const data = await res.json();

        if (!data.nodes || data.nodes.length === 0) {
            container.innerHTML = '<div style="color:var(--text-muted);padding:2rem;">No schema data found.</div>';
            return;
        }

        container.innerHTML = '';

        // For each table node, fetch full detail and render a schema card
        for (const node of data.nodes) {
            const card = document.createElement('div');
            card.style.cssText = 'margin-bottom:2rem; padding:1.5rem; background:var(--bg-ice); border-radius:16px; border:1px solid var(--border-soft);';

            // Header
            card.innerHTML = `
                <div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:1rem;">
                    <div style="width:8px;height:8px;border-radius:50%;background:var(--primary);"></div>
                    <span style="font-family:'Outfit',sans-serif;font-weight:700;font-size:1rem;color:var(--text-bright);">${node.label}</span>
                </div>
                <div class="knowledge-cols-${node.id}" style="display:flex;flex-wrap:wrap;gap:0.4rem;">
                    <span style="color:var(--text-muted);font-size:0.8rem;"><i class="fas fa-circle-notch fa-spin"></i> Loading columns...</span>
                </div>
            `;
            container.appendChild(card);

            // Load column details async
            fetch(`${API_ROOT}/table/${node.id}`)
                .then(r => r.json())
                .then(detail => {
                    const colWrap = card.querySelector(`.knowledge-cols-${node.id}`);
                    if (!colWrap) return;
                    const cols = detail.columns || {};
                    colWrap.innerHTML = Object.entries(cols).map(([col, type]) =>
                        `<span style="font-size:0.72rem;padding:0.2rem 0.6rem;background:white;border:1px solid var(--border-soft);border-radius:6px;color:var(--text-muted);font-family:'JetBrains Mono',monospace;">
                            <strong style="color:var(--text-main)">${col}</strong>&nbsp;<span style="opacity:0.5">${type}</span>
                        </span>`
                    ).join('');

                    // Show row count if available
                    const rows = detail.sample_data ? detail.sample_data.length : 0;
                    colWrap.insertAdjacentHTML('beforeend',
                        `<div style="width:100%;margin-top:0.75rem;font-size:0.75rem;color:var(--text-muted);">Sample preview: ${rows} rows</div>`
                    );
                })
                .catch(() => {});
        }

        // Show relationships
        if (data.edges && data.edges.length > 0) {
            const relCard = document.createElement('div');
            relCard.style.cssText = 'margin-bottom:2rem; padding:1.5rem; background:var(--primary-light); border-radius:16px; border:1px solid rgba(79,70,229,0.2);';
            relCard.innerHTML = `
                <div style="font-family:'Outfit',sans-serif;font-weight:700;font-size:0.9rem;color:var(--primary);margin-bottom:1rem;text-transform:uppercase;letter-spacing:2px;">Relationships</div>
                ${data.edges.map(e =>
                    `<div style="font-size:0.82rem;color:var(--text-muted);padding:0.4rem 0;font-family:'JetBrains Mono',monospace;">
                        ${e.from} <span style="color:var(--primary)">→</span> ${e.to}
                    </div>`
                ).join('')}
            `;
            container.appendChild(relCard);
        }

        _knowledgeLoaded = true;
    } catch (err) {
        container.innerHTML = `<div style="color:var(--error);padding:2rem;">Failed to load schema: ${err.message}</div>`;
    }
}

// ===================== DB UPLOAD MODAL LOGIC =====================
function initUploadModal() {
    const modal = document.getElementById('uploadModal');
    const closeBtn = document.getElementById('closeUploadModal');
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('dbFileInput');
    const useBtn = document.getElementById('useThisDbBtn');

    if (!modal) return;

    // Close modal
    if (closeBtn) closeBtn.onclick = () => resetAndCloseModal();
    modal.onclick = (e) => { if (e.target === modal) resetAndCloseModal(); };

    // Drag and drop
    if (dropZone) {
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('drag-over');
        });
        dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('drag-over');
            const file = e.dataTransfer.files[0];
            if (file) handleFileUpload(file);
        });
    }

    // File picker
    if (fileInput) {
        fileInput.onchange = () => {
            if (fileInput.files[0]) handleFileUpload(fileInput.files[0]);
        };
    }

    // Use this DB button
    if (useBtn) {
        useBtn.onclick = () => {
            resetAndCloseModal();
            // Show a welcome query suggestion
            const input = document.getElementById('queryInput');
            if (input && !input.value) {
                input.value = 'Show all tables and row counts';
                input.focus();
            }
        };
    }
}

function resetAndCloseModal() {
    document.getElementById('uploadModal').classList.remove('active');
    // Reset state
    const progress = document.getElementById('uploadProgress');
    const success = document.getElementById('uploadSuccess');
    const fill = document.getElementById('progressFill');
    if (progress) progress.classList.remove('active');
    if (success) success.classList.remove('active');
    if (fill) fill.style.width = '0%';
    const fileInput = document.getElementById('dbFileInput');
    if (fileInput) fileInput.value = '';
}

let _uploadedDbData = null;

async function handleFileUpload(file) {
    const allowedExts = ['.db', '.sqlite', '.sqlite3'];
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!allowedExts.includes(ext)) {
        alert('Invalid file type. Please upload a .db, .sqlite, or .sqlite3 file.');
        return;
    }

    // Show progress
    const progress = document.getElementById('uploadProgress');
    const fill = document.getElementById('progressFill');
    const label = document.getElementById('progressLabel');
    const success = document.getElementById('uploadSuccess');
    const dropZone = document.getElementById('dropZone');

    if (progress) progress.classList.add('active');
    if (success) success.classList.remove('active');
    if (dropZone) dropZone.style.pointerEvents = 'none';

    // Animate progress bar
    let prog = 0;
    const ticker = setInterval(() => {
        prog = Math.min(prog + Math.random() * 15, 85);
        if (fill) fill.style.width = prog + '%';
    }, 200);

    try {
        const formData = new FormData();
        formData.append('file', file);
        if (label) label.textContent = `Uploading ${file.name}...`;

        const res = await fetch(`${API_ROOT}/upload-db`, {
            method: 'POST',
            body: formData
        });

        clearInterval(ticker);

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Upload failed');
        }

        const data = await res.json();
        _uploadedDbData = data;

        // Complete progress bar
        if (fill) fill.style.width = '100%';
        if (label) label.textContent = 'Schema analysis complete!';

        setTimeout(() => {
            if (progress) progress.classList.remove('active');
            showUploadSuccess(data);
        }, 600);

    } catch (err) {
        clearInterval(ticker);
        if (fill) fill.style.width = '0%';
        if (progress) progress.classList.remove('active');
        if (dropZone) dropZone.style.pointerEvents = '';
        alert('Upload failed: ' + err.message);
    }
}

function showUploadSuccess(data) {
    const success = document.getElementById('uploadSuccess');
    const titleEl = document.getElementById('uploadSuccessTitle');
    const tableCount = document.getElementById('tableCountLabel');
    const relCount = document.getElementById('relCountLabel');
    const tableList = document.getElementById('detectedTablesList');
    const useBtn = document.getElementById('useThisDbBtn');

    if (titleEl) titleEl.textContent = data.filename + ' ready!';
    if (tableCount) tableCount.textContent = data.table_count;
    if (relCount) relCount.textContent = data.relationship_count;

    if (tableList) {
        tableList.innerHTML = data.tables.map(t =>
            `<span class="table-badge">${t}</span>`
        ).join('');
    }

    // Store session for queries
    setCustomDbSession({
        session_id: data.session_id,
        filename: data.filename,
        tables: data.tables
    });

    if (success) success.classList.add('active');

    if (useBtn) {
        useBtn.onclick = () => {
            resetAndCloseModal();
            const input = document.getElementById('queryInput');
            if (input && !input.value) {
                input.value = 'Show me the first 10 rows from ' + (data.tables[0] || 'the first table');
                input.focus();
            }
        };
    }
}
